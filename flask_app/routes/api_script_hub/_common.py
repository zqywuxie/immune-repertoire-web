"""Shared constants, state, and helper functions for the Script Hub API.

All route handlers live in sibling domain modules (cache, modules_config,
boxplot, profile_analysis, enrichment, tasks_results).
"""

from __future__ import annotations

import io
import json
import logging
import math
import os
import re
import threading
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from flask import current_app

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
from flask_app.services.db_alignment_service import DBAlignmentService
from flask_app.services.boxplot_service import BoxPlotService
from flask_app.services.pep_analysis_service import PepAnalysisService
from flask_app.services.topclone_service import TopCloneService
from flask_app.services.umap_service import UmapService
from flask_app.services.volcano_service import VolcanoService
from flask_app.services.go_kegg_enrichment_service import GoKeggEnrichmentService
from flask_app.services.umapin_service import UmapinService
from flask_app.services.ml_analysis_service import MLAnalysisService
from flask_app.services.pgen_analysis_service import PgenAnalysisService
from flask_app.services.mait_nkt_service import MaitNktService
from flask_app.services.figure_style import save_publication_png
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.result_path_resolver import candidate_job_roots, scoped_results_root
from flask_app.services.script_hub_job_service import get_script_hub_job_service
from flask_app.services.user_scope import assert_owned, current_user_id

logger = logging.getLogger(__name__)

_script_executor = ThreadPoolExecutor(max_workers=2)
_script_task_lock = threading.Lock()
_script_tasks: Dict[str, Dict[str, Any]] = {}

_RESULT_DIR = "script_hub"
_ALLOWED_MODULES = {"db-alignment", "boxplot", "profile", "topclone", "pep-analysis", "pgen-analysis", "umap", "volcano", "go-kegg-enrichment", "umapin", "ml-analysis", "mait-nkt"}
_COLUMN_HINTS = {
    "cdr3_column": ["cdr3(pep)", "cdr3_pep", "cdr3aa", "cdr3_aa", "cdr3", "aminoacid", "sequence"],
    "copy_column": ["copy", "copies", "count", "reads", "umis", "umi", "frequency"],
}
_SUPPORTED_CHAINS = {"TRA", "TRB"}
_SUPPORTED_CHAINS_WIDE = {"IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"}
_RESULT_FILES = {"viewer.html", "metadata.json", "db_alignment_bundle.zip", "specify_ratio.csv", "specify_ratio_with_profile.csv", "alignment_summary.csv", "pep_analysis_metadata.json", "pep_analysis_results.zip", "pgen_analysis_metadata.json", "pgen_analysis_results.zip", "boxplot_results.zip", "topclone_results.zip", "ml_analysis_results.zip", "mait_nkt_results.zip"}

# Encoding fallback for CSV/TSV files (GBK common in Chinese Windows environments)
_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]


class ScriptTaskCancelled(BaseException):
    """Cooperative cancellation signal for Script Hub worker threads."""


def _projects_root() -> Path:
    return Path(current_app.root_path) / "data" / "projects"


def _project_asset_service():
    from flask_app.services.project_asset_service import get_project_asset_service

    return get_project_asset_service(_projects_root())


def _robust_read_csv(path, **kwargs):
    """Read CSV/TSV/XLSX with encoding fallback chain and xlsx support."""
    suffix = str(path).lower()
    if suffix.endswith((".xlsx", ".xls", ".xlsm")):
        kwargs.pop("sep", None)
        kwargs.pop("encoding", None)
        kwargs.pop("low_memory", None)
        return pd.read_excel(path, sheet_name=kwargs.pop("sheet_name", 0), **kwargs)
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(path, encoding="latin-1", **kwargs)


def _history_entry(progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "progress": round(progress, 2),
        "stage": stage,
        "detail": detail,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "meta": meta or {},
    }


def _set_task_state(task_id: str, **updates: Any) -> None:
    with _script_task_lock:
        task = _script_tasks.setdefault(task_id, {})
        if task.get("status") == "cancelled" and updates.get("status") != "cancelled":
            snapshot = dict(task)
        else:
            updates.setdefault("user_id", task.get("user_id") or current_user_id())
            task.update(updates)
            snapshot = dict(task)
    _sync_job_state(task_id, snapshot)


def _get_task_state(task_id: str) -> Dict[str, Any] | None:
    with _script_task_lock:
        task = _script_tasks.get(task_id)
        return dict(task) if task else None


def _sync_job_state(task_id: str, task: Dict[str, Any]) -> None:
    meta = task.get("meta") if isinstance(task.get("meta"), dict) else {}
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    module_name = task.get("module") or meta.get("module") or result.get("module") or ""
    job = {
        **task,
        "job_id": task.get("job_id") or task_id,
        "task_id": task_id,
        "module": module_name,
    }
    try:
        get_script_hub_job_service().upsert_job(str(job["job_id"]), job)
    except Exception:
        logger.warning("Failed to sync Script Hub job state for %s", task_id, exc_info=True)


def _script_task_cancel_requested(task_id: str) -> bool:
    task = _get_task_state(task_id)
    if task and task.get("status") == "cancelled":
        return True
    try:
        job = get_script_hub_job_service().get_job(task_id)
    except Exception:
        job = None
    return bool(job and (job.get("cancel_requested") or job.get("status") == "cancelled"))


def _mark_script_task_cancelled(task_id: str, detail: str = "Job cancelled by user.") -> Dict[str, Any]:
    history_item = _history_entry(100.0, "Cancelled", detail, {"phase": "cancelled"})
    with _script_task_lock:
        task = _script_tasks.setdefault(task_id, {})
        meta = task.get("meta") if isinstance(task.get("meta"), dict) else {}
        task.update({
            "status": "cancelled",
            "stage": "Cancelled",
            "detail": detail,
            "meta": {**meta, "phase": "cancelled"},
        })
        history = task.setdefault("history", [])
        if not history or history[-1] != history_item:
            history.append(history_item)
            if len(history) > 80:
                del history[:-80]
        snapshot = dict(task)
    _sync_job_state(task_id, snapshot)
    return snapshot


def _record_stage(task_id: str, progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> None:
    if _script_task_cancel_requested(task_id):
        _mark_script_task_cancelled(task_id)
        raise ScriptTaskCancelled()

    history_item = _history_entry(progress, stage, detail, meta)
    with _script_task_lock:
        task = _script_tasks.setdefault(task_id, {})
        if task.get("status") == "cancelled":
            raise ScriptTaskCancelled()
        task["status"] = "running"
        task["progress"] = round(progress, 2)
        task["stage"] = stage
        task["detail"] = detail
        task["meta"] = meta or {}
        history = task.setdefault("history", [])
        if not history or history[-1] != history_item:
            history.append(history_item)
            if len(history) > 80:
                del history[:-80]
        snapshot = dict(task)
    _sync_job_state(task_id, snapshot)


def _resolve_results_root() -> Path:
    return scoped_results_root()


def _sanitize_nan(obj: Any) -> Any:
    """Recursively replace non-JSON scalar values with strict JSON-safe values."""
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_nan(v) for v in obj]
    if obj is None:
        return None
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(obj, "item") and callable(getattr(obj, "item")):
        try:
            return _sanitize_nan(obj.item())
        except (TypeError, ValueError):
            pass
    if hasattr(obj, "isoformat") and callable(getattr(obj, "isoformat")):
        try:
            return obj.isoformat()
        except (TypeError, ValueError):
            pass
    return obj


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _normalize_chain(raw_chain: str) -> str:
    normalized = str(raw_chain or "").strip().upper()
    alias_map = {
        "TCRA": "TRA",
        "TCRB": "TRB",
    }
    return alias_map.get(normalized, normalized)


def _infer_chain_from_filename(filename: str) -> str:
    return DBAlignmentService._infer_chain_from_filename(filename)  # pylint: disable=protected-access


def _find_matching_column(columns: List[str], patterns: List[str]) -> str:
    lowered = [(column, str(column or "").strip().lower()) for column in columns]
    for pattern in patterns:
        normalized_pattern = pattern.lower()
        for column, lowered_name in lowered:
            if lowered_name == normalized_pattern or normalized_pattern in lowered_name:
                return column
    return ""


def _strip_table_suffix(filename: str) -> str:
    """Remove common table extensions, including compressed variants."""
    name = str(filename or "")
    lowered = name.lower()
    for suffix in (".csv.gz", ".tsv.gz", ".txt.gz", ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".xlsm"):
        if lowered.endswith(suffix):
            return name[:-len(suffix)]
    return Path(name).stem


def _is_table_file(path: Path) -> bool:
    lowered = path.name.lower()
    return lowered.endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz", ".xlsx", ".xls", ".xlsm"))


def _read_header_columns(path: Path) -> List[str]:
    sep = "\t" if path.name.lower().endswith((".tsv", ".tsv.gz")) else ","
    try:
        return _robust_read_csv(path, nrows=0, sep=sep).columns.tolist()
    except Exception as exc:  # pragma: no cover - callers surface warnings
        logger.warning("Failed to read header from %s: %s", path, exc)
        return []


def _looks_like_pep_table(path: Path, columns: Optional[List[str]] = None) -> bool:
    cols = columns if columns is not None else _read_header_columns(path)
    lowered = {str(col or "").strip().lower() for col in cols}
    required_any = {"cdr3(pep)", "cdr3_pep", "cdr3aa", "cdr3_aa", "cdr3"}
    return bool(required_any & lowered) and "copy" in lowered and "v" in lowered and "j" in lowered


def _chain_from_parent_dirs(path: Path) -> str:
    for parent in [path.parent, *list(path.parents)[:3]]:
        chain = _normalize_chain(parent.name)
        if chain in _SUPPORTED_CHAINS_WIDE:
            return chain
    return ""


def _resolve_profile_path(base_path: str, profile_path: Optional[str]) -> Optional[Path]:
    explicit = Path(str(profile_path or "").strip()) if str(profile_path or "").strip() else None
    if explicit and explicit.exists() and explicit.is_file():
        return explicit.resolve()
    return None


def _collect_asset_hints(base_path: str, profile_path: Optional[str]) -> Dict[str, Any]:
    base = Path(base_path)
    profile_file = _resolve_profile_path(base_path, profile_path)
    profile_columns: List[str] = []
    if profile_file is not None:
        try:
            profile_columns = _robust_read_csv(profile_file, nrows=0).columns.tolist()
        except Exception as exc:  # pragma: no cover - defensive, reported to UI
            logger.warning("Failed to read profile header from %s: %s", profile_file, exc)

    datapoint_candidates: List[str] = []
    for root in [base, base.parent] if base.parent != base else [base]:
        for candidate in sorted(root.glob("*Datapoint*.csv"))[:5]:
            datapoint_candidates.append(str(candidate.resolve()))
        for candidate in sorted(root.glob("Datapoint*.tsv"))[:5]:
            datapoint_candidates.append(str(candidate.resolve()))

    deduped_datapoints = list(dict.fromkeys(datapoint_candidates))
    return {
        "profile_path": str(profile_file) if profile_file else "",
        "profile_columns": profile_columns,
        "available_categories": [column for column in profile_columns if str(column).strip().lower() != "sample"],
        "datapoint_candidates": deduped_datapoints[:10],
    }


def _is_profile_like_file(path: Path) -> bool:
    lowered = path.name.lower()
    return lowered.startswith("profile") and lowered.endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz", ".xlsx", ".xls", ".xlsm"))


def _infer_wide_chain_from_filename(filename: str) -> str:
    stem = _strip_table_suffix(filename)
    upper_name = stem.upper()
    for chain in sorted(_SUPPORTED_CHAINS_WIDE, key=len, reverse=True):
        if (
            upper_name.endswith(f"__{chain}")
            or upper_name.endswith(f"_{chain}")
            or upper_name.endswith(f"-{chain}")
            or f"_{chain}_" in upper_name
            or f"-{chain}-" in upper_name
        ):
            return chain
    inferred = _normalize_chain(_infer_chain_from_filename(filename))
    return inferred if inferred in _SUPPORTED_CHAINS_WIDE else ""


def _sample_name_from_pep_file(path: Path, chain: str) -> str:
    stem = _strip_table_suffix(path.name)
    upper_stem = stem.upper()
    markers = [f"__{chain}", f"_{chain}", f"-{chain}"]
    for marker in markers:
        index = upper_stem.rfind(marker)
        if index > 0:
            return stem[:index].rstrip("_- ")
    if _normalize_chain(path.parent.name) == chain:
        return stem
    return Path(stem).stem


def _iter_candidate_pep_files(paths: List[str]) -> List[Path]:
    files: List[Path] = []
    seen: set[str] = set()
    for raw_path in paths:
        if not str(raw_path or "").strip():
            continue
        path = Path(str(raw_path).strip())
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else sorted(
            candidate for candidate in path.rglob("*")
            if candidate.is_file() and candidate.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz"))
        )
        for candidate in candidates:
            if not candidate.is_file() or _is_profile_like_file(candidate):
                continue
            chain = _infer_wide_chain_from_filename(candidate.name) or _chain_from_parent_dirs(candidate)
            if not chain and not _looks_like_pep_table(candidate):
                continue
            if chain and not _looks_like_pep_table(candidate):
                continue
            resolved = str(candidate.resolve())
            if resolved not in seen:
                seen.add(resolved)
                files.append(candidate.resolve())
    return files


def _read_table_columns(path: Optional[Path]) -> List[str]:
    if path is None or not path.exists() or not path.is_file():
        return []
    return _read_header_columns(path)


def _is_readable_table_asset(path: str) -> bool:
    target = Path(str(path or "").strip())
    if not target.exists() or not target.is_file():
        return False
    try:
        if target.stat().st_size <= 0:
            return False
    except OSError:
        return False
    return bool(_read_table_columns(target))


def _project_assets_root() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "projects"


def _resolve_registered_asset_path(project_id: str, storage_path: str) -> str:
    raw_path = str(storage_path or "").strip()
    if not raw_path:
        return ""
    if Path(raw_path).exists():
        return raw_path

    normalized = raw_path.replace("\\", "/")
    marker = f"data/projects/{project_id}/assets/"
    index = normalized.lower().find(marker.lower())
    if index < 0:
        return raw_path

    relative = normalized[index + len(marker):].strip("/")
    if not relative:
        return raw_path
    candidate = _project_assets_root() / str(project_id) / "assets" / Path(*relative.split("/"))
    return str(candidate) if candidate.exists() else raw_path


def _is_project_profile_asset(asset: Any) -> bool:
    asset_type = str(getattr(asset, "asset_type", "") or "").strip().lower()
    return asset_type == "profile"


def _is_project_transcriptome_asset(asset: Any) -> bool:
    asset_type = str(getattr(asset, "asset_type", "") or "").strip().lower()
    return asset_type == "transcriptome"


def _collect_project_script_hub_assets(project_id: Optional[str]) -> Dict[str, Any]:
    if not str(project_id or "").strip():
        return {
            "pep_paths": [],
            "profile_path": "",
            "profile_paths": [],
            "invalid_profile_paths": [],
            "transcriptome_path": "",
            "transcriptome_paths": [],
            "invalid_transcriptome_paths": [],
        }
    try:
        from flask_app.models.database import Project
    except Exception as exc:  # pragma: no cover - defensive import fallback
        logger.warning("ProjectAsset import failed while collecting Script Hub assets: %s", exc)
        return {
            "pep_paths": [],
            "profile_path": "",
            "profile_paths": [],
            "invalid_profile_paths": [],
            "transcriptome_path": "",
            "transcriptome_paths": [],
            "invalid_transcriptome_paths": [],
        }

    project = Project.query.get(str(project_id).strip())
    assert_owned(project, "Project")
    assets = _project_asset_service().list_assets(str(project_id).strip())
    pep_paths: List[str] = []
    profile_paths: List[str] = []
    transcriptome_paths: List[str] = []
    for asset in assets:
        storage_path = _resolve_registered_asset_path(
            str(getattr(asset, "project_id", "") or project_id).strip(),
            str(getattr(asset, "storage_path", "") or "").strip(),
        )
        if not storage_path:
            continue
        asset_type = str(getattr(asset, "asset_type", "") or "").strip().lower()
        if asset_type == "pep":
            pep_paths.append(storage_path)
        if _is_project_profile_asset(asset):
            profile_paths.append(storage_path)
        if _is_project_transcriptome_asset(asset):
            transcriptome_paths.append(storage_path)

    readable_profiles = [path for path in profile_paths if _is_readable_table_asset(path)]
    invalid_profiles = [path for path in profile_paths if path not in readable_profiles]
    readable_transcriptomes = [path for path in transcriptome_paths if _is_readable_table_asset(path)]
    invalid_transcriptomes = [path for path in transcriptome_paths if path not in readable_transcriptomes]
    return {
        "pep_paths": list(dict.fromkeys(pep_paths)),
        "profile_paths": list(dict.fromkeys(profile_paths)),
        "profile_path": (readable_profiles or [""])[0],
        "invalid_profile_paths": invalid_profiles,
        "transcriptome_paths": list(dict.fromkeys(transcriptome_paths)),
        "transcriptome_path": (readable_transcriptomes or [""])[0],
        "invalid_transcriptome_paths": invalid_transcriptomes,
    }


def _collect_project_cached_usage_assets(project_id: Optional[str]) -> List[Dict[str, Any]]:
    if not str(project_id or "").strip():
        return []
    assets: List[Dict[str, Any]] = []
    try:
        from flask_app.models.database import ProjectAsset
    except Exception as exc:  # pragma: no cover - defensive import fallback
        logger.warning("ProjectAsset import failed while collecting cached usage assets: %s", exc)
        ProjectAsset = None

    if ProjectAsset is not None:
        rows = _project_asset_service().list_assets(str(project_id).strip(), asset_type="cached_usage")
        for asset in rows:
            storage_path = _resolve_registered_asset_path(
                str(getattr(asset, "project_id", "") or project_id).strip(),
                str(getattr(asset, "storage_path", "") or "").strip(),
            )
            metadata = getattr(asset, "metadata_json", None) or {}
            if storage_path:
                assets.append({
                    "id": getattr(asset, "id", ""),
                    "storage_path": storage_path,
                    "original_name": getattr(asset, "original_name", "") or "",
                    "metadata": metadata if isinstance(metadata, dict) else {},
                    "source": "sql",
                })
    try:
        from flask_app.services.mongo_service import get_cached_usage
        for doc in get_cached_usage(str(project_id).strip()):
            metadata = doc.get("metadata_json") if isinstance(doc.get("metadata_json"), dict) else {}
            usage_types = doc.get("usage_types") if isinstance(doc.get("usage_types"), dict) else {}
            merged_metadata = {
                **metadata,
                "source": "mongodb",
                "source_job_id": doc.get("source_job_id", ""),
                "source_result_signature": doc.get("source_result_signature") or metadata.get("source_result_signature", ""),
                "source_result_id": doc.get("source_result_id") or metadata.get("source_result_id", ""),
                "usage_scope": doc.get("usage_scope") or metadata.get("usage_scope", ""),
                "group_field": doc.get("group_field") or metadata.get("group_field", ""),
                "chains": doc.get("chains") or metadata.get("chains", []),
                "group_fields": doc.get("group_fields") or metadata.get("group_fields", []),
                "usage_types": usage_types or metadata.get("usage_types", {}),
            }
            storage_path = str(doc.get("storage_path") or metadata.get("storage_path") or "").strip()
            if storage_path:
                assets.append({
                    "id": str(doc.get("_id") or ""),
                    "storage_path": storage_path,
                    "original_name": doc.get("original_name") or "",
                    "metadata": merged_metadata,
                    "source": "mongodb",
                })
    except Exception:
        logger.warning("Failed to load Mongo cached usage for project %s", project_id, exc_info=True)
    return assets


def _resolve_project_cached_usage_path(data: Dict[str, Any], *, preferred: str) -> str:
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        return ""

    preferred = str(preferred or "").strip().lower()
    candidates: List[str] = []
    for manifest in _pep_cache_manifests_for_project(project_id):
        output_files = manifest.get("output_files") if isinstance(manifest.get("output_files"), dict) else {}
        usage_types = output_files.get("usage_types") if isinstance(output_files.get("usage_types"), dict) else {}
        umapin_tables = output_files.get("umapin_tables") if isinstance(output_files.get("umapin_tables"), dict) else {}
        if preferred == "umapin":
            candidates.extend([
                str(umapin_tables.get("df_1VJusage_all") or "").strip(),
                str(umapin_tables.get("df_VJ_all") or "").strip(),
                str(usage_types.get("1VJusage") or "").strip(),
                str(usage_types.get("0VJusage") or "").strip(),
            ])
        elif preferred == "volcano":
            candidates.extend([
                str(usage_types.get("1VJusage") or "").strip(),
                str(usage_types.get("0VJusage") or "").strip(),
            ])
        else:
            candidates.extend(str(path or "").strip() for path in usage_types.values())

    assets = _collect_project_cached_usage_assets(project_id)
    assets.sort(key=lambda item: 0 if (item.get("metadata") or {}).get("usage_scope") == "usage_cate" else 1)
    for asset in assets:
        meta = asset.get("metadata") or {}
        storage_path = str(asset.get("storage_path") or "").strip()
        if preferred == "umapin":
            candidates.extend([
                str(meta.get("umapin_data_path") or "").strip(),
                str(meta.get("df_1vj_all_path") or "").strip(),
                str(meta.get("df_vj_all_path") or "").strip(),
            ])
        if preferred == "volcano":
            candidates.extend([
                str(meta.get("volcano_data_dir") or "").strip(),
                str(meta.get("usage_1vj_path") or "").strip(),
            ])
        candidates.append(storage_path)

    for raw_path in candidates:
        if not raw_path:
            continue
        target = Path(raw_path)
        if target.exists():
            return str(target.resolve())
    return ""


def _pep_tra_candidates_from_output_base(output_base: Path) -> List[Path]:
    output_base = Path(output_base)
    candidates: List[Path] = [
        output_base / "Pep_shared" / "TRA.csv",
        output_base / "Pep_shared_cate" / "Pep_shared" / "TRA.csv",
    ]
    if output_base.exists() and output_base.is_dir():
        candidates.extend(sorted(output_base.glob("*/Pep_shared_cate/Pep_shared/TRA.csv")))
        candidates.extend(sorted(output_base.glob("*/arrage_pep/Pep_shared_cate/Pep_shared/TRA.csv")))
    seen: set[str] = set()
    unique: List[Path] = []
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _pep_output_base_candidates_from_path(path: Path) -> List[Path]:
    path = Path(path)
    base = path if path.is_dir() else path.parent
    candidates = [base, *list(base.parents)]
    valid: List[Path] = []
    for candidate in candidates:
        if (candidate / "Pep_shared").exists() or (candidate / "pep_analysis_metadata.json").exists():
            valid.append(candidate)
    return valid or candidates[:4]


def _resolve_pep_analysis_tra_source(data: Dict[str, Any]) -> Dict[str, Any]:
    source_job_id = str(data.get("source_job_id") or "").strip()
    project_id = str(data.get("project_id") or "").strip()
    candidates: List[Dict[str, Any]] = []

    if project_id:
        for manifest in _pep_cache_manifests_for_project(project_id):
            job_id = str(manifest.get("job_id") or manifest.get("cache_id") or "").strip()
            if source_job_id and job_id and job_id != source_job_id:
                continue
            output_files = manifest.get("output_files") if isinstance(manifest.get("output_files"), dict) else {}
            pep_shared = output_files.get("pep_shared") if isinstance(output_files.get("pep_shared"), dict) else {}
            tra_path = str(pep_shared.get("TRA") or "").strip()
            if tra_path:
                candidates.append({
                    "tra_path": tra_path,
                    "source_kind": "cache_manifest",
                    "source_job_id": job_id,
                    "output_base": manifest.get("output_base") or "",
                    "metadata": manifest,
                })

    def _add_output_base(output_base: Any, *, source_kind: str, job_id: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        raw = str(output_base or "").strip()
        if not raw:
            return
        base = Path(raw)
        if base.is_file():
            base = base.parent
        candidates.append({
            "output_base": str(base),
            "source_kind": source_kind,
            "source_job_id": job_id,
            "metadata": metadata or {},
        })

    def _add_tra_path(path_value: Any, *, source_kind: str, job_id: str = "", metadata: Optional[Dict[str, Any]] = None) -> None:
        raw = str(path_value or "").strip()
        if not raw:
            return
        candidates.append({
            "tra_path": raw,
            "source_kind": source_kind,
            "source_job_id": job_id,
            "metadata": metadata or {},
        })

    if source_job_id:
        pep_result = _try_find_script_task_result(source_job_id)
        result = pep_result.get("result") if pep_result else {}
        if isinstance(result, dict):
            metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
            _add_output_base(result.get("output_base") or metadata.get("output_base"), source_kind="job", job_id=source_job_id, metadata=metadata)
            intermediate = metadata.get("intermediate_paths") if isinstance(metadata.get("intermediate_paths"), dict) else {}
            for tra_candidate in intermediate.get("tra_candidates") or []:
                _add_tra_path(tra_candidate, source_kind="job_metadata", job_id=source_job_id, metadata=metadata)

    if project_id:
        try:
            rows = _project_asset_service().list_assets(project_id, asset_type="processed_result")
            for row in rows:
                meta = getattr(row, "metadata_json", None) or {}
                if str(meta.get("analysis_type") or "").strip() != "pep-analysis":
                    continue
                nested = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
                merged_meta = {**nested, **meta}
                job_id = str(meta.get("job_id") or nested.get("job_id") or "").strip()
                if source_job_id and job_id and job_id != source_job_id:
                    continue
                _add_output_base(
                    meta.get("output_base") or nested.get("output_base") or getattr(row, "storage_path", ""),
                    source_kind="project_result",
                    job_id=job_id,
                    metadata=merged_meta,
                )
                intermediate = nested.get("intermediate_paths") if isinstance(nested.get("intermediate_paths"), dict) else {}
                for tra_candidate in intermediate.get("tra_candidates") or []:
                    _add_tra_path(tra_candidate, source_kind="project_result_metadata", job_id=job_id, metadata=merged_meta)
        except Exception:
            logger.warning("Failed to inspect project PEP result assets for %s", project_id, exc_info=True)

        cached_assets = _collect_project_cached_usage_assets(project_id)
        for asset in cached_assets:
            meta = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
            if str(meta.get("source_module") or "").strip() != "pep-analysis":
                continue
            job_id = str(meta.get("source_job_id") or "").strip()
            if source_job_id and job_id and job_id != source_job_id:
                continue
            for key in ("pep_shared_TRA_path", "pep_shared_cate_TRA_path"):
                _add_tra_path(meta.get(key), source_kind="cached_usage", job_id=job_id, metadata=meta)
            for key in ("pep_output_base", "output_base"):
                _add_output_base(meta.get(key), source_kind="cached_usage", job_id=job_id, metadata=meta)
            storage_path = str(asset.get("storage_path") or meta.get("storage_path") or "").strip()
            if storage_path:
                for base in _pep_output_base_candidates_from_path(Path(storage_path)):
                    _add_output_base(base, source_kind="cached_usage_path", job_id=job_id, metadata=meta)

    seen: set[str] = set()
    for candidate in candidates:
        direct_path = str(candidate.get("tra_path") or "").strip()
        possible_paths = [Path(direct_path)] if direct_path else _pep_tra_candidates_from_output_base(Path(candidate.get("output_base") or ""))
        for path in possible_paths:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            if path.exists() and path.is_file():
                return {
                    "path": str(path.resolve()),
                    "dataframe": _robust_read_csv(path),
                    "source_job_id": candidate.get("source_job_id") or source_job_id,
                    "source_kind": candidate.get("source_kind") or "pep_analysis",
                    "output_base": str(candidate.get("output_base") or path.parent.parent),
                }

    raise ValidationError(
        message="未找到项目中可用于 MAIT/NKT 的 PEP 共享分析 TRA.csv，请先运行 PEP 共享分析并包含 TRA 链，或手动选择 TRA CSV。",
        details={"source_job_id": source_job_id, "project_id": project_id},
    )


def _request_registered_assets(data: Dict[str, Any], *profile_keys: str) -> Dict[str, Any]:
    """Resolve Script Hub PEP/Profile inputs through one project-first policy."""
    project_id = str(data.get("project_id") or "").strip()
    if project_id:
        project_assets = _collect_project_script_hub_assets(project_id)
        profile_paths = project_assets.get("profile_paths") or []
        return {
            **project_assets,
            "profile_path": project_assets.get("profile_path") or (profile_paths[0] if profile_paths else ""),
        }

    raw_paths = data.get("pep_paths") if isinstance(data.get("pep_paths"), list) else []
    pep_paths = [str(item).strip() for item in raw_paths if str(item or "").strip()]
    base_path = str(data.get("base_path") or data.get("pep_data_path") or data.get("pep_data_dir") or "").strip()
    if base_path and base_path not in pep_paths:
        pep_paths.insert(0, base_path)

    profile_path = ""
    for key in profile_keys:
        value = str(data.get(key) or "").strip()
        if value:
            profile_path = value
            break
    return {
        "pep_paths": pep_paths,
        "profile_path": profile_path,
        "profile_paths": [profile_path] if profile_path else [],
        "invalid_profile_paths": [],
        "transcriptome_path": "",
        "transcriptome_paths": [],
        "invalid_transcriptome_paths": [],
    }


def _profile_path_from_request(data: Dict[str, Any], *keys: str) -> Optional[str]:
    value = _request_registered_assets(data, *keys)["profile_path"] or ""
    return str(PathAccessService.validate_read_path(value)) if value else None


def _transcriptome_path_from_request(data: Dict[str, Any], *keys: str) -> Optional[str]:
    project_id = str(data.get("project_id") or "").strip()
    if project_id:
        value = _collect_project_script_hub_assets(project_id).get("transcriptome_path") or ""
        if value:
            return str(PathAccessService.validate_read_path(value))
    for key in keys:
        value = str(data.get(key) or "").strip()
        if value:
            return str(PathAccessService.validate_read_path(value))
    return None


def _pep_paths_from_request(data: Dict[str, Any]) -> List[str]:
    return [str(PathAccessService.validate_read_path(path)) for path in _request_registered_assets(data)["pep_paths"]]


def _selected_samples_from_request(data: Dict[str, Any]) -> List[str]:
    raw = data.get("selected_samples")
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item or "").strip()]


def _selected_group_values_from_request(data: Dict[str, Any]) -> Dict[str, List[str]]:
    raw = data.get("selected_group_values")
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, List[str]] = {}
    for field, values in raw.items():
        if not isinstance(values, list):
            continue
        clean_values = [str(item).strip() for item in values if str(item or "").strip()]
        if clean_values:
            result[str(field).strip()] = clean_values
    return result


def _selected_samples_by_group_from_request(data: Dict[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    raw = data.get("selected_samples_by_group")
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, Dict[str, List[str]]] = {}
    for field, groups in raw.items():
        if not isinstance(groups, dict):
            continue
        field_key = str(field).strip()
        if not field_key:
            continue
        for group_value, samples in groups.items():
            if not isinstance(samples, list):
                continue
            group_key = str(group_value).strip()
            clean_samples = [str(item).strip() for item in samples if str(item or "").strip()]
            if group_key:
                result.setdefault(field_key, {})[group_key] = clean_samples
    return result


def _validate_selected_samples_against_group_values(data: Dict[str, Any]) -> None:
    selected_samples = _selected_samples_from_request(data)
    selected_group_values = _selected_group_values_from_request(data)
    selected_samples_by_group = _selected_samples_by_group_from_request(data)
    if not selected_group_values:
        return
    profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")
    if not profile_path:
        raise ValidationError(message="profile_path is required for group value sample validation", details={"field": "profile_path"})
    df = _robust_read_csv(Path(profile_path))
    sample_col = _detect_profile_sample_column(df.columns.tolist())
    if not sample_col:
        raise ValidationError(message="Profile sample column not found", details={"available_columns": df.columns.tolist()})
    valid_samples: set[str] = set()
    missing_fields = [field for field in selected_group_values if field not in df.columns]
    if missing_fields:
        raise ValidationError(message="Selected group field not found in Profile", details={"missing_fields": missing_fields, "available_columns": df.columns.tolist()})
    for field, values in selected_group_values.items():
        allowed = {str(item).strip() for item in values if str(item).strip()}
        field_df = df[[sample_col, field]].dropna(subset=[sample_col, field]).copy()
        field_df[sample_col] = field_df[sample_col].astype(str).str.strip()
        field_df[field] = field_df[field].astype(str).str.strip()
        valid_samples.update(field_df[field_df[field].isin(allowed)][sample_col].tolist())
        grouped_selected = selected_samples_by_group.get(field, {})
        invalid_group_values = [group_value for group_value in grouped_selected if group_value not in allowed]
        if invalid_group_values:
            raise ValidationError(
                message="Selected sample groups do not match selected group values",
                details={
                    "field": field,
                    "invalid_group_values": invalid_group_values[:30],
                    "selected_group_values": selected_group_values,
                },
            )
        for group_value, group_samples in grouped_selected.items():
            group_valid_samples = set(field_df[field_df[field] == group_value][sample_col].tolist())
            invalid_group_samples = [sample for sample in group_samples if sample not in group_valid_samples]
            if invalid_group_samples:
                raise ValidationError(
                    message="Selected samples do not belong to the requested group",
                    details={
                        "field": field,
                        "group_value": group_value,
                        "invalid_samples": invalid_group_samples[:30],
                        "valid_sample_examples": sorted(group_valid_samples)[:30],
                    },
                )
    if selected_samples:
        invalid_samples = [sample for sample in selected_samples if sample not in valid_samples]
        if invalid_samples:
            raise ValidationError(
                message="Selected samples do not match selected group values",
                details={
                    "invalid_samples": invalid_samples[:30],
                    "selected_group_values": selected_group_values,
                    "valid_sample_examples": sorted(valid_samples)[:30],
                },
            )


def _detect_profile_sample_column(columns: List[str]) -> str:
    lower_map = {str(col).strip().lower(): str(col) for col in columns}
    for preferred in ("sample", "sample_id", "sample_name", "id"):
        if preferred in lower_map:
            return lower_map[preferred]
    return ""


def _pep_cache_manifests_for_project(project_id: str) -> List[Dict[str, Any]]:
    registry_path = _resolve_results_root() / _RESULT_DIR / "cache_registry.json"
    manifests: List[Dict[str, Any]] = []
    try:
        if not registry_path.exists():
            return manifests
        loaded = json.loads(registry_path.read_text(encoding="utf-8"))
        entries = loaded.get("entries") if isinstance(loaded, dict) else loaded
        if not isinstance(entries, list):
            return manifests
        project_key = str(project_id or "").strip()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_project = str(entry.get("project_id") or "").strip()
            if entry_project and entry_project != project_key:
                continue
            manifest_path = str(entry.get("manifest_path") or "").strip()
            if not manifest_path:
                output_base = str(entry.get("output_base") or "").strip()
                manifest_path = str(Path(output_base) / "cache_manifest.json") if output_base else ""
            path = Path(manifest_path)
            if path.exists() and path.is_file():
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(manifest, dict):
                    manifests.append(manifest)
    except Exception:
        logger.warning("Failed to read PEP cache manifests from registry", exc_info=True)
    return manifests


def _primary_pep_path_from_request(data: Dict[str, Any], *keys: str) -> str:
    pep_paths = _pep_paths_from_request(data)
    if str(data.get("project_id") or "").strip():
        return pep_paths[0] if pep_paths else ""
    for key in keys:
        value = str(data.get(key) or "").strip()
        if value and value not in pep_paths:
            return str(PathAccessService.validate_read_path(value))
    return str(PathAccessService.validate_read_path(pep_paths[0])) if pep_paths else ""


def _analysis_input_descriptor(path_value: str, asset_type: str) -> Dict[str, Any]:
    path = Path(str(path_value or "").strip())
    descriptor: Dict[str, Any] = {
        "asset_type": asset_type,
        "path": str(path_value or "").strip(),
        "exists": path.exists(),
    }
    try:
        resolved = path.resolve()
        descriptor["path"] = str(resolved)
        stat = resolved.stat()
        descriptor["mtime"] = int(stat.st_mtime)
        descriptor["size"] = int(stat.st_size) if resolved.is_file() else 0
        descriptor["kind"] = "file" if resolved.is_file() else "directory"
    except OSError:
        descriptor["mtime"] = 0
        descriptor["size"] = 0
        descriptor["kind"] = ""
    return descriptor


def _analysis_external_input_descriptor(item: Dict[str, Any]) -> Dict[str, Any]:
    """Build a stable descriptor for non-filesystem inputs such as source jobs."""
    descriptor = {
        "asset_type": str(item.get("asset_type") or "input").strip(),
    }
    for key in sorted(item.keys()):
        if key in {"asset_type", "path"}:
            continue
        value = item.get(key)
        if value is not None:
            descriptor[key] = str(value).strip()
    return descriptor


def _build_script_cache_context(
    *,
    project_id: Optional[str],
    module_name: str,
    input_paths: List[Dict[str, str]],
    config_json: Dict[str, Any],
) -> Dict[str, Any]:
    project_id = str(project_id or "").strip()
    if not project_id:
        return {"project_id": "", "analysis_signature": "", "input_assets": [], "config_json": config_json}
    input_assets = []
    for item in input_paths:
        path_value = str(item.get("path") or "").strip()
        if path_value:
            input_assets.append(_analysis_input_descriptor(path_value, item.get("asset_type", "input")))
        elif any(key for key in item.keys() if key not in {"asset_type", "path"}):
            input_assets.append(_analysis_external_input_descriptor(item))
    input_assets.sort(key=lambda item: (item.get("asset_type", ""), item.get("path", "")))
    try:
        from flask_app.services.mongo_service import build_analysis_signature
        analysis_signature = build_analysis_signature(
            project_id=project_id,
            analysis_type=module_name,
            input_assets=input_assets,
            config_json=config_json,
        )
    except Exception:
        logger.warning("Failed to build analysis signature for %s", module_name, exc_info=True)
        analysis_signature = ""
    return {
        "project_id": project_id,
        "analysis_signature": analysis_signature,
        "input_assets": input_assets,
        "config_json": config_json,
    }


def _force_rerun_requested(data: Dict[str, Any]) -> bool:
    return str(data.get("force_rerun") or "").strip().lower() in {"1", "true", "yes", "on"}


def _cache_context_from_script_request(data: Dict[str, Any], module_name: str) -> Dict[str, Any]:
    """Mirror run-endpoint cache inputs without creating a task."""
    project_id = str(data.get("project_id") or "").strip() or None

    if module_name == "db-alignment":
        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path")
        profile_path = _profile_path_from_request(data, "profile_path") or ""
        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else {}
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [base_path])]
                + ([{"asset_type": "profile", "path": profile_path}] if profile_path else [])
            ),
            config_json={
                "field_mapping": {
                    "cdr3_column": str(field_mapping.get("cdr3_column") or "").strip(),
                    "copy_column": str(field_mapping.get("copy_column") or "").strip(),
                },
                "categories": [str(item).strip() for item in (data.get("categories") or []) if str(item).strip()],
                "contained_pathology": _as_bool(data.get("contained_pathology"), False),
                "pathology_values": [str(item).strip() for item in (data.get("pathology_values") or []) if str(item).strip()],
                "selected_samples": _selected_samples_from_request(data),
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
            },
        )

    if module_name in {"boxplot", "profile", "umap"}:
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        config_json = {
            "param_begin": str(data.get("param_begin") or "").strip(),
            "param_over": str(data.get("param_over") or "").strip(),
            "pvalue_threshold": float(data.get("pvalue_threshold") or 0.05),
            "selected_samples": _selected_samples_from_request(data),
            "selected_group_values": _selected_group_values_from_request(data),
            "selected_samples_by_group": _selected_samples_by_group_from_request(data),
        }
        if module_name == "profile":
            config_json.update({
                "grouping_begin": str(data.get("grouping_begin") or "").strip(),
                "grouping_over": str(data.get("grouping_over") or "").strip(),
                "grouptype_fields": data.get("grouptype_fields") if isinstance(data.get("grouptype_fields"), list) else [],
                "group_order": str(data.get("group_order") or "").strip() or None,
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
            })
        elif module_name == "boxplot":
            config_json.update({
                "classification_begin": str(data.get("classification_begin") or "").strip(),
                "classification_over": str(data.get("classification_over") or "").strip(),
                "grouptype_fields": data.get("grouptype_fields") if isinstance(data.get("grouptype_fields"), list) else [],
                "group_order": str(data.get("group_order") or "").strip() or None,
            })
        else:
            config_json.update({
                "classification_begin": str(data.get("classification_begin") or "").strip(),
                "classification_over": str(data.get("classification_over") or "").strip(),
                "n_neighbors": int(data.get("n_neighbors") or 6),
                "min_dist": float(data.get("min_dist") or 0.01),
            })
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json=config_json,
        )

    if module_name == "topclone":
        pep_paths = _pep_paths_from_request(data)
        pep_data_path = _primary_pep_path_from_request(data, "pep_data_path", "base_path")
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_path])]
                + ([{"asset_type": "profile", "path": datapoint_path}] if datapoint_path else [])
            ),
            config_json={
                "mode": str(data.get("mode") or "trace").strip(),
                "top_n": int(data.get("top_n") or 10),
                "group_field": str(data.get("group_field") or "").strip() or None,
                "group_order": str(data.get("group_order") or "").strip() or None,
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples": _selected_samples_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
                "pvalue_threshold": float(data.get("pvalue_threshold") or 0.05),
            },
        )

    if module_name in {"pep-analysis", "pgen-analysis"}:
        pep_paths = _pep_paths_from_request(data)
        pep_key = "pep_data_dir" if module_name == "pep-analysis" else "pep_data_dir"
        pep_data_dir = _primary_pep_path_from_request(data, pep_key, "base_path", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        if module_name == "pep-analysis":
            optional_steps_raw = data.get("optional_steps") if isinstance(data.get("optional_steps"), list) else None
            optional_steps = {int(step) for step in optional_steps_raw if str(step).isdigit()} if optional_steps_raw is not None else None
            optional_steps = {step for step in optional_steps if step in {5, 6, 7, 8}} if optional_steps is not None else None
            config_json = {
                "selected_chains": data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else [],
                "group_fields": data.get("group_fields") if isinstance(data.get("group_fields"), list) else [],
                "group_order": str(data.get("group_order") or "").strip() or None,
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples": _selected_samples_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
                "pvalue_threshold": float(data.get("pvalue_threshold") or 0.05),
                "min_sample_threshold": int(data.get("min_sample_threshold") or 3),
                "optional_steps": sorted(optional_steps) if optional_steps is not None else None,
            }
        else:
            config_json = {
                "selected_chains": data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else [],
                "sample_col": str(data.get("sample_col") or "sample").strip() or "sample",
                "species": str(data.get("species") or "human").strip() or "human",
                "distribution_category_col": str(data.get("distribution_category_col") or "").strip(),
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples": _selected_samples_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
            }
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_dir])]
                + ([{"asset_type": "profile", "path": profile_path}] if profile_path else [])
            ),
            config_json=config_json,
        )

    if module_name == "volcano":
        input_mode = str(data.get("input_mode") or "usage").strip().lower()
        if input_mode == "expression":
            expression_path = _transcriptome_path_from_request(
                data,
                "expression_path",
                "transcriptome_path",
                "profile_path",
                "datapoint_path",
            ) or ""
            return _build_script_cache_context(
                project_id=project_id,
                module_name=module_name,
                input_paths=[{"asset_type": "transcriptome", "path": expression_path}],
                config_json={
                    "input_mode": input_mode,
                    "group_prefix": str(data.get("group_prefix") or "tpm_").strip(),
                    "comparisons": _parse_group_comparisons(data.get("comparisons")),
                    "pvalue_threshold": float(data.get("pvalue_threshold") or 0.05),
                    "logfc_cutoff": float(data.get("logfc_cutoff") or 1.0),
                },
            )
        data_dir = str(data.get("data_dir") or "").strip() or _resolve_project_cached_usage_path(data, preferred="volcano")
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "cached_usage", "path": data_dir}],
            config_json={"pvalue_threshold": float(data.get("pvalue_threshold") or 0.05)},
        )

    if module_name == "go-kegg-enrichment":
        expression_path = _transcriptome_path_from_request(
            data,
            "expression_path",
            "transcriptome_path",
            "profile_path",
            "datapoint_path",
        ) or ""
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "transcriptome", "path": expression_path}],
            config_json={
                "group_prefix": str(data.get("group_prefix") or "tpm_").strip(),
                "comparisons": _parse_group_comparisons(data.get("comparisons")),
                "pvalue_threshold": float(data.get("pvalue_threshold") or 0.05),
                "logfc_cutoff": float(data.get("logfc_cutoff") or 1.0),
                "enrich_pvalue_cutoff": float(data.get("enrich_pvalue_cutoff") or 0.05),
                "p_adjust_method": str(data.get("p_adjust_method") or "none").strip(),
                "show_category": int(data.get("show_category") or 20),
                "simplify_go": _as_bool(data.get("simplify_go"), True),
                "do_gsea": _as_bool(data.get("do_gsea"), True),
            },
        )

    if module_name == "umapin":
        data_path = str(data.get("data_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "cached_usage", "path": data_path}],
            config_json={
                "param_begin": str(data.get("param_begin") or "").strip(),
                "param_over": str(data.get("param_over") or "").strip(),
                "category_col": str(data.get("category_col") or "Category").strip(),
                "n_neighbors": int(data.get("n_neighbors") or 6),
                "min_dist": float(data.get("min_dist") or 0.01),
                "do_fdr": bool(data.get("do_fdr") or False),
            },
        )

    if module_name == "ml-analysis":
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        mode = str(data.get("mode") or "profile").strip().lower().replace("-", "_").replace("+", "_")
        if mode in {"vj", "vj_usage", "usage"}:
            mode = "vj"
        elif mode in {"profile_vj", "profile_usage", "profile_vj_usage"}:
            mode = "profile_vj"
        else:
            mode = "profile"
        usage_path = str(data.get("usage_path") or "").strip()
        if mode in {"vj", "profile_vj"}:
            usage_path = usage_path or _resolve_project_cached_usage_path(data, preferred="umapin")
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "profile", "path": profile_path},
                *([{"asset_type": "cached_usage", "path": usage_path}] if usage_path else []),
            ],
            config_json={
                "mode": mode,
                "label_col": str(data.get("label_col") or "").strip(),
                "sample_col": str(data.get("sample_col") or "Sample").strip() or "Sample",
                "param_begin": str(data.get("param_begin") or "").strip(),
                "param_over": str(data.get("param_over") or "").strip(),
                "filter_col": str(data.get("filter_col") or "").strip(),
                "filter_value": str(data.get("filter_value") or "").strip(),
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples": _selected_samples_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
                "feature_cols": _list_payload(data.get("feature_cols")) if mode != "vj" else [],
                "usage_feature_cols": _list_payload(data.get("usage_feature_cols")),
                "custom_threshold": float(data.get("custom_threshold") or 0.003),
                "cv_splits": int(data.get("cv_splits") or 3),
                "roc_cv_splits": int(data.get("roc_cv_splits") or 7),
            },
        )

    if module_name == "mait-nkt":
        tra_source = str(data.get("tra_source") or "upload").strip()
        tra_path = str(data.get("tra_path") or "").strip()
        source_job_id = str(data.get("source_job_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path") or ""
        resolved_tra_path = tra_path
        resolved_source_job_id = source_job_id
        if tra_source == "pep_analysis" and tra_path and Path(tra_path).exists() and Path(tra_path).is_file():
            resolved_tra_path = str(PathAccessService.validate_read_path(tra_path))
        elif tra_source == "pep_analysis":
            resolved = _resolve_pep_analysis_tra_source(data)
            resolved_tra_path = resolved["path"]
            resolved_source_job_id = str(resolved.get("source_job_id") or source_job_id)
        return _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "tra", "path": resolved_tra_path} if tra_source == "upload" else {"asset_type": "pep_analysis_tra", "path": resolved_tra_path, "source_job_id": resolved_source_job_id},
                {"asset_type": "profile", "path": profile_path},
            ],
            config_json={
                "group_field": str(data.get("group_field") or "").strip(),
                "group_order": str(data.get("group_order") or "").strip() or None,
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples": _selected_samples_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
                "tra_source": tra_source,
            },
        )

    raise ValidationError(message="Unsupported script hub module", details={"module": module_name})


def _result_relative_path_from_url(job_id: str, url: str) -> str:
    marker = f"/api/script-hub/results/{job_id}/"
    if marker not in str(url or ""):
        return ""
    return str(url).split(marker, 1)[1].strip("/")


def _stored_script_result_available(doc: Dict[str, Any]) -> bool:
    output_base = Path(str(doc.get("output_base") or ""))
    if not output_base.exists() or not output_base.is_dir():
        return False
    job_id = str(doc.get("job_id") or "")
    for url_key in ("viewer_url", "zip_url"):
        rel = _result_relative_path_from_url(job_id, str(doc.get(url_key) or ""))
        if rel and not (output_base / Path(*rel.split("/"))).exists():
            return False
    return True


def _mongo_result_to_script_result(doc: Dict[str, Any], module_name: str) -> Dict[str, Any]:
    metadata = doc.get("metadata_json") if isinstance(doc.get("metadata_json"), dict) else {}
    result = {
        "module": module_name,
        "job_id": doc.get("job_id", ""),
        "output_base": doc.get("output_base", ""),
        "viewer_url": doc.get("viewer_url", ""),
        "zip_url": doc.get("zip_url", ""),
        "metadata_url": metadata.get("metadata_url", ""),
        "metadata": metadata.get("metadata", metadata),
        "analysis_signature": doc.get("analysis_signature", ""),
        "result_id": str(doc.get("_id") or ""),
        "reused_result": True,
    }
    for key, value in metadata.items():
        if key.endswith("_urls") or key in {"png_urls", "csv_urls", "selected_chains", "sample_count", "profile_path"}:
            result.setdefault(key, value)
    return _sanitize_nan(result)


def _try_find_script_task_result(job_id: str) -> Optional[Dict[str, Any]]:
    job_id = str(job_id or "").strip()
    if not job_id:
        return None

    task = _get_task_state(job_id)
    if task:
        return {"job_id": job_id, "task": task, "result": task.get("result") if isinstance(task.get("result"), dict) else task}

    try:
        job = get_script_hub_job_service().get_job(job_id)
    except Exception:
        job = None
    if job:
        return {"job_id": job_id, "task": job, "result": job.get("result") if isinstance(job.get("result"), dict) else job}

    try:
        from flask_app.services.mongo_service import results_col
        doc = results_col().find_one({"job_id": job_id, "analysis_type": "pep-analysis", "status": "completed"})
        if doc:
            return {"job_id": job_id, "task": doc, "result": _mongo_result_to_script_result(doc, "pep-analysis")}
    except Exception:
        logger.warning("Failed to query PEP result by job id %s", job_id, exc_info=True)

    try:
        from flask_app.models.database import ProjectAsset
        asset = ProjectAsset.query.filter(ProjectAsset.asset_type == "processed_result").all()
        for row in asset:
            meta = getattr(row, "metadata_json", None) or {}
            if str(meta.get("analysis_type") or "").strip() != "pep-analysis":
                continue
            if str(meta.get("job_id") or "").strip() != job_id:
                continue
            return {
                "job_id": job_id,
                "task": meta,
                "result": {
                    "module": "pep-analysis",
                    "job_id": job_id,
                    "output_base": meta.get("output_base") or getattr(row, "storage_path", "") or "",
                    "metadata": meta.get("metadata") if isinstance(meta.get("metadata"), dict) else meta,
                },
            }
    except Exception:
        logger.warning("Failed to query SQL PEP result asset by job id %s", job_id, exc_info=True)

    return None


def _find_reusable_script_result(cache_context: Dict[str, Any], module_name: str) -> Optional[Dict[str, Any]]:
    project_id = cache_context.get("project_id") or ""
    signature = cache_context.get("analysis_signature") or ""
    if not project_id or not signature:
        return None
    try:
        from flask_app.services.mongo_service import find_result_by_signature
        doc = find_result_by_signature(project_id, module_name, signature)
    except Exception:
        logger.warning("Failed to query cached result for %s", module_name, exc_info=True)
        return None
    if not doc or not _stored_script_result_available(doc):
        return None
    return _mongo_result_to_script_result(doc, module_name)


def _try_reuse_script_result(cache_context: Dict[str, Any], module_name: str) -> Optional[Dict[str, Any]]:
    project_id = cache_context.get("project_id") or ""
    signature = cache_context.get("analysis_signature") or ""
    if not project_id or not signature:
        return None
    result = _find_reusable_script_result(cache_context, module_name)
    if not result:
        return None
    task_id = f"script_task_{uuid.uuid4().hex[:12]}"
    history = [_history_entry(100.0, "Completed", "Reused existing project analysis result", {
        "phase": "completed",
        "module": module_name,
        "reused_result": True,
    })]
    _set_task_state(
        task_id,
        status="completed",
        progress=100.0,
        stage="Completed",
        detail="Reused existing project analysis result",
        meta={"phase": "completed", "module": module_name, "reused_result": True},
        result=result,
        history=history,
        project_id=project_id,
        analysis_signature=signature,
        input_assets=cache_context.get("input_assets") or [],
        config_json=cache_context.get("config_json") or {},
    )
    return {
        "success": True,
        "task_id": task_id,
        "job_id": task_id,
        "status_url": f"/api/script-hub/task/{task_id}",
        "reused_result": True,
        "analysis_signature": signature,
        "result_id": result.get("result_id", ""),
        "result": result,
    }


def _persist_script_result(
    *,
    project_id: str,
    module_name: str,
    result: Dict[str, Any],
    analysis_signature: str,
    input_assets: List[Dict[str, Any]],
    config_json: Dict[str, Any],
    app_context_app: Optional[Any] = None,
) -> str:
    if not project_id or not analysis_signature:
        return ""

    def _save() -> str:
        result_metadata = {
            **(result.get("metadata") if isinstance(result.get("metadata"), dict) else {}),
            "analysis_signature": analysis_signature,
            "metadata_url": result.get("metadata_url", ""),
            "viewer_url": result.get("viewer_url", ""),
            "zip_url": result.get("zip_url", ""),
            "output_base": result.get("output_base", ""),
        }
        result_metadata = _sanitize_nan(result_metadata)
        files = []
        for key in ("viewer_url", "zip_url", "metadata_url"):
            if result.get(key):
                files.append({"kind": key, "url": result.get(key)})
        for key, value in result.items():
            if key.endswith("_urls") and isinstance(value, list):
                files.extend({"kind": key, "url": url} for url in value if url)

        from flask_app.services.mongo_service import save_result
        result_id = save_result(
            project_id=project_id,
            analysis_type=module_name,
            job_id=str(result.get("job_id") or ""),
            files=files,
            metadata_json={
                **result_metadata,
                "metadata": _sanitize_nan(result.get("metadata") if isinstance(result.get("metadata"), dict) else {}),
                **_sanitize_nan({key: value for key, value in result.items() if key.endswith("_urls") or key in {"png_urls", "csv_urls"}}),
            },
            analysis_signature=analysis_signature,
            input_assets=input_assets,
            config_json=_sanitize_nan(config_json),
            viewer_url=str(result.get("viewer_url") or ""),
            zip_url=str(result.get("zip_url") or ""),
            output_base=str(result.get("output_base") or ""),
            status="completed",
        )

        try:
            from flask_app.models.database import Project
            from flask_app.services.project_asset_service import get_project_asset_service
            project = Project.query.filter(Project.id == project_id).first()
            if project is not None:
                metadata_for_asset = {
                    **result_metadata,
                    "result_id": result_id,
                    "analysis_signature": analysis_signature,
                    "input_assets": input_assets,
                    "config_json": config_json,
                }
                get_project_asset_service(Path(current_app.root_path) / "data" / "projects").register_analysis_result(
                    project,
                    analysis_type=module_name,
                    job_id=str(result.get("job_id") or ""),
                    output_base=str(result.get("output_base") or ""),
                    report_path=str(result.get("report_path") or ""),
                    report_url=str(result.get("viewer_url") or ""),
                    metadata_url=str(result.get("metadata_url") or ""),
                    zip_url=str(result.get("zip_url") or ""),
                    viewer_url=str(result.get("viewer_url") or ""),
                    metadata=metadata_for_asset,
                )
        except Exception:
            logger.warning("Failed to sync script result asset for project %s", project_id, exc_info=True)
        return result_id

    if app_context_app is not None:
        with app_context_app.app_context():
            return _save()
    return _save()


def _complete_script_task(
    task_id: str,
    *,
    module_name: str,
    detail: str,
    result: Dict[str, Any],
    history: List[Dict[str, Any]],
    app_context_app: Optional[Any] = None,
    stage: str = "Completed",
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    task_context = _get_task_state(task_id) or {}
    if task_context.get("status") == "cancelled" or _script_task_cancel_requested(task_id):
        _mark_script_task_cancelled(task_id)
        return
    project_id = str(task_context.get("project_id") or "").strip()
    analysis_signature = str(task_context.get("analysis_signature") or "").strip()
    input_assets = task_context.get("input_assets") if isinstance(task_context.get("input_assets"), list) else []
    config_json = task_context.get("config_json") if isinstance(task_context.get("config_json"), dict) else {}
    if analysis_signature:
        result["analysis_signature"] = analysis_signature
    result_id = _persist_script_result(
        project_id=project_id,
        module_name=module_name,
        result=result,
        analysis_signature=analysis_signature,
        input_assets=input_assets,
        config_json=config_json,
        app_context_app=app_context_app,
    )
    if result_id:
        result["result_id"] = result_id
    completed_meta = {"phase": "completed", "module": module_name, **(meta or {})}
    _set_task_state(
        task_id,
        status="completed",
        progress=100.0,
        stage=stage,
        detail=detail,
        meta=completed_meta,
        result=result,
        history=history[-80:],
    )


def _build_and_save_viewer(output_base, result, metadata, *, title, subtitle, dl_extras=None):
    import json as _json
    result_items = metadata.get("result_items") if isinstance(metadata.get("result_items"), list) else []
    data_mode_by_name = {}
    for item in result_items:
        if not isinstance(item, dict):
            continue
        name = Path(str(item.get("path") or item.get("title") or "")).name
        data_mode = str(item.get("data_mode") or "").strip()
        if name and data_mode:
            data_mode_by_name[name] = data_mode
    img_items = []
    for u in result.get("png_urls", []):
        fname = u.rsplit("/", 1)[-1] if "/" in u else u
        cat = data_mode_by_name.get(fname) or (fname.rsplit(".", 1)[0].rsplit("_", 1)[0] if "_" in fname else "plot")
        img_items.append({"src": u, "title": fname, "category": cat, "sig": False})
    dl_sections = []
    if dl_extras:
        for key, fallback_name, label in dl_extras:
            links = []
            urls = result.get(key, [])
            if isinstance(urls, str) and urls:
                urls = [urls]
            if isinstance(urls, list):
                for uu in urls:
                    name = fallback_name or (uu.rsplit("/", 1)[-1] if "/" in uu else uu)
                    links.append({"url": uu, "name": name})
            if links:
                dl_sections.append({"label": label, "links": links})
    viewer_path = output_base / "viewer.html"
    _write_unified_viewer(
        viewer_path=viewer_path, title=title, subtitle=subtitle,
        image_groups=[{"label": "Images", "items": img_items}],
        download_sections=dl_sections,
        stats=[{"label": "Images", "value": str(len(img_items))},
               {"label": "CSV Files", "value": str(sum(len(ds["links"]) for ds in dl_sections))}],
        metadata=metadata)
    job_id_str = str(output_base.name)
    result["viewer_url"] = f"/api/script-hub/results/{job_id_str}/viewer.html"
    mpath = output_base / "metadata.json"
    mpath.write_text(_json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    result["metadata_url"] = f"/api/script-hub/results/{job_id_str}/metadata.json"


def _build_topclone_viewer(output_base: Path, result: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    import html as _html
    import json as _json

    output_base = Path(output_base)
    chain_pattern = re.compile(r"top(?P<topn>\d+)(?P<chain>TRA|TRB|TRG|TRD|IGH|IGK|IGL)", re.IGNORECASE)
    cards: List[Dict[str, str]] = []
    chains_seen: List[str] = []
    top_seen: List[str] = []
    classes_seen: List[str] = []

    for url in result.get("png_urls") or []:
        rel = _result_relative_path_from_url(output_base.name, str(url)) or str(url)
        parts = [part for part in rel.replace("\\", "/").split("/") if part]
        filename = parts[-1] if parts else str(url).rsplit("/", 1)[-1]
        stem = filename.rsplit(".", 1)[0]
        match = chain_pattern.search(stem)
        chain = match.group("chain").upper() if match else "ALL"
        top_n = match.group("topn") if match else "all"
        class_col = parts[-2] if len(parts) >= 2 else (metadata.get("group_field") or "plot")
        if class_col.lower() in {"ungrouped", "boxplot", "boxplots"}:
            class_col = metadata.get("group_field") or class_col
        title = stem
        cards.append({
            "src": str(url),
            "title": title,
            "chain": chain,
            "top_n": top_n,
            "class_col": str(class_col),
        })
        if chain not in chains_seen:
            chains_seen.append(chain)
        if top_n not in top_seen:
            top_seen.append(top_n)
        if str(class_col) not in classes_seen:
            classes_seen.append(str(class_col))

    top_seen.sort(key=lambda value: int(value) if str(value).isdigit() else 999999)
    default_chain = (metadata.get("chains") or chains_seen or ["ALL"])[0]
    default_top = "10" if "10" in top_seen else (top_seen[0] if top_seen else "all")
    default_class = classes_seen[0] if classes_seen else ""

    def _options(values: List[str], selected: str) -> str:
        return "".join(
            '<option value="' + _html.escape(str(value)) + '"' + (" selected" if str(value) == str(selected) else "") + ">"
            + _html.escape(str(value)) + "</option>"
            for value in values
        )

    dl_sections = []
    for key, label in (
        ("topclone_csv_url", "TopClone CSV"),
        ("csv_urls", "BoxPlot CSV"),
        ("pvalue_urls", "P-value CSV"),
        ("cdr3_urls", "Top CDR3 CSV"),
        ("zip_url", "ZIP"),
    ):
        urls = result.get(key) or []
        if isinstance(urls, str):
            urls = [urls] if urls else []
        links = []
        for url in urls:
            name = str(url).rsplit("/", 1)[-1] if "/" in str(url) else str(url)
            links.append({"url": str(url), "name": name})
        if links:
            dl_sections.append({"label": label, "links": links})

    downloads_html = ""
    for section in dl_sections:
        links_html = "".join(
            '<a class="download-link" href="' + _html.escape(link["url"]) + '" download>'
            + _html.escape(link["name"]) + "</a>"
            for link in section["links"]
        )
        downloads_html += '<section class="download-section"><h2>' + _html.escape(section["label"]) + '</h2><div class="download-grid">' + links_html + "</div></section>"

    cards_json = _json.dumps(cards, ensure_ascii=False).replace("</", "<\\/")
    chains_json = _json.dumps(chains_seen or [default_chain], ensure_ascii=False)
    tops_json = _json.dumps(top_seen or [default_top], ensure_ascii=False)
    classes_json = _json.dumps(classes_seen or [default_class], ensure_ascii=False)

    viewer_path = output_base / "viewer.html"
    viewer_path.write_text(f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>TopClone Analysis Results</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif; background: #f4f7fa; color: #172033; line-height: 1.55; }}
    .page {{ max-width: 1240px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }}
    .back-link {{ display: inline-flex; color: #11597c; text-decoration: none; font-size: .85rem; margin-bottom: .8rem; }}
    .back-link:hover {{ text-decoration: underline; }}
    .header, .controls, .plot-panel, .download-section {{ background: #fff; border: 1px solid #dee6ed; border-radius: 12px; }}
    .header {{ padding: 1.35rem 1.55rem; margin-bottom: 1rem; }}
    .header h1 {{ font-size: 1.3rem; margin-bottom: .35rem; }}
    .meta {{ color: #5f7082; font-size: .86rem; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: .65rem; margin-top: 1rem; }}
    .stat-item {{ flex: 1 1 130px; min-width: 120px; background: #f7fafc; border: 1px solid #e1e9f0; border-radius: 8px; padding: .7rem .85rem; }}
    .stat-item strong {{ display: block; color: #607287; font-size: .72rem; margin-bottom: .2rem; }}
    .stat-item span {{ font-weight: 700; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: .8rem; align-items: flex-end; padding: .95rem 1.05rem; margin-bottom: 1rem; }}
    .control-group {{ display: flex; flex-direction: column; gap: .28rem; }}
    .control-group label {{ color: #607287; font-size: .72rem; font-weight: 700; text-transform: uppercase; }}
    .control-group select {{ min-width: 150px; border: 1px solid #c4d1dc; border-radius: 8px; background: #fff; padding: .5rem .65rem; font-size: .9rem; }}
    .counter {{ margin-left: auto; color: #607287; font-size: .82rem; }}
    .plot-panel {{ min-height: 340px; overflow: hidden; }}
    .plot-card {{ display: none; }}
    .plot-card.is-active {{ display: block; }}
    .plot-head {{ display: flex; justify-content: space-between; gap: 1rem; align-items: flex-start; border-bottom: 1px solid #edf2f6; background: #fbfdfe; padding: .75rem .9rem; }}
    .plot-head strong {{ display: block; font-size: .88rem; }}
    .plot-head span {{ color: #607287; font-size: .74rem; }}
    .plot-card img {{ display: block; width: 100%; max-height: 660px; object-fit: contain; background: #fafbfc; }}
    .empty {{ padding: 3rem 1rem; text-align: center; color: #7d8fa1; }}
    .download-section {{ padding: 1rem; margin-top: 1rem; }}
    .download-section h2 {{ font-size: .92rem; margin-bottom: .55rem; }}
    .download-grid {{ display: flex; flex-wrap: wrap; gap: .45rem; }}
    .download-link {{ border: 1px solid #c4d1dc; border-radius: 8px; color: #11597c; padding: .42rem .65rem; text-decoration: none; font-size: .82rem; }}
    .download-link:hover {{ background: #eef6fb; }}
    @media (max-width: 640px) {{ .controls {{ align-items: stretch; }} .control-group, .control-group select {{ width: 100%; }} .counter {{ margin-left: 0; }} }}
  </style>
</head>
<body>
<div class="page">
  <a class="back-link" href="javascript:history.back()">&#8592; Back</a>
  <div class="header">
    <h1>TopClone Analysis Results</h1>
    <div class="meta">Mode: {_html.escape(str(metadata.get("mode", "")))} | Chains: {_html.escape(", ".join(metadata.get("chains", [])))}</div>
    <div class="stats">
      <div class="stat-item"><strong>Samples</strong><span>{_html.escape(str(metadata.get("sample_count", "-")))}</span></div>
      <div class="stat-item"><strong>Chains</strong><span>{_html.escape(str(len(metadata.get("chains", []))))}</span></div>
      <div class="stat-item"><strong>Top N</strong><span>{_html.escape(", ".join(str(v) for v in metadata.get("top_clone_values", [])))}</span></div>
      <div class="stat-item"><strong>Plots</strong><span>{_html.escape(str(len(cards)))}</span></div>
    </div>
  </div>
  <div class="controls">
    <div class="control-group"><label for="chainSelect">Chain</label><select id="chainSelect">{_options(chains_seen or [default_chain], str(default_chain))}</select></div>
    <div class="control-group"><label for="topSelect">Top N</label><select id="topSelect">{_options(top_seen or [default_top], str(default_top))}</select></div>
    <div class="control-group"><label for="classSelect">Group field</label><select id="classSelect">{_options(classes_seen or [default_class], str(default_class))}</select></div>
    <span class="counter" id="counter"></span>
  </div>
  <div class="plot-panel" id="plotPanel"><div class="empty">No TopClone plots available.</div></div>
  {downloads_html}
</div>
<script>
(function() {{
  const cards = {cards_json};
  const chains = {chains_json};
  const topNs = {tops_json};
  const classes = {classes_json};
  const chainSelect = document.getElementById('chainSelect');
  const topSelect = document.getElementById('topSelect');
  const classSelect = document.getElementById('classSelect');
  const plotPanel = document.getElementById('plotPanel');
  const counter = document.getElementById('counter');

  function fillOptions(select, values, selected) {{
    const current = selected || select.value;
    select.innerHTML = '';
    values.forEach((value) => {{
      const opt = document.createElement('option');
      opt.value = value;
      opt.textContent = value;
      if (String(value) === String(current)) opt.selected = true;
      select.appendChild(opt);
    }});
    if (!select.value && select.options.length) select.options[0].selected = true;
  }}

  function filtered() {{
    return cards.filter((card) => (
      String(card.chain) === String(chainSelect.value)
      && String(card.top_n) === String(topSelect.value)
      && String(card.class_col) === String(classSelect.value)
    ));
  }}

  function refreshDependentOptions() {{
    const chain = chainSelect.value;
    const validTopNs = topNs.filter((topN) => cards.some((card) => String(card.chain) === String(chain) && String(card.top_n) === String(topN)));
    fillOptions(topSelect, validTopNs.length ? validTopNs : topNs, topSelect.value);
    const topN = topSelect.value;
    const validClasses = classes.filter((cls) => cards.some((card) => String(card.chain) === String(chain) && String(card.top_n) === String(topN) && String(card.class_col) === String(cls)));
    fillOptions(classSelect, validClasses.length ? validClasses : classes, classSelect.value);
  }}

  function render() {{
    refreshDependentOptions();
    const matches = filtered();
    if (!matches.length) {{
      plotPanel.innerHTML = '<div class="empty">No plot for the selected chain and Top N.</div>';
      counter.textContent = '0 plots';
      return;
    }}
    plotPanel.innerHTML = matches.map((card, index) => (
      '<article class="plot-card ' + (index === 0 ? 'is-active' : '') + '">'
      + '<div class="plot-head"><div><strong>' + escapeHtml(card.title) + '</strong><span>' + escapeHtml(card.chain + ' | top' + card.top_n + ' | ' + card.class_col) + '</span></div></div>'
      + '<a href="' + escapeAttr(card.src) + '" target="_blank" rel="noopener"><img src="' + escapeAttr(card.src) + '" alt="' + escapeAttr(card.title) + '"></a>'
      + '</article>'
    )).join('');
    counter.textContent = matches.length + ' plot' + (matches.length === 1 ? '' : 's');
  }}

  function escapeHtml(value) {{
    return String(value || '').replace(/[&<>"']/g, (ch) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
  }}
  function escapeAttr(value) {{ return escapeHtml(value); }}

  chainSelect.addEventListener('change', render);
  topSelect.addEventListener('change', render);
  classSelect.addEventListener('change', render);
  render();
}})();
</script>
</body>
</html>""", encoding="utf-8")
    job_id_str = output_base.name
    result["viewer_url"] = f"/api/script-hub/results/{job_id_str}/viewer.html"
    metadata_path = output_base / "metadata.json"
    metadata_path.write_text(_json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    result["metadata_url"] = f"/api/script-hub/results/{job_id_str}/metadata.json"


def _result_url_exists(output_base: Path, url: str) -> bool:
    if not url:
        return False
    marker = f"/api/script-hub/results/{output_base.name}/"
    if marker not in url:
        return False
    rel = url.split(marker, 1)[1].strip("/")
    if not rel:
        return False
    return (output_base / Path(*rel.split("/"))).exists()


def _result_file_url(output_base: Path, file_path: Path) -> str:
    rel = file_path.relative_to(output_base)
    return f"/api/script-hub/results/{output_base.name}/{rel.as_posix()}"


def _result_url_to_path(output_base: Path, url: str) -> Optional[Path]:
    marker = f"/api/script-hub/results/{output_base.name}/"
    if not url or marker not in str(url):
        return None
    rel = str(url).split(marker, 1)[1].strip("/")
    if not rel:
        return None
    path = output_base / Path(*rel.split("/"))
    return path if path.exists() and path.is_file() else None


def _script_hub_zip_category(file_path: Path) -> Optional[str]:
    suffix = file_path.suffix.lower()
    if file_path.name == "viewer.html":
        return "viewer"
    if suffix == ".png":
        return "figures"
    if suffix in {".csv", ".tsv", ".xlsx", ".xls"}:
        return "tables"
    if suffix in {".txt", ".log"}:
        return "logs"
    if suffix == ".json":
        return "metadata"
    if suffix in {".html"}:
        return "reports"
    return None


def _iter_script_hub_result_files(output_base: Path, result: Dict[str, Any]) -> List[Path]:
    files: List[Path] = []
    seen: set[str] = set()

    def add_path(path: Optional[Path]) -> None:
        if path is None or not path.exists() or not path.is_file():
            return
        if path.suffix.lower() in {".zip", ".pdf", ".svg", ".jpg", ".jpeg", ".webp"}:
            return
        if _script_hub_zip_category(path) is None:
            return
        resolved = str(path.resolve())
        if resolved in seen:
            return
        seen.add(resolved)
        files.append(path)

    for key, value in result.items():
        if not (str(key).endswith("_url") or str(key).endswith("_urls")):
            continue
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, str):
                add_path(_result_url_to_path(output_base, item))

    for file_path in sorted(output_base.rglob("*")):
        add_path(file_path)

    return sorted(files, key=lambda path: path.relative_to(output_base).as_posix())


def _ensure_result_zip(output_base: Path, result: Dict[str, Any], *, zip_name: str) -> str:
    zip_path = output_base / zip_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in _iter_script_hub_result_files(output_base, result):
            if file_path.resolve() == zip_path.resolve():
                continue
            category = _script_hub_zip_category(file_path)
            if not category:
                continue
            arcname = f"{category}/{file_path.relative_to(output_base).as_posix()}"
            zf.write(file_path, arcname)
    return _result_file_url(output_base, zip_path)


def _normalize_script_result(
    result: Dict[str, Any],
    output_base: Path,
    metadata: Dict[str, Any],
    *,
    title: str,
    subtitle: str,
    dl_extras=None,
    zip_name: str = "script_hub_results.zip",
) -> Dict[str, Any]:
    output_base = Path(output_base)
    if not _result_url_exists(output_base, str(result.get("viewer_url") or "")):
        _build_and_save_viewer(
            output_base,
            result,
            metadata or {},
            title=title,
            subtitle=subtitle,
            dl_extras=dl_extras,
        )
    elif metadata and not result.get("metadata_url"):
        metadata_path = output_base / "metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        result["metadata_url"] = _result_file_url(output_base, metadata_path)

    result["zip_url"] = _ensure_result_zip(output_base, result, zip_name=zip_name)
    return result


def _pep_chain_from_result_rel(rel: str) -> str:
    parts = str(rel or "").split("/")
    filename = parts[-1] if parts else ""
    stem = filename.rsplit(".", 1)[0]
    for part in parts:
        normalized = _normalize_chain(part)
        if normalized in _SUPPORTED_CHAINS_WIDE:
            return normalized
    for chain in sorted(_SUPPORTED_CHAINS_WIDE, key=len, reverse=True):
        if stem.upper().startswith(chain) or f"_{chain}_" in stem.upper():
            return chain
    return "ALL" if stem.upper().startswith("ALL") else "Other"


def _pep_usage_type_from_result_rel(rel: str) -> str:
    usage_types = {"0Vusage", "1Vusage", "0Jusage", "1Jusage", "0VJusage", "1VJusage"}
    for part in str(rel or "").split("/"):
        if part in usage_types:
            return part
    return "All"


def _pep_plot_type_from_result_rel(rel: str, section: str) -> str:
    rel_text = str(rel or "")
    filename = rel_text.rsplit("/", 1)[-1]
    if section == "Differential heatmaps":
        return "heatmap"
    if section == "CDR3 classification proportions":
        return "proportion"
    if section == "CDR3 arrangement heatmaps":
        return "arrange_heatmap"
    if section == "Unique CDR3 heatmaps":
        return "summary" if filename.upper().startswith("ALL_") else "unique_cdr3"
    return "plot"


def _pep_section_step(section: str) -> int:
    return {
        "Differential heatmaps": 5,
        "CDR3 classification proportions": 6,
        "CDR3 arrangement heatmaps": 7,
        "Unique CDR3 heatmaps": 8,
    }.get(section, 0)


def _pep_viewer_items(urls: List[str], section: str, job_id: str, created_at: str = "") -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    marker = f"/api/script-hub/results/{job_id}/"
    step = _pep_section_step(section)
    for url in urls:
        if not str(url).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
            continue
        rel = url.split(marker, 1)[1] if marker in url else url.rsplit("/", 1)[-1]
        parts = rel.split("/")
        group_field = parts[0] if len(parts) > 2 else "Summary"
        chain = _pep_chain_from_result_rel(rel)
        usage_type = _pep_usage_type_from_result_rel(rel)
        plot_type = _pep_plot_type_from_result_rel(rel, section)
        filter_dimensions = ["group_field", "chain", "usage_type", "plot_type"]
        title = parts[-1]
        if section == "Differential heatmaps" and len(parts) >= 4:
            title = f"{parts[-3]} / {parts[-2]} / {parts[-1]}"
        elif section == "CDR3 arrangement heatmaps":
            group_field = ""
            usage_type = ""
            plot_type = ""
            filter_dimensions = ["chain"]
            title = f"{chain} / {parts[-1]}"
        elif section == "Unique CDR3 heatmaps":
            title = f"{chain} / {plot_type} / {parts[-1]}"
        image_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"pep_step{step}_{rel}").strip("_")
        data_category = section
        items.append({
            "image_id": image_id,
            "image_path": rel,
            "image_name": parts[-1],
            "analysis_type": "PEP",
            "url": url,
            "kind": "image",
            "section": section,
            "category": section,
            "data_category": data_category,
            "step": str(step),
            "script": PEP_STEP_SCRIPT_LABELS.get(step, ""),
            "chain": chain,
            "group": group_field,
            "group_field": group_field,
            "comparison": "",
            "usage_type": usage_type,
            "plot_type": plot_type,
            "image_type": plot_type,
            "filter_dimensions": filter_dimensions,
            "title": title,
            "label": title,
            "rel": rel,
            "created_at": created_at,
        })
    return items


PEP_STEP_SCRIPT_LABELS = {
    5: "5.Heat_map_Thread.py",
    6: "6.Pep_statistication.py",
    7: "7.CDR3_arrage_heatmap_ver1.0.py",
    8: "8.plot_heatmap.py",
}


def _pep_download_items(urls: List[str], section: str, step: int, job_id: str, kind: str = "csv") -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    marker = f"/api/script-hub/results/{job_id}/"
    for url in urls or []:
        if not isinstance(url, str) or not url.strip():
            continue
        rel = url.split(marker, 1)[1] if marker in url else url.rsplit("/", 1)[-1]
        parts = rel.split("/")
        group_field = parts[0] if len(parts) > 2 else "Summary"
        title = parts[-1] if parts else rel
        items.append({
            "url": url,
            "kind": kind,
            "section": section,
            "category": section,
            "step": str(step),
            "script": PEP_STEP_SCRIPT_LABELS.get(step, "2.Pep_shared.py" if step == 2 else ""),
            "chain": _pep_chain_from_result_rel(rel),
            "group": group_field,
            "group_field": group_field,
            "usage_type": _pep_usage_type_from_result_rel(rel),
            "plot_type": "table" if kind == "csv" else kind,
            "title": title,
            "label": title,
            "rel": rel,
        })
    return items


def _generate_pep_csv_preview_images(output_base: Path, csv_paths: List[str], *, limit: int = 24) -> List[str]:
    previews_dir = output_base / "viewer_previews"
    urls: List[str] = []
    job_id = str(output_base.name)
    seen_names: set[str] = set()

    for raw_path in csv_paths[:limit]:
        path = Path(str(raw_path or ""))
        if not path.exists() or not path.is_file():
            continue
        try:
            df = _robust_read_csv(path, low_memory=False)
        except Exception as exc:
            logger.warning("Failed to create PEP CSV preview for %s: %s", path, exc)
            continue
        if df.empty:
            continue

        indexed = df.copy()
        first_col = indexed.columns[0]
        if not pd.api.types.is_numeric_dtype(indexed[first_col]):
            indexed = indexed.set_index(first_col)

        numeric = indexed.apply(pd.to_numeric, errors="coerce").dropna(axis=0, how="all").dropna(axis=1, how="all")
        if numeric.empty:
            continue
        numeric = numeric.iloc[:60, :40].fillna(0)

        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import seaborn as sns

            rel = path.relative_to(output_base).as_posix() if path.is_relative_to(output_base) else path.name
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", rel).strip("_") or "preview"
            safe_name = safe_name.rsplit(".", 1)[0] + ".png"
            while safe_name in seen_names:
                safe_name = safe_name.rsplit(".", 1)[0] + "_1.png"
            seen_names.add(safe_name)

            previews_dir.mkdir(parents=True, exist_ok=True)
            out_path = previews_dir / safe_name
            width = max(7.0, min(18.0, numeric.shape[1] * 0.42 + 2.8))
            height = max(4.8, min(18.0, numeric.shape[0] * 0.24 + 2.2))
            fig, ax = plt.subplots(figsize=(width, height), dpi=140)
            sns.heatmap(numeric, cmap="viridis", ax=ax, cbar=True)
            ax.set_title(rel, fontsize=9)
            ax.tick_params(axis="x", labelrotation=90, labelsize=6)
            ax.tick_params(axis="y", labelsize=6)
            fig.tight_layout()
            save_publication_png(fig, out_path)
            plt.close(fig)
            urls.append(f"/api/script-hub/results/{job_id}/{out_path.relative_to(output_base).as_posix()}")
        except Exception as exc:
            logger.warning("Failed to render PEP CSV preview for %s: %s", path, exc)
            continue

    return urls


def _write_pep_analysis_viewer(output_base: Path, result: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    import html as _html

    job_id = str(result.get("job_id") or output_base.name)
    created_at = str(metadata.get("generated_at") or metadata.get("created_at") or "")
    image_sections = [
        ("Differential heatmaps", _pep_viewer_items(result.get("heatmap_image_urls") or [], "Differential heatmaps", job_id, created_at)),
        ("CDR3 classification proportions", _pep_viewer_items(result.get("proportion_plot_urls") or [], "CDR3 classification proportions", job_id, created_at)),
        ("CDR3 arrangement heatmaps", _pep_viewer_items(result.get("arrange_heatmap_urls") or [], "CDR3 arrangement heatmaps", job_id, created_at)),
        ("Unique CDR3 heatmaps", _pep_viewer_items(result.get("plot_heatmap_urls") or [], "Unique CDR3 heatmaps", job_id, created_at)),
    ]
    all_images = [item for _, items in image_sections for item in items]
    result["viewer_items"] = all_images
    download_items = (
        _pep_download_items(result.get("shared_matrix_urls") or [], "Shared matrices", 2, job_id)
        + _pep_download_items(result.get("usage_urls") or [], "Usage matrices", 2, job_id)
        + _pep_download_items(result.get("heatmap_csv_urls") or [], "Differential heatmap CSV", 5, job_id)
        + _pep_download_items(result.get("classification_urls") or [], "CDR3 classification CSV", 6, job_id)
        + _pep_download_items(result.get("proportion_urls") or [], "CDR3 proportion CSV", 6, job_id)
        + _pep_download_items([result.get("metadata_url")] if result.get("metadata_url") else [], "Metadata", 0, job_id, "json")
        + _pep_download_items([result.get("zip_url")] if result.get("zip_url") else [], "Archive", 0, job_id, "zip")
    )
    result["download_items"] = download_items
    metadata["viewer_items"] = all_images
    metadata["image_files"] = all_images
    metadata["viewer_filter_schema"] = [
        {"key": "section", "label": "PEP step/category"},
        {"key": "group_field", "label": "Group field"},
        {"key": "chain", "label": "Chain"},
        {"key": "usage_type", "label": "Usage type"},
        {"key": "plot_type", "label": "Image type"},
    ]
    metadata["viewer_filter_modes"] = {
        "CDR3 arrangement heatmaps": ["chain"],
    }
    visible_sections = [(name, items) for name, items in image_sections if items]
    default_section = visible_sections[0][0] if visible_sections else ""

    def _unique_option_values(key: str, section: Optional[str] = None) -> List[str]:
        values = []
        for item in all_images:
            if section and item.get("section") != section:
                continue
            value = str(item.get(key) or "").strip()
            if value and value not in values:
                values.append(value)
        return values

    def _options_html(values: List[str], default: str = "", include_all: bool = True) -> str:
        html = ""
        if include_all:
            html += '<option value="__all__"' + (" selected" if default == "__all__" else "") + ">All</option>"
        for value in values:
            html += (
                '<option value="' + _html.escape(value) + '"'
                + (" selected" if value == default else "")
                + ">" + _html.escape(value) + "</option>"
            )
        return html

    section_values = [name for name, _ in visible_sections]
    default_group = (_unique_option_values("group_field", default_section) or ["__all__"])[0]
    default_chain = (_unique_option_values("chain", default_section) or ["__all__"])[0]
    default_usage = (_unique_option_values("usage_type", default_section) or ["__all__"])[0]
    default_plot = (_unique_option_values("plot_type", default_section) or ["__all__"])[0]
    section_options_html = _options_html(section_values, default_section, include_all=False)
    group_options_html = _options_html(_unique_option_values("group_field"), default_group)
    chain_options_html = _options_html(_unique_option_values("chain"), default_chain)
    usage_options_html = _options_html(_unique_option_values("usage_type"), default_usage)
    plot_options_html = _options_html(_unique_option_values("plot_type"), default_plot)

    def _download_links(key: str) -> str:
        links = result.get(key) or []
        if isinstance(links, str):
            links = [links] if links else []
        if not isinstance(links, list):
            return ""
        marker = f"/api/script-hub/results/{job_id}/"

        def _download_name(url: str) -> str:
            url_text = str(url)
            if marker in url_text:
                return url_text.split(marker, 1)[1]
            return url_text.rsplit("/", 1)[-1]

        return "".join(
            '<a href="' + _html.escape(str(url)) + '" download>' + _html.escape(_download_name(str(url))) + '</a>'
            for url in links
        )

    cards_html = "".join(
            '<article class="plot-card"'
            ' data-section="' + _html.escape(str(item.get("section") or "")) + '"'
            ' data-group-field="' + _html.escape(str(item.get("group_field") or "")) + '"'
            ' data-chain="' + _html.escape(str(item.get("chain") or "")) + '"'
            ' data-usage-type="' + _html.escape(str(item.get("usage_type") or "")) + '"'
            ' data-plot-type="' + _html.escape(str(item.get("plot_type") or "")) + '"'
            ' data-filter-dimensions="' + _html.escape(",".join(item.get("filter_dimensions") or [])) + '">'
            '<a href="' + _html.escape(item["url"]) + '" target="_blank" rel="noopener">'
            '<img src="' + _html.escape(item["url"]) + '" alt="' + _html.escape(item["title"]) + '" loading="lazy"></a>'
            '<div class="plot-meta"><strong>' + _html.escape(item["title"]) + '</strong>'
            '<span>' + _html.escape(
                " / ".join([
                    str(item.get("section") or ""),
                    str(item.get("chain") or ""),
                    *([
                        str(item.get("group_field") or ""),
                        str(item.get("usage_type") or ""),
                    ] if "chain" not in (item.get("filter_dimensions") or []) or len(item.get("filter_dimensions") or []) > 1 else []),
                ]).strip(" / ")
            ) + '</span></div>'
            '</article>'
            for item in all_images
    )

    sections_html = []
    if cards_html:
        sections_html.append(
            '<section class="viewer-section" data-section="pep-images"><div class="section-head"><h2>Filtered images</h2>'
            '<span id="pepVisibleCount">' + str(len(all_images)) + ' images</span></div><div class="plot-grid" id="pepPlotGrid">' + cards_html + '</div>'
            '<div class="empty-note is-hidden" id="pepNoMatches">No images match the selected filters.</div></section>'
        )

    if not sections_html:
        sections_html.append(
            '<section class="viewer-section empty"><h2>No images generated</h2>'
            '<p>Selected optional steps may not have produced heatmaps. Check metadata and CSV outputs below.</p></section>'
        )

    download_sections = [
        ("2.Pep_shared.py / Pep_shared", _download_links("shared_matrix_urls")),
        ("2.Pep_shared.py / usage", _download_links("usage_urls")),
        ("5.Heat_map_Thread.py / heatmap/csv_file", _download_links("heatmap_csv_urls")),
        ("6.Pep_statistication.py / arrage_pep", _download_links("classification_urls")),
        ("6.Pep_statistication.py / prop_pep", _download_links("proportion_urls")),
    ]
    downloads_html = "".join(
        '<details><summary>' + _html.escape(label) + '</summary><div class="download-grid">' + links + '</div></details>'
        for label, links in download_sections if links
    )

    counts = metadata.get("output_counts") if isinstance(metadata.get("output_counts"), dict) else {}
    stats = [
        ("Chains", len(metadata.get("selected_chains") or [])),
        ("Group fields", len(metadata.get("group_fields") or [])),
        ("Images", len(all_images)),
        ("Shared CSV", counts.get("shared_matrix", len(result.get("shared_matrix_urls") or []))),
    ]
    stats_html = "".join(
        '<div class="stat"><span>' + _html.escape(label) + '</span><strong>' + _html.escape(str(value)) + '</strong></div>'
        for label, value in stats
    )

    warnings = metadata.get("optional_step_errors") if isinstance(metadata.get("optional_step_errors"), list) else []
    warning_html = ""
    if warnings:
        warning_html = '<div class="warning"><strong>Optional step warnings</strong><ul>' + "".join(
            '<li>Step ' + _html.escape(str(item.get("step", ""))) + ' / '
            + _html.escape(str(item.get("group_field", ""))) + ': '
            + _html.escape(str(item.get("error", ""))) + '</li>'
            for item in warnings[:20]
        ) + '</ul></div>'

    viewer_path = output_base / "viewer.html"
    viewer_path.write_text("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PEP Sharing Analysis Results</title>
  <style>
    * { box-sizing: border-box; }
    body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, "Microsoft YaHei", sans-serif; background: #f6f8fb; color: #172033; }
    .page { max-width: 1480px; margin: 0 auto; padding: 24px 18px 48px; }
    .hero { background: #ffffff; border: 1px solid #dde5ee; border-radius: 8px; padding: 22px 24px; margin-bottom: 18px; }
    .hero h1 { margin: 0 0 8px; font-size: 24px; line-height: 1.25; }
    .hero p { margin: 0; color: #5d6d82; font-size: 14px; }
    .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-top: 18px; }
    .stat { border: 1px solid #e3e9f0; border-radius: 6px; padding: 10px 12px; background: #f9fbfd; }
    .stat span { display: block; color: #68788d; font-size: 12px; margin-bottom: 4px; }
    .stat strong { font-size: 20px; }
    .viewer-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; margin: 16px 0; }
    .viewer-toolbar label.is-hidden { display: none; }
    .viewer-toolbar label { display: grid; gap: 5px; color: #53677f; font-size: 13px; font-weight: 650; }
    .viewer-toolbar select { min-width: min(100%, 320px); border: 1px solid #cbd7e3; border-radius: 6px; padding: 8px 10px; background: #fff; color: #26364a; font-weight: 650; }
    .viewer-section { background: #ffffff; border: 1px solid #dde5ee; border-radius: 8px; padding: 18px; margin-bottom: 16px; }
    .viewer-section.is-hidden, .plot-card.is-hidden { display: none; }
    .section-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 14px; }
    .section-head h2 { margin: 0; font-size: 17px; }
    .section-head span { color: #6b7c90; font-size: 13px; }
    .plot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
    .plot-card { border: 1px solid #e1e8ef; border-radius: 6px; overflow: hidden; background: #fff; }
    .plot-card img { display: block; width: 100%; height: auto; background: #fff; }
    .plot-meta { border-top: 1px solid #edf1f5; padding: 9px 11px; }
    .plot-meta strong { display: block; font-size: 13px; line-height: 1.35; word-break: break-word; }
    .plot-meta span { display: block; margin-top: 3px; color: #6b7c90; font-size: 12px; }
    .downloads { background: #ffffff; border: 1px solid #dde5ee; border-radius: 8px; padding: 16px 18px; }
    .downloads h2 { margin: 0 0 12px; font-size: 17px; }
    details { border-top: 1px solid #edf1f5; padding: 10px 0; }
    details:first-of-type { border-top: 0; }
    summary { cursor: pointer; font-weight: 650; color: #26364a; }
    .download-grid { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .download-grid a { display: inline-flex; max-width: 360px; border: 1px solid #cbd7e3; border-radius: 6px; padding: 6px 10px; color: #0f5f86; text-decoration: none; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .download-grid a:hover { background: #eef7fb; }
    .warning { margin: 0 0 16px; border: 1px solid #f1c36d; background: #fff8e6; border-radius: 8px; padding: 12px 14px; color: #6b4d07; }
    .warning ul { margin: 8px 0 0 18px; padding: 0; }
    .empty p, .empty-note { color: #68788d; }
    .empty-note { padding: 20px; text-align: center; border: 1px dashed #cbd7e3; border-radius: 6px; background: #f9fbfd; }
    .empty-note.is-hidden { display: none; }
    @media (max-width: 720px) { .plot-grid { grid-template-columns: 1fr; } .page { padding: 14px 10px 32px; } }
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <h1>PEP Sharing Analysis Results</h1>
      <p>Chains: """ + _html.escape(", ".join(metadata.get("selected_chains") or [])) + """ | Group fields: """ + _html.escape(", ".join(metadata.get("group_fields") or [])) + """</p>
      <div class="stats">""" + stats_html + """</div>
    </section>
    """ + ("""
    <div class="viewer-toolbar">
      <label for="pepImageCategorySelect">Image category<select id="pepImageCategorySelect">""" + section_options_html + """</select></label>
      <label for="pepGroupFieldSelect">Group field<select id="pepGroupFieldSelect">""" + group_options_html + """</select></label>
      <label for="pepChainSelect">Chain<select id="pepChainSelect">""" + chain_options_html + """</select></label>
      <label for="pepUsageSelect">Usage type<select id="pepUsageSelect">""" + usage_options_html + """</select></label>
      <label for="pepPlotTypeSelect">Plot type<select id="pepPlotTypeSelect">""" + plot_options_html + """</select></label>
    </div>
    """ if section_options_html else "") + """
    """ + warning_html + """
    """ + "".join(sections_html) + """
    <section class="downloads">
      <h2>CSV Downloads</h2>
      """ + (downloads_html or '<p class="empty-note">No CSV downloads available.</p>') + """
    </section>
  </main>
  <script>
  (function() {
    var categorySelect = document.getElementById('pepImageCategorySelect');
    var groupSelect = document.getElementById('pepGroupFieldSelect');
    var chainSelect = document.getElementById('pepChainSelect');
    var usageSelect = document.getElementById('pepUsageSelect');
    var plotSelect = document.getElementById('pepPlotTypeSelect');
    var countEl = document.getElementById('pepVisibleCount');
    var emptyEl = document.getElementById('pepNoMatches');
    var cards = Array.prototype.slice.call(document.querySelectorAll('.plot-card'));

    function matches(select, value) {
      return !select || select.value === '__all__' || select.value === value;
    }
    function selectedSection() {
      return categorySelect ? categorySelect.value : '';
    }
    function isChainOnlySection() {
      return selectedSection() === 'CDR3 arrangement heatmaps';
    }
    function setFilterVisibility() {
      var chainOnly = isChainOnlySection();
      [
        { select: groupSelect, hidden: chainOnly },
        { select: usageSelect, hidden: chainOnly },
        { select: plotSelect, hidden: chainOnly }
      ].forEach(function(item) {
        if (!item.select) return;
        var label = item.select.closest ? item.select.closest('label') : null;
        if (label) label.classList.toggle('is-hidden', item.hidden);
        if (item.hidden) item.select.value = '__all__';
      });
    }

    function applyFilters() {
      setFilterVisibility();
      var chainOnly = isChainOnlySection();
      var visible = 0;
      cards.forEach(function(card) {
        var keep = matches(categorySelect, card.dataset.section)
          && (chainOnly || matches(groupSelect, card.dataset.groupField))
          && matches(chainSelect, card.dataset.chain)
          && (chainOnly || matches(usageSelect, card.dataset.usageType))
          && (chainOnly || matches(plotSelect, card.dataset.plotType));
        card.classList.toggle('is-hidden', !keep);
        if (keep) visible += 1;
      });
      if (countEl) countEl.textContent = visible + ' images';
      if (emptyEl) emptyEl.classList.toggle('is-hidden', visible !== 0);
    }
    [categorySelect, groupSelect, chainSelect, usageSelect, plotSelect].forEach(function(select) {
      if (select) select.addEventListener('change', applyFilters);
    });
    applyFilters();
  })();
  </script>
</body>
</html>""", encoding="utf-8")
    result["viewer_url"] = f"/api/script-hub/results/{job_id}/viewer.html"
    metadata_path = output_base / "pep_analysis_metadata.json"
    if metadata_path.exists():
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")



def _write_unified_viewer(
    *,
    viewer_path: Path,
    title: str,
    subtitle: str,
    image_groups: list,
    download_sections: list,
    stats: list,
    metadata: dict,
) -> None:
    """Generate a self-contained filterable viewer.html with the profile-viewer UI pattern."""
    import html as _html

    all_categories = []
    seen = set()
    for group in image_groups:
        for item in group.get("items", []):
            cat = str(item.get("category", "")).strip()
            if cat and cat not in seen:
                seen.add(cat)
                all_categories.append(cat)
    default_category = all_categories[0] if all_categories else ""

    cards = []
    for group in image_groups:
        for item in group.get("items", []):
            src = _html.escape(str(item.get("src", "")))
            title_text = _html.escape(str(item.get("title", src.rsplit("/", 1)[-1] if "/" in src else src)))
            raw_category = str(item.get("category", "")).strip()
            category = _html.escape(raw_category)
            is_sig = item.get("sig", False)
            badge_class = "is-sig" if is_sig else "is-ns"
            badge_text = "Significant" if is_sig else "NS"
            cards.append(
                '<article class="plot-card' + (" is-hidden" if raw_category != default_category else "") + '" data-category="' + category + '" data-sig="'
                + ("1" if is_sig else "0") + '">'
                '<div class="plot-head"><div><strong>' + title_text + '</strong><span>' + category + '</span></div>'
                '<em class="' + badge_class + '">' + badge_text + '</em></div>'
                '<a href="' + src + '" target="_blank" rel="noopener">'
                '<img src="' + src + '" alt="' + title_text + '" loading="lazy"></a></article>'
            )

    cards_html = "".join(cards) if cards else '<div class="empty-txt">No output available.</div>'

    category_select_html = "".join(
        '<option value="' + _html.escape(c) + '"' + (" selected" if c == default_category else "") + ">"
        + _html.escape(c) + "</option>"
        for c in all_categories
    )
    if not category_select_html:
        category_select_html = '<option value="">(no categories)</option>'

    stats_html = "".join(
        '<div class="stat-item"><strong>' + _html.escape(s["label"]) + '</strong><span>' + _html.escape(s["value"]) + '</span></div>'
        for s in stats
    )

    download_html = ""
    for ds in download_sections:
        label = _html.escape(ds.get("label", ""))
        links = ds.get("links", [])
        if not links:
            continue
        btns = "".join(
            '<a class="btn btn-sm btn-outline-secondary m-1" href="' + _html.escape(ll["url"]) + '" download>'
            + _html.escape(ll.get("name", ll["url"].rsplit("/", 1)[-1])) + '</a>'
            for ll in links
        )
        download_html += '<div class="download-section"><div class="section-label">' + label + '</div><div class="d-flex flex-wrap gap-1">' + btns + '</div></div>'

    html_page = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>""" + _html.escape(title) + """</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Microsoft YaHei", sans-serif; background: #f4f7fa; color: #1e293b; line-height: 1.6; }
    .page { max-width: 1440px; margin: 0 auto; padding: 1.5rem 1rem 3rem; }
    .header { background: #fff; border-radius: 18px; padding: 1.5rem 1.8rem; margin-bottom: 1.2rem; border: 1px solid #dee6ed; box-shadow: 0 8px 24px rgba(0,0,0,.04); }
    .header h1 { font-size: 1.35rem; font-weight: 720; margin-bottom: .35rem; }
    .header .meta { color: #5f7d94; font-size: .88rem; }
    .stats { display: flex; flex-wrap: wrap; gap: .65rem; margin-top: 1rem; }
    .stat-item { flex: 1 1 140px; min-width: 130px; background: #f6f9fc; border-radius: 12px; padding: .75rem 1rem; border: 1px solid #dee8f0; }
    .stat-item strong { display: block; font-size: .72rem; color: #5f7d94; text-transform: uppercase; letter-spacing: .04em; margin-bottom: .22rem; }
    .stat-item span { font-size: .95rem; font-weight: 680; }
    .toolbar { display: flex; flex-wrap: wrap; gap: .55rem; align-items: center; margin-bottom: 1rem; }
    .sig-toggle { display: inline-flex; align-items: center; gap: .45rem; padding: .52rem 1rem; border-radius: 999px; border: 1px solid #c5d4e0; background: #fff; cursor: pointer; font-size: .84rem; font-weight: 600; transition: all .15s; user-select: none; }
    .sig-toggle:hover { border-color: #6fa3c4; }
    .sig-toggle.is-active { border-color: #0b6b5f; background: #ecfbf6; color: #0b6b5f; }
    .category-filter { display: inline-flex; align-items: center; gap: .45rem; color: #5f7d94; font-size: .82rem; font-weight: 650; }
    .category-filter select { min-width: min(100vw - 2rem, 280px); border: 1px solid #c5d4e0; border-radius: 10px; background: #fff; color: #1e293b; padding: .52rem .72rem; font-weight: 650; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: .85rem; }
    .plot-card { background: #fff; border-radius: 14px; border: 1px solid #dee6ed; overflow: hidden; transition: transform .15s, box-shadow .15s; }
    .plot-card:hover { box-shadow: 0 6px 18px rgba(0,0,0,.07); }
    .plot-card.is-hidden { display: none; }
    .plot-head { display: flex; justify-content: space-between; align-items: flex-start; gap: .5rem; padding: .7rem .85rem; border-bottom: 1px solid #edf2f6; background: #fbfdfe; }
    .plot-head strong { display: block; font-size: .82rem; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .plot-head span { display: block; color: #5f7d94; font-size: .72rem; margin-top: .05rem; }
    .plot-head em { flex: 0 0 auto; font-size: .68rem; font-weight: 700; padding: .2rem .48rem; border-radius: 999px; font-style: normal; }
    .plot-head em.is-sig { background: #dcfce7; color: #166534; }
    .plot-head em.is-ns { background: #f1f5f9; color: #64748b; }
    .plot-card img { width: 100%; height: auto; display: block; cursor: pointer; }
    .empty-txt { grid-column: 1 / -1; text-align: center; padding: 2.5rem 1rem; color: #8397a8; font-size: .92rem; }
    .download-section { margin-top: .75rem; }
    .section-label { font-size: .82rem; font-weight: 700; color: #475569; margin-bottom: .35rem; }
    .back-link { display: inline-flex; align-items: center; gap: .35rem; color: #11597c; text-decoration: none; font-size: .85rem; margin-bottom: .8rem; }
    .back-link:hover { text-decoration: underline; }
    @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<div class="page">
  <a class="back-link" href="javascript:history.back()">&#8592; Back</a>
  <div class="header">
    <h1>""" + _html.escape(title) + """</h1>
    <div class="meta">""" + _html.escape(subtitle) + """</div>
    <div class="stats">""" + stats_html + """</div>
  </div>
  <div class="toolbar">
    <button class="sig-toggle" id="sigToggle">Show significant only</button>
    <label class="category-filter" for="categorySelect">Image category
      <select id="categorySelect">""" + category_select_html + """</select>
    </label>
  </div>
  <div class="grid" id="plotGrid">""" + cards_html + """</div>
  """ + download_html + """
</div>
<script>
(function() {
  var cards = document.querySelectorAll('.plot-card');
  var sigToggle = document.getElementById('sigToggle');
  var categorySelect = document.getElementById('categorySelect');
  var sigOnly = false;
  var activeCat = categorySelect ? categorySelect.value : '';
  function applyFilters() {
    cards.forEach(function(card) {
      var ms = !sigOnly || card.dataset.sig === '1';
      var mc = !activeCat || card.dataset.category === activeCat;
      card.classList.toggle('is-hidden', !ms || !mc);
    });
  }
  if (sigToggle) sigToggle.addEventListener('click', function() {
    sigOnly = !sigOnly;
    sigToggle.classList.toggle('is-active', sigOnly);
    sigToggle.textContent = sigOnly ? 'Showing significant only' : 'Show significant only';
    applyFilters();
  });
  if (categorySelect) categorySelect.addEventListener('change', function() {
    activeCat = categorySelect.value;
    applyFilters();
  });
  applyFilters();
})();
</script>
</body>
</html>"""
    viewer_path.write_text(html_page, encoding="utf-8")


# ── Shared cross-module helpers ──

def _resolve_usage_data_dir(path: Path) -> Path:
    for candidate in (
        path / "1VJusage",
        path / "usage" / "1VJusage",
        path / "0VJusage",
        path / "usage" / "0VJusage",
    ):
        if candidate.exists() and candidate.is_dir():
            return candidate
    return path


def _looks_like_category_row(series) -> bool:
    """Return True if the row appears to be category labels (mostly non-numeric)."""
    if len(series) == 0:
        return False
    numeric_count = 0
    total = 0
    for v in series.dropna():
        total += 1
        try:
            float(v)
            numeric_count += 1
        except (ValueError, TypeError):
            pass
    return total > 0 and numeric_count / total < 0.3


def _suggest_profile_ranges(columns: List[str]) -> Dict[str, str]:
    """Suggest Grouping Range (categorical columns) and Parameter Range (metric columns)."""
    grouping_cols: List[str] = []
    param_cols: List[str] = []
    found_first_metric = False
    for col in columns:
        is_metric = (
            "_" in col
            and not col.lower() in {"sample", "sample_id", "sample_name", "project", "species", "chain", "barcode"}
        )
        if is_metric:
            found_first_metric = True
        if found_first_metric:
            param_cols.append(col)
        else:
            grouping_cols.append(col)
    if not param_cols:
        param_cols = list(columns)
    if not grouping_cols:
        grouping_cols = [columns[0]] if columns else []
    return {
        "suggested_grouping_begin": grouping_cols[0] if grouping_cols else "",
        "suggested_grouping_over": grouping_cols[-1] if grouping_cols else "",
        "suggested_param_begin": param_cols[0] if param_cols else "",
        "suggested_param_over": param_cols[-1] if param_cols else "",
    }


def _suggest_umap_ranges(columns: List[str]) -> Dict[str, str]:
    suggestions = _suggest_profile_ranges(columns)
    grouping_cols = []
    if suggestions["suggested_param_begin"] in columns:
        metric_start = columns.index(suggestions["suggested_param_begin"])
        grouping_cols = columns[:metric_start]
    if not grouping_cols:
        grouping_cols = [columns[0]] if columns else []
    non_sample_grouping = [
        col for col in grouping_cols
        if str(col or "").strip().lower() not in {"sample", "sample_id", "sample_name"}
    ]
    class_cols = non_sample_grouping or grouping_cols
    return {
        **suggestions,
        "suggested_classification_begin": class_cols[0] if class_cols else "",
        "suggested_classification_over": class_cols[-1] if class_cols else "",
    }



