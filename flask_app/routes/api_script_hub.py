"""
API routes for unified script-style analysis modules.
Currently exposes the DB alignment workflow as an asset-driven script entry.
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
from flask import Blueprint, current_app, jsonify, request, send_file

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

script_hub_bp = Blueprint("script_hub", __name__, url_prefix="/api/script-hub")
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
            },
        )

    if module_name in {"boxplot", "profile", "umap"}:
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        config_json = {
            "param_begin": str(data.get("param_begin") or "").strip(),
            "param_over": str(data.get("param_over") or "").strip(),
            "pvalue_threshold": float(data.get("pvalue_threshold") or 0.05),
        }
        if module_name == "profile":
            config_json.update({
                "grouping_begin": str(data.get("grouping_begin") or "").strip(),
                "grouping_over": str(data.get("grouping_over") or "").strip(),
                "grouptype_fields": data.get("grouptype_fields") if isinstance(data.get("grouptype_fields"), list) else [],
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
            config_json = {
                "selected_chains": data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else [],
                "group_fields": data.get("group_fields") if isinstance(data.get("group_fields"), list) else [],
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
        mode = str(data.get("mode") or "profile").strip().lower()
        usage_path = str(data.get("usage_path") or "").strip()
        if mode == "vj-usage":
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
                "feature_cols": _list_payload(data.get("feature_cols")) if mode != "profile" else [],
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


@script_hub_bp.route("/cache/check", methods=["POST"])
def check_script_hub_cache():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "db-alignment").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        cache_context = _cache_context_from_script_request(data, module_name)
        result = _find_reusable_script_result(cache_context, module_name)
        return jsonify(_sanitize_nan({
            "success": True,
            "hit": bool(result),
            "reused_result": bool(result),
            "module": module_name,
            "analysis_signature": cache_context.get("analysis_signature", ""),
            "result_id": result.get("result_id", "") if result else "",
            "result": result,
            "project_id": cache_context.get("project_id", ""),
            "config_json": cache_context.get("config_json", {}),
            "input_assets": cache_context.get("input_assets", []),
        }))
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error checking Script Hub cache: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_CACHE_CHECK_ERROR", "message": str(exc)}), 500


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


def _inspect_data_selection_payload(pep_paths: List[str], profile_path: Optional[str]) -> Dict[str, Any]:
    pep_files = _iter_candidate_pep_files(pep_paths)
    discovered_chains: set[str] = set()
    sample_names: set[str] = set()
    file_preview: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for pep_file in pep_files:
        chain = _infer_wide_chain_from_filename(pep_file.name) or _chain_from_parent_dirs(pep_file)
        if not chain:
            continue
        discovered_chains.add(chain)
        sample_names.add(_sample_name_from_pep_file(pep_file, chain))
        if len(file_preview) < 20:
            file_preview.append({
                "path": str(pep_file),
                "filename": pep_file.name,
                "chain": chain,
                "sample": _sample_name_from_pep_file(pep_file, chain),
            })

    resolved_profile = str(profile_path or "").strip()
    profile_candidates = [resolved_profile] if resolved_profile else []

    profile_file = Path(resolved_profile) if resolved_profile else None
    profile_columns = _read_table_columns(profile_file)
    group_fields = [column for column in profile_columns if str(column).strip().lower() != "sample"]

    if pep_paths and not pep_files:
        warnings.append("No CSV files were found under the selected PEP paths.")
    if pep_files and not discovered_chains:
        warnings.append("CSV files were found, but no supported chain suffix was detected.")
    if resolved_profile and not profile_columns:
        warnings.append("Profile file was selected, but its header could not be read.")

    return {
        "pep_paths": pep_paths,
        "profile_path": resolved_profile,
        "profile_candidates": profile_candidates,
        "profile_columns": profile_columns,
        "group_fields": group_fields,
        "chains": sorted(discovered_chains),
        "chain_count": len(discovered_chains),
        "sample_count": len(sample_names),
        "samples": sorted(sample_names)[:50],
        "pep_file_count": len(pep_files),
        "pep_files_preview": file_preview,
        "warnings": warnings,
    }


def _discover_db_alignment_inputs(base_path: str, profile_path: Optional[str], requested_mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not str(base_path or "").strip():
        raise ValidationError(message="base_path is required", details={"field": "base_path"})

    service = get_auto_heatmap_service()
    scan_result = service.scan_base_folder(base_path)

    filtered_samples: List[Dict[str, Any]] = []
    discovered_chains: set[str] = set()
    preview_file_path = ""
    preview_columns: List[str] = []
    preview_rows: List[List[Any]] = []

    for sample in scan_result.samples:
        normalized_files: Dict[str, Dict[str, Any]] = {}
        for file_info in sample.data_files:
            normalized_chain = _normalize_chain(_infer_chain_from_filename(file_info.filename))
            if normalized_chain not in _SUPPORTED_CHAINS:
                continue
            if normalized_chain not in normalized_files:
                normalized_files[normalized_chain] = {
                    "filename": file_info.filename,
                    "filepath": file_info.filepath,
                    "size": file_info.size,
                    "rows": file_info.rows,
                    "columns": file_info.columns,
                }
                discovered_chains.add(normalized_chain)
                if not preview_file_path:
                    preview_file_path = file_info.filepath

        if normalized_files:
            filtered_samples.append(
                {
                    "original_name": sample.original_name,
                    "display_name": sample.display_name,
                    "folder_path": sample.folder_path,
                    "data_files": list(normalized_files.values()),
                }
            )

    if not filtered_samples:
        raise ValidationError(
            message="No TRA/TRB pep files were detected under the selected base path",
            details={"base_path": base_path}
        )

    if not discovered_chains:
        raise ValidationError(
            message="DB alignment currently supports TRA/TRB files only",
            details={"base_path": base_path}
        )

    if preview_file_path:
        preview_result = service.get_file_columns(preview_file_path)
        preview_columns = list(preview_result.get("columns") or [])
        preview_rows = list(preview_result.get("sample_data") or [])
        suggested_mapping = {
            "cdr3_column": str(preview_result.get("suggested_cdr3") or _find_matching_column(preview_columns, _COLUMN_HINTS["cdr3_column"])).strip(),
            "copy_column": str(preview_result.get("suggested_copy") or _find_matching_column(preview_columns, _COLUMN_HINTS["copy_column"])).strip(),
        }
    else:
        suggested_mapping = {"cdr3_column": "", "copy_column": ""}

    requested_mapping = requested_mapping if isinstance(requested_mapping, dict) else {}
    resolved_mapping = {
        "cdr3_column": str(requested_mapping.get("cdr3_column") or suggested_mapping["cdr3_column"]).strip(),
        "copy_column": str(requested_mapping.get("copy_column") or suggested_mapping["copy_column"]).strip(),
    }

    missing_mapping = [name for name, value in resolved_mapping.items() if not value]
    if missing_mapping:
        raise ValidationError(
            message="Unable to auto-detect required DB alignment columns",
            details={
                "missing_fields": missing_mapping,
                "preview_file": preview_file_path,
                "available_columns": preview_columns,
            }
        )

    invalid_mapping = [value for value in resolved_mapping.values() if value not in preview_columns]
    if invalid_mapping:
        raise ValidationError(
            message="Selected field mapping does not exist in the detected pep file",
            details={"invalid_columns": invalid_mapping, "available_columns": preview_columns}
        )

    chain_list = sorted(discovered_chains)
    asset_hints = _collect_asset_hints(base_path, profile_path)
    sample_preview = [
        {
            "sample_name": sample["display_name"] or sample["original_name"],
            "chains": [_normalize_chain(_infer_chain_from_filename(file_info.get("filename", ""))) for file_info in sample["data_files"]],
            "file_count": len(sample["data_files"]),
        }
        for sample in filtered_samples[:20]
    ]

    return {
        "base_path": base_path,
        "summary": scan_result.summary,
        "samples": filtered_samples,
        "sample_count": len(filtered_samples),
        "pep_file_count": sum(len(sample["data_files"]) for sample in filtered_samples),
        "selected_chains": chain_list,
        "sample_preview": sample_preview,
        "preview_file_path": preview_file_path,
        "preview_columns": preview_columns,
        "preview_rows": preview_rows,
        "suggested_field_mapping": suggested_mapping,
        "resolved_field_mapping": resolved_mapping,
        **asset_hints,
    }


def _build_profile_category_preview(
    *,
    profile_path: str,
    profile_sheet: Optional[str] = None,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    path = Path(str(profile_path or "").strip())
    if not path.exists() or not path.is_file():
        raise ValidationError(message="Profile file not found", details={"profile_path": profile_path})

    read_kwargs: Dict[str, Any] = {"low_memory": False}
    if profile_sheet:
        read_kwargs["sheet_name"] = profile_sheet
    df = _robust_read_csv(path, **read_kwargs)
    requested = [str(item).strip() for item in (categories or []) if str(item or "").strip()]
    if not requested:
        requested = [
            col for col in df.columns.tolist()
            if str(col or "").strip().lower() not in {"sample", "sample_id", "sample_name"}
        ]

    fields = []
    for field in requested:
        if field not in df.columns:
            fields.append({"field": field, "values": [], "unique_count": 0, "missing": True, "truncated": False})
            continue
        values = sorted(str(value) for value in df[field].dropna().unique().tolist() if str(value).strip())
        fields.append({
            "field": field,
            "values": values[:40],
            "unique_count": len(values),
            "missing": False,
            "truncated": len(values) > 40,
        })

    return {
        "profile_path": str(path.resolve()),
        "profile_sheet": profile_sheet or "",
        "fields": fields,
    }


def _run_db_alignment_task(
    task_id: str,
    *,
    results_root: Path,
    base_path: str,
    output_name: Optional[str],
    profile_path: Optional[str],
    field_mapping: Dict[str, str],
    categories: List[str],
    contained_pathology: bool,
    pathology_values: List[str],
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "Inspect assets", "Scanning pep/Profile inputs for DB alignment", {"module": "db-alignment"})

        discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping)

        _record_stage(
            task_id,
            12,
            "Inspect assets",
            f"Detected {discovery['sample_count']} sample(s) and {len(discovery['selected_chains'])} chain(s)",
            {
                "module": "db-alignment",
                "sample_count": discovery["sample_count"],
                "selected_chains": discovery["selected_chains"],
            }
        )

        service = DBAlignmentService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            samples=discovery["samples"],
            selected_chains=discovery["selected_chains"],
            field_mapping=discovery["resolved_field_mapping"],
            output_name=output_name,
            base_path=base_path,
            profile_path=profile_path,
            categories=categories,
            contained_pathology=contained_pathology,
            pathology_values=pathology_values,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                max(12.0, float(progress or 0.0)),
                stage,
                detail,
                {"module": "db-alignment", **(meta or {})}
            )
        )

        result = {
            "module": "db-alignment",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "report_path": str(report.viewer_path),
            "viewer_url": f"/api/script-hub/results/{report.job_id}/viewer.html",
            "metadata_url": f"/api/script-hub/results/{report.job_id}/metadata.json",
            "zip_url": f"/api/script-hub/results/{report.job_id}/db_alignment_bundle.zip",
            "sample_count": int(report.metadata.get("sample_count") or 0),
            "selected_chains": list(report.metadata.get("selected_chains") or []),
            "profile_path": str(report.metadata.get("profile_path") or ""),
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="DB Alignment Results",
            subtitle="Chains: " + ", ".join(result.get("selected_chains") or []),
            dl_extras=[("metadata_url", "metadata.json", "Metadata")],
            zip_name="db_alignment_bundle.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="db-alignment",
            detail="DB alignment report generated",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:  # pragma: no cover - surfaced to UI and logs
        logger.error("Script hub DB alignment task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "db-alignment"},
            history=history[-80:]
        )


def _discover_boxplot_inputs(base_path: str, datapoint_path: Optional[str]) -> Dict[str, Any]:
    datapoint = None
    file_candidates: List[str] = []

    if datapoint_path:
        dp = Path(datapoint_path)
        if dp.exists() and dp.is_file():
            datapoint = dp
            file_candidates.append(str(dp.resolve()))

    if not file_candidates and base_path:
        base = Path(base_path)
        if not base.exists():
            raise ValidationError(message="Base path does not exist", details={"base_path": base_path})
        search_roots = [base]
        if base.parent != base:
            search_roots.append(base.parent)
        seen: set[str] = set()
        for root in search_roots:
            for pattern in ["*.csv", "*.tsv", "*/*.csv", "*/*.tsv", "**/*.csv", "**/*.tsv"]:
                for candidate in sorted(root.glob(pattern)):
                    resolved = str(candidate.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        file_candidates.append(resolved)
                        if len(file_candidates) >= 50:
                            break
                if len(file_candidates) >= 50:
                    break
            if len(file_candidates) >= 50:
                break

    if datapoint is None and file_candidates:
        datapoint = Path(file_candidates[0])

    if datapoint is None:
        raise ValidationError(
            message="No CSV/TSV files found. Provide a specific datapoint_path or ensure the base_path contains .csv/.tsv files.",
            details={"base_path": base_path, "datapoint_path": datapoint_path}
        )
    try:
        df = _robust_read_csv(datapoint, nrows=0)
    except pd.errors.EmptyDataError as exc:
        raise ValidationError(
            message="Registered Profile file is empty or has no columns.",
            details={"profile_path": str(datapoint.resolve())},
        ) from exc
    columns = df.columns.tolist()
    if not columns:
        raise ValidationError(
            message="Registered Profile file is empty or has no columns.",
            details={"profile_path": str(datapoint.resolve())},
        )
    return {
        "base_path": base_path,
        "datapoint_path": str(datapoint.resolve()),
        "columns": columns,
        "column_count": len(columns),
        "suggested_param_begin": columns[0] if columns else "",
        "suggested_param_over": columns[-1] if columns else "",
        "file_candidates": file_candidates,
    }


def _run_boxplot_task(
    task_id: str,
    *,
    results_root: Path,
    datapoint_path: str,
    classification_begin: str,
    classification_over: str,
    grouptype_fields: Optional[List[str]] = None,
    param_begin: str,
    param_over: str,
    group_order: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    output_name: Optional[str] = None,
    module_name: str = "boxplot",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "Inspect assets", f"Reading datapoint from {datapoint_path}", {"module": module_name})
        dp_path = str(datapoint_path)
        if not Path(dp_path).exists():
            raise FileNotFoundError(f"Datapoint file not found: {dp_path}")
        columns = _robust_read_csv(dp_path, nrows=0).columns.tolist()

        if grouptype_fields:
            for gf in grouptype_fields:
                if gf not in columns:
                    raise ValidationError(message=f"grouptype field not found: {gf}", details={"available_columns": columns})
        elif classification_begin:
            if classification_begin not in columns:
                raise ValidationError(message=f"classification_begin column not found: {classification_begin}", details={"available_columns": columns})
            classification_over = classification_over.strip() if classification_over else classification_begin
            if classification_over not in columns:
                raise ValidationError(message=f"classification_over column not found: {classification_over}", details={"available_columns": columns})
        if param_begin not in columns:
            raise ValidationError(message=f"param_begin column not found: {param_begin}", details={"available_columns": columns})
        if param_over not in columns:
            raise ValidationError(message=f"param_over column not found: {param_over}", details={"available_columns": columns})

        _record_stage(task_id, 10, f"{module_name.title()} analysis", f"Starting with {len(columns)} columns", {"module": module_name})

        service = BoxPlotService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            datapoint_path=dp_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            grouptype_fields=grouptype_fields,
            param_begin=param_begin,
            param_over=param_over,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls: List[str] = []
        for png_path in report.png_paths:
            rel = Path(png_path).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        pvalue_urls: List[str] = []
        for pv_path in report.pvalue_paths:
            rel = Path(pv_path).relative_to(report.output_base)
            pvalue_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls: List[str] = []
        for csv_path in report.csv_paths:
            rel = Path(csv_path).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        sig_urls: List[str] = []
        for sig_path in report.significant_paths:
            rel = Path(sig_path).relative_to(report.output_base)
            sig_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        zip_url = ""
        if report.zip_path:
            zp = Path(report.zip_path)
            if zp.exists():
                rel = zp.relative_to(report.output_base)
                zip_url = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        viewer_url = ""
        if report.viewer_path and report.viewer_path.exists():
            viewer_url = f"/api/script-hub/results/{report.job_id}/viewer.html"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "viewer_url": viewer_url,
            "png_urls": png_urls,
            "pvalue_urls": pvalue_urls,
            "csv_urls": csv_urls,
            "significant_urls": sig_urls,
            "zip_url": zip_url,
            "metadata_url": f"/api/script-hub/results/{report.job_id}/boxplot_metadata.json",
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title=f"{module_name.title()} Analysis Results",
            subtitle="Profile: " + str(report.metadata.get("datapoint_path") or datapoint_path),
            dl_extras=[("csv_urls", None, "BoxPlot CSV"), ("pvalue_urls", None, "P-value CSV")],
            zip_name="boxplot_results.zip" if module_name == "boxplot" else f"{module_name}_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"{module_name.title()} generated {len(report.png_paths)} plots",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Script hub BoxPlot task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": module_name},
            history=history[-80:]
        )


@script_hub_bp.route("/quick-scan", methods=["POST"])
def quick_scan():
    """Lightweight scan of a single directory or file. Returns stats for the UI preview panel."""
    data = request.get_json() or {}
    paths = data.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list) or len(paths) == 0:
        return jsonify({"success": False, "message": "paths is required"}), 400

    results = []
    total_samples = 0
    total_pep_files = 0
    all_chains = set()

    for p in paths:
        target = Path(str(p))
        entry = {"path": str(p), "type": "file", "name": target.name}
        try:
            if target.is_dir():
                entry["type"] = "directory"
                # Scan for PEP files: {Sample}__{Chain}.csv
                pep_files = list(target.glob("*.csv")) + list(target.glob("*.csv.gz")) + list(target.glob("*.tsv")) + list(target.glob("*.tsv.gz"))
                samples = set()
                chains = set()
                for f in pep_files:
                    name = f.name
                    if "__" in name:
                        parts = name.rsplit("__", 1)
                        stem = parts[0]
                        chain_raw = parts[1].rsplit(".", 1)[0]
                        chain = _normalize_chain(chain_raw)
                        if chain in _SUPPORTED_CHAINS_WIDE:
                            samples.add(stem)
                            chains.add(chain)
                entry["sample_count"] = len(samples)
                entry["pep_file_count"] = len(pep_files)
                entry["chains"] = sorted(chains)
                total_samples += len(samples)
                total_pep_files += len(pep_files)
                all_chains.update(chains)
            elif target.is_file():
                entry["type"] = "file"
                if target.suffix.lower() == '.xlsx':
                    xl = pd.ExcelFile(target)
                    entry["sheets"] = xl.sheet_names
                    entry["sheet_count"] = len(xl.sheet_names)
                    # Preview first sheet
                    df = pd.read_excel(target, sheet_name=0, nrows=0)
                    entry["columns"] = df.columns.tolist()
                    entry["column_count"] = len(entry["columns"])
                else:
                    df = _robust_read_csv(target, nrows=0)
                    entry["columns"] = df.columns.tolist()
                    entry["column_count"] = len(entry["columns"])
            else:
                entry["error"] = "Path does not exist"
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)

    column_sets = [set(r.get("columns", [])) for r in results if r.get("type") == "file" and "columns" in r]
    columns_aligned = True
    if len(column_sets) > 1:
        first = column_sets[0]
        columns_aligned = all(s == first for s in column_sets[1:])

    return jsonify({
        "success": True,
        "results": results,
        "summary": {
            "pep_dir_count": sum(1 for r in results if r.get("type") == "directory"),
            "dp_file_count": sum(1 for r in results if r.get("type") == "file"),
            "total_samples": total_samples,
            "total_pep_files": total_pep_files,
            "all_chains": sorted(all_chains),
            "columns_aligned": columns_aligned,
        },
    })


@script_hub_bp.route("/modules", methods=["GET"])
def list_modules():
    return jsonify(
        {
            "success": True,
            "modules": [
                {
                    "key": "db-alignment",
                    "label": "数据库比对",
                    "status": "available",
                    "description": "基于 pep 和 Profile 数据，与 VDJdb / McPAS-TCR 公共数据库做精确匹配分析。",
                },
                {
                    "key": "profile",
                    "label": "Profile 分析",
                    "status": "available",
                    "description": "从 Datapoint/Profile CSV 读取分组字段与参数范围，生成分组箱线图并做 Mann-Whitney U 统计检验。",
                },
                {
                    "key": "pep-analysis",
                    "label": "PEP 共享分析",
                    "status": "available",
                    "description": "PEP 共享矩阵、V/J/VJ 使用频率、分组比较热图、CDR3 分类、排列热图和可视化。",
                },
                {
                    "key": "charts",
                    "label": "综合图表",
                    "status": "available",
                    "description": "基于 PEP 数据生成相似性热图、Treemap 和 Chord 图表报告。",
                },
                {
                    "key": "pgen-analysis",
                    "label": "Pgen 分析",
                    "status": "available",
                    "description": "参考 Pgen_260213 / SoNNia 流程，按样本和链计算 CDR3 Pgen、Q、Ppost 及 Pgen 均值汇总。",
                },
                {
                    "key": "topclone",
                    "label": "TopClone 分析",
                    "status": "available",
                    "description": "从 pep_data 计算 top clone 比例，再运行 BoxPlot 统计分析。",
                },
                {
                    "key": "umap",
                    "label": "UMAP 降维分析",
                    "status": "available",
                    "description": "基于 Mann-Whitney U 显著性预过滤的 UMAP 降维投影。",
                },
                {
                    "key": "volcano",
                    "label": "火山图分析",
                    "status": "available",
                    "description": "对 VJ usage 或表达矩阵做两组间差异比较，生成火山图（log2FC vs -log10 p-value）。",
                },
                {
                    "key": "go-kegg-enrichment",
                    "label": "GO/KEGG 富集分析",
                    "status": "available",
                    "description": "参考 G0_KEGG_enrichment：表达矩阵差异分析、火山图、GO/KEGG ORA 与 GSEA。",
                },
                {
                    "key": "umapin",
                    "label": "UMAPin 降维",
                    "status": "available",
                    "description": "基于 VJ usage 拼接数据做 UMAP 降维投影，可选 FDR 多重检验校正。",
                },
                {
                    "key": "ml-analysis",
                    "label": "机器学习分析",
                    "status": "available",
                    "description": "参考 ML_260526 随机森林流程，支持 Profile 特征或 PEP共享分析缓存的 VJ usage 特征。",
                },
                {
                    "key": "mait-nkt",
                    "label": "MAIT/NKT 分析",
                    "status": "available",
                    "description": "基于 TRA CDR3 宽表与参考 MAIT/iNKT 序列比对，计算丰度分数并生成分组箱线图。",
                },
            ],
        }
    )


@script_hub_bp.route("/data-selection/inspect", methods=["POST"])
def inspect_data_selection():
    try:
        data = request.get_json() or {}
        project_id = str(data.get("project_id") or "").strip()
        project_assets = _collect_project_script_hub_assets(project_id)
        if project_id:
            pep_paths = project_assets["pep_paths"]
            profile_path = project_assets["profile_path"] or None
        else:
            pep_paths = _pep_paths_from_request(data)
            profile_path = _profile_path_from_request(data, "profile_path")
        discovery = _inspect_data_selection_payload(pep_paths, profile_path)
        invalid_profiles = project_assets.get("invalid_profile_paths", []) if project_id else []
        registered_profiles = project_assets.get("profile_paths", []) if project_id else []
        invalid_transcriptomes = project_assets.get("invalid_transcriptome_paths", []) if project_id else []
        registered_transcriptomes = project_assets.get("transcriptome_paths", []) if project_id else []
        if registered_profiles:
            discovery["registered_profile_paths"] = registered_profiles[:20]
        if registered_transcriptomes:
            discovery["registered_transcriptome_paths"] = registered_transcriptomes[:20]
            discovery["transcriptome_path"] = project_assets.get("transcriptome_path") or registered_transcriptomes[0]
        if invalid_profiles and not profile_path:
            discovery["warnings"].append(
                "项目已注册 Profile 资产无效或为空，请在项目资产页删除后重新注册有效的 Profile 文件。"
            )
            discovery["invalid_profile_paths"] = invalid_profiles[:5]
        if invalid_transcriptomes and not project_assets.get("transcriptome_path"):
            discovery["warnings"].append(
                "项目已注册转录组表达矩阵无效或为空，请在项目资产页删除后重新注册有效的表达矩阵。"
            )
            discovery["invalid_transcriptome_paths"] = invalid_transcriptomes[:5]
        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_data_selection: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Script Hub data selection: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_SELECTION_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/db-alignment/inspect", methods=["POST"])
def inspect_db_alignment():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path")
        profile_path = _profile_path_from_request(data, "profile_path")
        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else None
        discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping)
        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_db_alignment: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error inspecting DB alignment inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/db-alignment/profile-categories", methods=["POST"])
def inspect_db_alignment_profile_categories():
    try:
        data = request.get_json() or {}
        profile_path = str(data.get("profile_path") or "").strip()
        profile_sheet = str(data.get("profile_sheet") or "").strip() or None
        categories = [str(item).strip() for item in (data.get("categories") or []) if str(item).strip()]
        preview = _build_profile_category_preview(
            profile_path=profile_path,
            profile_sheet=profile_sheet,
            categories=categories,
        )
        return jsonify(_sanitize_nan({"success": True, **preview}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect profile categories: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting profile categories: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_PROFILE_CATEGORY_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/db-alignment/run", methods=["POST"])
def run_db_alignment():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "db-alignment").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path")
        if not base_path:
            raise ValidationError(message="base_path is required", details={"field": "base_path"})

        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else {}
        output_name = str(data.get("output_name") or "").strip() or None
        profile_path = _profile_path_from_request(data, "profile_path")
        categories = [str(item).strip() for item in (data.get("categories") or []) if str(item).strip()]
        pathology_values = [str(item).strip() for item in (data.get("pathology_values") or []) if str(item).strip()]
        contained_pathology = _as_bool(data.get("contained_pathology"), False)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
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
                "categories": categories,
                "contained_pathology": contained_pathology,
                "pathology_values": pathology_values,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "base_path": base_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_db_alignment_task,
            task_id,
            results_root=_resolve_results_root(),
            base_path=base_path,
            output_name=output_name,
            profile_path=profile_path,
            field_mapping={
                "cdr3_column": str(field_mapping.get("cdr3_column") or "").strip(),
                "copy_column": str(field_mapping.get("copy_column") or "").strip(),
            },
            categories=categories,
            contained_pathology=contained_pathology,
            pathology_values=pathology_values,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_db_alignment: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error queuing DB alignment task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/boxplot/inspect", methods=["POST"])
def inspect_boxplot():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path")
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path)
        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_boxplot: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting BoxPlot inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/boxplot/columns", methods=["POST"])
def get_boxplot_columns():
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})

        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp, nrows=0)

        columns = df.columns.tolist()
        return jsonify({
            "success": True,
            "file_path": file_path,
            "columns": columns,
            "column_count": len(columns),
            "suggested_param_begin": columns[0] if columns else "",
            "suggested_param_over": columns[-1] if columns else "",
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_boxplot_columns: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading BoxPlot columns: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_COLUMNS_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/boxplot/group-values", methods=["POST"])
def get_boxplot_group_values():
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        column = str(data.get("column") or "").strip()
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})
        if not column:
            raise ValidationError(message="column is required", details={"field": "column"})

        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp)

        if column not in df.columns:
            raise ValidationError(message=f"Column not found: {column}", details={"available_columns": df.columns.tolist()})

        raw_values = df[column].dropna().unique().tolist()
        values = sorted(str(v) for v in raw_values)
        return jsonify({
            "success": True,
            "file_path": file_path,
            "column": column,
            "values": values,
            "count": len(values),
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_boxplot_group_values: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading BoxPlot group values: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_GROUP_VALUES_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/boxplot/group-values-bulk", methods=["POST"])
def get_boxplot_group_values_bulk():
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        columns = data.get("columns") if isinstance(data.get("columns"), list) else []
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})
        if not columns:
            raise ValidationError(message="columns is required", details={"field": "columns"})

        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp)

        result: Dict[str, Any] = {}
        for column in columns:
            if column not in df.columns:
                result[column] = {"error": f"Column not found: {column}"}
                continue
            raw_values = df[column].dropna().unique().tolist()
            values = sorted(str(v) for v in raw_values)
            result[column] = {"values": values, "count": len(values)}

        return jsonify({
            "success": True,
            "file_path": file_path,
            "groups": result,
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_boxplot_group_values_bulk: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading BoxPlot group values bulk: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_GROUP_VALUES_BULK_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/boxplot/run", methods=["POST"])
def run_boxplot():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "boxplot").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        classification_begin = str(data.get("classification_begin") or "").strip()
        classification_over = str(data.get("classification_over") or "").strip()
        grouptype_fields = data.get("grouptype_fields") if isinstance(data.get("grouptype_fields"), list) else None
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()
        group_order = str(data.get("group_order") or "").strip() or None

        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name="boxplot",
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json={
                "classification_begin": classification_begin,
                "classification_over": classification_over,
                "grouptype_fields": grouptype_fields or [],
                "param_begin": param_begin,
                "param_over": param_over,
                "group_order": group_order,
                "pvalue_threshold": pvalue_threshold,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, "boxplot")
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "datapoint_path": datapoint_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_boxplot_task,
            task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            grouptype_fields=grouptype_fields,
            param_begin=param_begin,
            param_over=param_over,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            module_name="boxplot",
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_boxplot: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing BoxPlot task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---------------------------------------------------------------------------
# TopClone task
# ---------------------------------------------------------------------------

def _build_and_save_viewer(output_base, result, metadata, *, title, subtitle, dl_extras=None):
    import json as _json
    img_items = []
    for u in result.get("png_urls", []):
        fname = u.rsplit("/", 1)[-1] if "/" in u else u
        cat = fname.rsplit(".", 1)[0].rsplit("_", 1)[0] if "_" in fname else "plot"
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


def _pep_viewer_items(urls: List[str], section: str, job_id: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    marker = f"/api/script-hub/results/{job_id}/"
    for url in urls:
        if not str(url).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")):
            continue
        rel = url.split(marker, 1)[1] if marker in url else url.rsplit("/", 1)[-1]
        parts = rel.split("/")
        group_field = parts[0] if len(parts) > 2 else "Summary"
        chain = _pep_chain_from_result_rel(rel)
        title = parts[-1]
        if section == "Differential heatmaps" and len(parts) >= 4:
            title = f"{parts[-3]} / {parts[-2]} / {parts[-1]}"
        items.append({
            "url": url,
            "section": section,
            "chain": chain,
            "group": group_field,
            "title": title,
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
    image_sections = [
        ("Differential heatmaps", _pep_viewer_items(result.get("heatmap_image_urls") or [], "Differential heatmaps", job_id)),
        ("CDR3 classification proportions", _pep_viewer_items(result.get("proportion_plot_urls") or [], "CDR3 classification proportions", job_id)),
        ("CDR3 arrangement heatmaps", _pep_viewer_items(result.get("arrange_heatmap_urls") or [], "CDR3 arrangement heatmaps", job_id)),
        ("Unique CDR3 heatmaps", _pep_viewer_items(result.get("plot_heatmap_urls") or [], "Unique CDR3 heatmaps", job_id)),
    ]
    all_images = [item for _, items in image_sections for item in items]
    visible_sections = [(name, items) for name, items in image_sections if items]
    default_section = visible_sections[0][0] if visible_sections else ""
    section_options_html = "".join(
        '<option value="' + _html.escape(section_name) + '"' + (" selected" if section_name == default_section else "") + ">"
        + _html.escape(section_name) + " (" + str(len(items)) + ")</option>"
        for section_name, items in visible_sections
    )

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

    sections_html = []
    for section_name, items in image_sections:
        if not items:
            continue
        cards = "".join(
            '<article class="plot-card" data-section="' + _html.escape(section_name) + '">'
            '<a href="' + _html.escape(item["url"]) + '" target="_blank" rel="noopener">'
            '<img src="' + _html.escape(item["url"]) + '" alt="' + _html.escape(item["title"]) + '" loading="lazy"></a>'
            '<div class="plot-meta"><strong>' + _html.escape(item["title"]) + '</strong>'
            '<span>' + _html.escape(item["chain"]) + ' / ' + _html.escape(item["group"]) + '</span></div>'
            '</article>'
            for item in items
        )
        sections_html.append(
            '<section class="viewer-section' + (" is-hidden" if section_name != default_section else "") + '" data-section="' + _html.escape(section_name) + '"><div class="section-head"><h2>' + _html.escape(section_name) + '</h2>'
            '<span>' + str(len(items)) + ' images</span></div><div class="plot-grid">' + cards + '</div></section>'
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
    .viewer-toolbar label { color: #53677f; font-size: 13px; font-weight: 650; }
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
    .empty p { color: #68788d; }
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
    """ + ('<div class="viewer-toolbar"><label for="pepImageCategorySelect">Image category</label><select id="pepImageCategorySelect">' + section_options_html + '</select></div>' if section_options_html else "") + """
    """ + warning_html + """
    """ + "".join(sections_html) + """
    <section class="downloads">
      <h2>CSV Downloads</h2>
      """ + (downloads_html or '<p class="empty-note">No CSV downloads available.</p>') + """
    </section>
  </main>
  <script>
  (function() {
    var select = document.getElementById('pepImageCategorySelect');
    var sections = Array.prototype.slice.call(document.querySelectorAll('.viewer-section[data-section]'));
    function applyCategory(category) {
      sections.forEach(function(section) {
        section.classList.toggle('is-hidden', section.dataset.section !== category);
      });
    }
    if (select) {
      select.addEventListener('change', function() { applyCategory(select.value); });
      applyCategory(select.value);
    }
  })();
  </script>
</body>
</html>""", encoding="utf-8")
    result["viewer_url"] = f"/api/script-hub/results/{job_id}/viewer.html"



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



def _run_topclone_task(
    task_id: str,
    *,
    results_root: Path,
    pep_data_path: str,
    datapoint_path: str,
    mode: str = "trace",
    top_n: int = 10,
    group_field: Optional[str] = None,
    group_order: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    selected_chains: Optional[List[str]] = None,
    output_name: Optional[str] = None,
    module_name: str = "topclone",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "TopClone inspect", f"Scanning {pep_data_path}", {"module": module_name})

        local_pep = pep_data_path
        local_dp = datapoint_path
        service = TopCloneService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            pep_data_path=local_pep,
            datapoint_path=local_dp,
            mode=mode,
            top_n=top_n,
            group_field=group_field,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            selected_chains=selected_chains,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": module_name, **(meta or {})}
            )
        )

        result: Dict[str, Any] = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "topclone_csv_url": "",
            "png_urls": [],
            "pvalue_urls": [],
            "csv_urls": [],
            "cdr3_urls": [],
            "per_sample_count": len(report.per_sample_files),
            "metadata": report.metadata,
        }

        if report.topclone_csv_path:
            rel = Path(report.topclone_csv_path).relative_to(report.output_base)
            result["topclone_csv_url"] = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        cdr3_root = report.output_base / "top_cdr3_sequences"
        if cdr3_root.exists():
            for cdr3_csv in sorted(cdr3_root.rglob("*.csv")):
                rel = cdr3_csv.relative_to(report.output_base)
                result["cdr3_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        if report.boxplot_report:
            bp = report.boxplot_report
            for png_path in bp.png_paths:
                rel = Path(png_path).relative_to(report.output_base)
                result["png_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            for pv_path in bp.pvalue_paths:
                rel = Path(pv_path).relative_to(report.output_base)
                result["pvalue_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            for csv_path in bp.csv_paths:
                rel = Path(csv_path).relative_to(report.output_base)
                result["csv_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            if bp.viewer_path and bp.viewer_path.exists():
                rel = bp.viewer_path.relative_to(report.output_base)
                result["viewer_url"] = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        result["zip_url"] = f"/api/script-hub/results/{report.job_id}/topclone_results.zip"
        _build_topclone_viewer(report.output_base, result, report.metadata)
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="TopClone Analysis Results",
            subtitle="Mode: " + str(report.metadata.get("mode", "")) + " | Chains: " + ", ".join(report.metadata.get("chains", [])),
            dl_extras=[("topclone_csv_url", "topclone.csv", "TopClone CSV"),
                       ("csv_urls", None, "BoxPlot CSV"),
                       ("pvalue_urls", None, "P-value CSV"),
                       ("cdr3_urls", None, "CDR3 Sequences")],
            zip_name="topclone_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"TopClone generated {len(result['png_urls'])} boxplots",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Script hub TopClone task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=0.0,
            stage="Failed",
            detail=str(exc),
            meta={"phase": "failed", "module": module_name},
            history=history[-80:]
        )


@script_hub_bp.route("/topclone/inspect", methods=["POST"])
def inspect_topclone():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        pep_data_path = _primary_pep_path_from_request(data, "pep_data_path", "base_path")
        if not pep_data_path:
            raise ValidationError(message="pep_data_path is required", details={"field": "pep_data_path"})
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""

        discovery = _inspect_data_selection_payload([pep_data_path], datapoint_path or None)
        chains = discovery.get("chains", [])
        samples = discovery.get("samples", [])
        category_cols = discovery.get("group_fields", [])

        return jsonify({
            "success": True,
            "pep_data_path": pep_data_path,
            "chains": chains,
            "chain_count": len(chains),
            "sample_count": len(samples),
            "samples": samples[:20],
            "category_cols": category_cols,
        })
    except ValidationError as exc:
        logger.warning("Validation error in inspect_topclone: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting TopClone inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/topclone/run", methods=["POST"])
def run_topclone():
    try:
        data = request.get_json() or {}
        module_name = "topclone"

        pep_paths = _pep_paths_from_request(data)
        pep_data_path = _primary_pep_path_from_request(data, "pep_data_path", "base_path")
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        mode = str(data.get("mode") or "trace").strip()
        top_n = int(data.get("top_n") or 10)
        group_field = str(data.get("group_field") or "").strip() or None
        group_order = str(data.get("group_order") or "").strip() or None
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        selected_chains = [
            _normalize_chain(str(chain))
            for chain in (data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else [])
            if str(chain or "").strip()
        ]
        output_name = str(data.get("output_name") or "").strip() or None

        if not pep_data_path:
            raise ValidationError(message="pep_data_path is required", details={"field": "pep_data_path"})
        if mode == "trace" and not datapoint_path:
            raise ValidationError(message="datapoint_path is required for trace mode", details={"field": "datapoint_path"})
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_path])]
                + ([{"asset_type": "profile", "path": datapoint_path}] if datapoint_path else [])
            ),
            config_json={
                "mode": mode,
                "top_n": top_n,
                "group_field": group_field,
                "group_order": group_order,
                "pvalue_threshold": pvalue_threshold,
                "selected_chains": selected_chains,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_path": pep_data_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_topclone_task,
            task_id,
            results_root=_resolve_results_root(),
            pep_data_path=pep_data_path,
            datapoint_path=datapoint_path,
            mode=mode,
            top_n=top_n,
            group_field=group_field,
            group_order=group_order,
            pvalue_threshold=pvalue_threshold,
            selected_chains=selected_chains or None,
            output_name=output_name,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_topclone: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing TopClone task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


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


@script_hub_bp.route("/profile/inspect", methods=["POST"])
def inspect_profile():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path")
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path)
        suggestions = _suggest_profile_ranges(discovery["columns"])
        discovery.update(suggestions)

        # Read sample rows for preview
        dp = Path(discovery["datapoint_path"])
        preview_rows = []
        try:
            df_preview = _robust_read_csv(dp, nrows=5)
            preview_rows = _sanitize_nan(df_preview.values.tolist())
        except Exception:
            pass
        discovery["preview_rows"] = preview_rows

        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_profile: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Profile inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/profile/columns", methods=["POST"])
def get_profile_columns():
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})


        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp, nrows=0)

        columns = df.columns.tolist()
        suggestions = _suggest_profile_ranges(columns)
        return jsonify({
            "success": True,
            "file_path": file_path,
            "columns": columns,
            "column_count": len(columns),
            **suggestions,
        })
    except ValidationError as exc:
        logger.warning("Validation error in get_profile_columns: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error reading Profile columns: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_COLUMNS_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/profile/run", methods=["POST"])
def run_profile():
    try:
        data = request.get_json() or {}
        module_name = "profile"
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        grouping_begin = str(data.get("grouping_begin") or "").strip()
        grouping_over = str(data.get("grouping_over") or "").strip()
        grouptype_fields = data.get("grouptype_fields") if isinstance(data.get("grouptype_fields"), list) else None
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json={
                "grouping_begin": grouping_begin,
                "grouping_over": grouping_over,
                "grouptype_fields": grouptype_fields or [],
                "param_begin": param_begin,
                "param_over": param_over,
                "pvalue_threshold": pvalue_threshold,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "datapoint_path": datapoint_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_boxplot_task,
            task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=grouping_begin,
            classification_over=grouping_over,
            grouptype_fields=grouptype_fields,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            module_name="profile",
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_profile: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Profile task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Pep Analysis inspect ----
@script_hub_bp.route("/pep-analysis/inspect", methods=["POST"])
def inspect_pep_analysis():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path", "pep_data_dir", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")

        discovery = _inspect_data_selection_payload(pep_paths, profile_path)

        if not discovery["chains"]:
            raise ValidationError(
                message="No pep files detected. Expected format: {Sample}__{Chain}.csv",
                details={"base_path": base_path, "pep_paths": pep_paths, "warnings": discovery.get("warnings", [])}
            )

        return jsonify({
            "success": True,
            "base_path": base_path or (pep_paths[0] if pep_paths else ""),
            "profile_path": discovery["profile_path"],
            "chains": discovery["chains"],
            "chain_count": discovery["chain_count"],
            "sample_count": discovery["sample_count"],
            "pep_file_count": discovery["pep_file_count"],
            "profile_candidates": discovery["profile_candidates"][:10],
            "profile_columns": discovery["profile_columns"],
            "group_fields": discovery["group_fields"],
            "warnings": discovery["warnings"],
        })
    except ValidationError as exc:
        logger.warning("Validation error in inspect_pep_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Pep analysis inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


# ---- Pep Analysis run ----
@script_hub_bp.route("/pep-analysis/run", methods=["POST"])
def run_pep_analysis():
    try:
        data = request.get_json() or {}
        module_name = "pep-analysis"

        pep_paths = _pep_paths_from_request(data)
        pep_data_dir = _primary_pep_path_from_request(data, "pep_data_dir", "base_path", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        selected_chains = data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else []
        group_fields = data.get("group_fields") if isinstance(data.get("group_fields"), list) else []

        if not pep_data_dir:
            raise ValidationError(message="pep_data_dir is required", details={"field": "pep_data_dir"})
        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})
        if not selected_chains:
            raise ValidationError(message="selected_chains is required", details={"field": "selected_chains"})
        if not group_fields:
            raise ValidationError(message="group_fields is required", details={"field": "group_fields"})

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        min_sample_threshold = int(data.get("min_sample_threshold") or 3)
        optional_steps_raw = data.get("optional_steps") if isinstance(data.get("optional_steps"), list) else None
        optional_steps = {int(step) for step in optional_steps_raw if str(step).isdigit()} if optional_steps_raw is not None else None
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        app_context_app = current_app._get_current_object() if project_id else None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_dir])]
                + [{"asset_type": "profile", "path": profile_path}]
            ),
            config_json={
                "selected_chains": selected_chains,
                "group_fields": group_fields,
                "pvalue_threshold": pvalue_threshold,
                "min_sample_threshold": min_sample_threshold,
                "optional_steps": sorted(optional_steps) if optional_steps is not None else None,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_dir": pep_data_dir}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_pep_analysis_task,
            task_id,
            results_root=_resolve_results_root(),
            pep_data_dir=pep_data_dir,
            profile_path=profile_path,
            group_fields=group_fields,
            selected_chains=selected_chains,
            pvalue_threshold=pvalue_threshold,
            min_sample_threshold=min_sample_threshold,
            optional_steps=optional_steps,
            output_name=output_name,
            project_id=project_id,
            app_context_app=app_context_app
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_pep_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Pep analysis task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Pgen Analysis inspect ----
@script_hub_bp.route("/pgen-analysis/inspect", methods=["POST"])
def inspect_pgen_analysis():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path", "pep_data_dir", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")
        discovery = _inspect_data_selection_payload(pep_paths, profile_path)
        sonnia_status = PgenAnalysisService.dependency_status()
        runnable_chains = [chain for chain in discovery["chains"] if chain not in {"TRD", "TRG"}]

        if not discovery["chains"]:
            raise ValidationError(
                message="No pep files detected. Expected format: {Sample}__{Chain}.csv",
                details={"base_path": base_path, "pep_paths": pep_paths, "warnings": discovery.get("warnings", [])},
            )
        if not discovery["profile_path"]:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})

        return jsonify(_sanitize_nan({
            "success": True,
            "base_path": base_path or (pep_paths[0] if pep_paths else ""),
            "profile_path": discovery["profile_path"],
            "chains": discovery["chains"],
            "runnable_chains": runnable_chains,
            "skipped_chains": [chain for chain in discovery["chains"] if chain in {"TRD", "TRG"}],
            "chain_count": len(discovery["chains"]),
            "sample_count": discovery["sample_count"],
            "pep_file_count": discovery["pep_file_count"],
            "profile_candidates": discovery["profile_candidates"][:10],
            "profile_columns": discovery["profile_columns"],
            "sample_column_candidates": [c for c in discovery["profile_columns"] if str(c).strip().lower() == "sample"]
                or discovery["profile_columns"][:1],
            "distribution_category_candidates": [
                c for c in discovery["profile_columns"]
                if str(c).strip().lower() != "sample"
            ],
            "sonnia": sonnia_status,
            "warnings": discovery["warnings"],
        }))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_pgen_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Pgen analysis inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/pgen-analysis/run", methods=["POST"])
def run_pgen_analysis():
    try:
        data = request.get_json() or {}
        module_name = "pgen-analysis"

        pep_paths = _pep_paths_from_request(data)
        pep_data_dir = _primary_pep_path_from_request(data, "pep_data_dir", "base_path", "pep_data_path")
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        selected_chains = data.get("selected_chains") if isinstance(data.get("selected_chains"), list) else []
        species = str(data.get("species") or "human").strip().lower() or "human"
        sample_col = str(data.get("sample_col") or "sample").strip() or "sample"
        distribution_category_col = str(data.get("distribution_category_col") or "").strip() or None
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None

        if not pep_data_dir:
            raise ValidationError(message="pep_data_dir is required", details={"field": "pep_data_dir"})
        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})
        if not selected_chains:
            raise ValidationError(message="selected_chains is required", details={"field": "selected_chains"})

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [pep_data_dir])]
                + [{"asset_type": "profile", "path": profile_path}]
            ),
            config_json={
                "selected_chains": selected_chains,
                "species": species,
                "sample_col": sample_col,
                "distribution_category_col": distribution_category_col or "",
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_dir": pep_data_dir}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_pgen_analysis_task,
            task_id,
            results_root=_resolve_results_root(),
            pep_data_dir=pep_data_dir,
            profile_path=profile_path,
            selected_chains=selected_chains,
            species=species,
            sample_col=sample_col,
            distribution_category_col=distribution_category_col,
            output_name=output_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_pgen_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Pgen analysis task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _run_pgen_analysis_task(
    task_id: str,
    *,
    results_root: Path,
    pep_data_dir: str,
    profile_path: str,
    selected_chains: List[str],
    species: str = "human",
    sample_col: str = "sample",
    distribution_category_col: Optional[str] = None,
    output_name: Optional[str] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        module_name = "pgen-analysis"
        _record_stage(task_id, 5, "Pgen analysis", f"Preparing {pep_data_dir}", {"module": module_name})
        service = PgenAnalysisService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            pep_data_dir=pep_data_dir,
            profile_path=profile_path,
            selected_chains=selected_chains,
            species=species,
            sample_col=sample_col,
            distribution_category_col=distribution_category_col,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": module_name, **(meta or {})},
            ),
        )

        def _url(path_str: str) -> str:
            path = Path(path_str)
            return f"/api/script-hub/results/{report.job_id}/{path.relative_to(report.output_base).as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "detail_urls": [_url(p) for p in report.detail_paths],
            "csv_urls": [_url(p) for p in report.csv_paths],
            "png_urls": [_url(p) for p in report.png_paths],
            "zip_url": _url(report.zip_path),
            "metadata_url": f"/api/script-hub/results/{report.job_id}/pgen_analysis_metadata.json",
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="Pgen Analysis Results",
            subtitle="Chains: " + ", ".join(report.metadata.get("selected_chains") or selected_chains),
            dl_extras=[
                ("csv_urls", None, "Pgen Summary CSV"),
                ("detail_urls", None, "Per-sample Pgen Detail CSV"),
            ],
            zip_name="pgen_analysis_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"Pgen analysis completed: {len(report.detail_paths)} detail tables, {len(report.png_paths)} figures",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Script hub Pgen analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "pgen-analysis"},
            history=history[-80:],
        )


def _cache_pep_usage_assets(
    project_id: str,
    job_id: str,
    output_base: str,
    selected_chains: List[str],
    group_fields: List[str],
    pep_data_dir: str,
    profile_path: str,
    projects_root: Path,
    analysis_signature: str = "",
    result_id: str = "",
) -> None:
    """Register Pep analysis usage directory as a cached_usage project asset."""
    try:
        from flask_app.models.database import Project
        from flask_app.services.project_asset_service import get_project_asset_service
        from pathlib import Path as _Path

        projects_root = _Path(projects_root)
        if not projects_root.exists():
            logger.warning("Projects root does not exist, skipping usage caching")
            return

        asset_service = get_project_asset_service(projects_root)
        project = Project.query.filter(Project.id == project_id).first()
        if project is None:
            logger.warning("Project %s not found, skipping usage caching", project_id)
            return

        output_dir = _Path(output_base)
        usage_dir = output_dir / "usage"
        mongo_save_cached_usage = None
        try:
            from flask_app.services.mongo_service import save_cached_usage
            mongo_save_cached_usage = save_cached_usage
        except Exception:
            logger.warning("Mongo cached usage service unavailable; SQL ProjectAsset cache will be used", exc_info=True)

        usage_types = {}
        for sub in ["1Vusage", "1Jusage", "1VJusage", "0Vusage", "0Jusage", "0VJusage"]:
            sub_path = usage_dir / sub
            if sub_path.exists() and sub_path.is_dir():
                usage_types[sub] = str(sub_path)

        if not usage_types:
            logger.info("No usage subdirectories found in %s", usage_dir)
            return

        def _usage_metadata(*, scope: str, storage_path: _Path, group_field: str = "") -> Dict[str, Any]:
            usage_type_dirs = {}
            for sub in ["1Vusage", "1Jusage", "1VJusage", "0Vusage", "0Jusage", "0VJusage"]:
                sub_path = storage_path / sub
                if sub_path.exists() and sub_path.is_dir():
                    usage_type_dirs[sub] = str(sub_path)
            return {
                "source_job_id": job_id,
                "source_result_signature": analysis_signature,
                "source_result_id": result_id,
                "source_module": "pep-analysis",
                "usage_scope": scope,
                "group_field": group_field,
                "chains": selected_chains,
                "group_fields": group_fields,
                "usage_types": usage_type_dirs,
                "pep_data_dir": pep_data_dir,
                "profile_path": profile_path,
                "pep_output_base": str(output_dir),
                "pep_shared_dir": str(output_dir / "Pep_shared"),
                "pep_shared_TRA_path": str(output_dir / "Pep_shared" / "TRA.csv") if (output_dir / "Pep_shared" / "TRA.csv").exists() else "",
                "pep_shared_cate_dir": str(output_dir / group_field / "Pep_shared_cate" / "Pep_shared") if group_field else "",
                "pep_shared_cate_TRA_path": str(output_dir / group_field / "Pep_shared_cate" / "Pep_shared" / "TRA.csv") if group_field and (output_dir / group_field / "Pep_shared_cate" / "Pep_shared" / "TRA.csv").exists() else "",
                "volcano_data_dir": str(storage_path / "1VJusage") if (storage_path / "1VJusage").exists() else str(storage_path),
                "usage_1vj_path": str(storage_path / "1VJusage") if (storage_path / "1VJusage").exists() else "",
                "umapin_data_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if scope == "usage" and (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
                "df_vj_all_path": str(output_dir / "usage" / "df_VJ_all.csv") if scope == "usage" and (output_dir / "usage" / "df_VJ_all.csv").exists() else "",
                "df_1vj_all_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if scope == "usage" and (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
            }

        metadata = _usage_metadata(scope="usage", storage_path=usage_dir)
        metadata.update({
            "source_job_id": job_id,
            "source_result_signature": analysis_signature,
            "source_result_id": result_id,
            "source_module": "pep-analysis",
            "usage_scope": "usage",
            "chains": selected_chains,
            "group_fields": group_fields,
            "usage_types": usage_types,
            "pep_data_dir": pep_data_dir,
            "profile_path": profile_path,
            "pep_output_base": str(output_dir),
            "pep_shared_dir": str(output_dir / "Pep_shared"),
            "pep_shared_TRA_path": str(output_dir / "Pep_shared" / "TRA.csv") if (output_dir / "Pep_shared" / "TRA.csv").exists() else "",
            "df_vj_all_path": str(output_dir / "usage" / "df_VJ_all.csv") if (output_dir / "usage" / "df_VJ_all.csv").exists() else "",
            "df_1vj_all_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
            "umapin_data_path": str(output_dir / "usage" / "df_1VJusage_all.csv") if (output_dir / "usage" / "df_1VJusage_all.csv").exists() else "",
        })

        asset = asset_service.register_cached_asset(
            project=project,
            asset_type="cached_usage",
            storage_path=str(usage_dir),
            metadata=metadata,
            original_name=f"pep_usage_{job_id}"
        )
        if mongo_save_cached_usage is not None:
            mongo_save_cached_usage(
                project_id=project_id,
                source_job_id=job_id,
                chains=selected_chains,
                group_fields=group_fields,
                usage_types=metadata.get("usage_types") or {},
                pep_data_dir=pep_data_dir,
                    profile_path=profile_path,
                    storage_path=str(usage_dir),
                    original_name=f"pep_usage_{job_id}",
                    metadata_json={**metadata, "storage_path": str(usage_dir)},
                )
        logger.info("Cached pep usage asset %s for project %s", asset.id, project_id)

        for group_field in group_fields:
            usage_cate_dir = output_dir / group_field / "usage_cate" / "usage"
            if not usage_cate_dir.exists() or not usage_cate_dir.is_dir():
                continue
            cate_metadata = _usage_metadata(
                scope="usage_cate",
                storage_path=usage_cate_dir,
                group_field=group_field,
            )
            cate_asset = asset_service.register_cached_asset(
                project=project,
                asset_type="cached_usage",
                storage_path=str(usage_cate_dir),
                metadata=cate_metadata,
                original_name=f"pep_usage_cate_{group_field}_{job_id}"
            )
            if mongo_save_cached_usage is not None:
                mongo_save_cached_usage(
                    project_id=project_id,
                    source_job_id=job_id,
                    chains=selected_chains,
                    group_fields=group_fields,
                    usage_types=cate_metadata.get("usage_types") or {},
                    pep_data_dir=pep_data_dir,
                    profile_path=profile_path,
                    storage_path=str(usage_cate_dir),
                    original_name=f"pep_usage_cate_{group_field}_{job_id}",
                    metadata_json={**cate_metadata, "storage_path": str(usage_cate_dir)},
                )
            logger.info("Cached pep usage_cate asset %s for project %s field %s", cate_asset.id, project_id, group_field)
    except Exception as exc:
        logger.warning("Failed to cache pep usage assets for project %s: %s", project_id, exc)


def _run_pep_analysis_task(
    task_id: str,
    *,
    results_root: Path,
    pep_data_dir: str,
    profile_path: str,
    group_fields: List[str],
    selected_chains: List[str],
    pvalue_threshold: float = 0.05,
    min_sample_threshold: int = 3,
    optional_steps: Optional[set] = None,
    output_name: Optional[str] = None,
    project_id: Optional[str] = None,
    app_context_app: Optional[Any] = None
) -> None:
    try:
        _record_stage(task_id, 5, "Pep Analysis", f"Scanning pep data from {pep_data_dir}", {"module": "pep-analysis"})

        local_pep_dir = pep_data_dir
        local_profile = profile_path
        _record_stage(task_id, 8, "Pep Analysis", f"Profile: {profile_path}, Groups: {group_fields}, Chains: {selected_chains}", {"module": "pep-analysis"})

        service = PepAnalysisService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            pep_data_dir=local_pep_dir,
            profile_path=local_profile,
            group_fields=group_fields,
            selected_chains=selected_chains,
            pvalue_threshold=pvalue_threshold,
            min_sample_threshold=min_sample_threshold,
            optional_steps=optional_steps,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": "pep-analysis", **(meta or {})}
            )
        )

        def _rel(path_str: str) -> str:
            return str(Path(path_str).relative_to(report.output_base).as_posix())

        def _url(path_str: str) -> str:
            return f"/api/script-hub/results/{report.job_id}/{_rel(path_str)}"

        result = {
            "module": "pep-analysis",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "shared_matrix_urls": [_url(p) for p in report.shared_matrix_paths],
            "usage_urls": [_url(p) for p in report.usage_paths],
            "heatmap_image_urls": [_url(p) for p in report.heatmap_image_paths],
            "heatmap_csv_urls": [_url(p) for p in report.heatmap_csv_paths],
            "classification_urls": [_url(p) for p in report.classification_paths],
            "proportion_urls": [_url(p) for p in report.proportion_paths],
            "proportion_plot_urls": [_url(p) for p in getattr(report, "proportion_plot_paths", [])],
            "arrange_heatmap_urls": [_url(p) for p in report.arrange_heatmap_paths],
            "plot_heatmap_urls": [_url(p) for p in report.plot_heatmap_paths],
            "zip_url": _url(report.zip_path),
            "metadata_url": f"/api/script-hub/results/{report.job_id}/pep_analysis_metadata.json",
            "metadata": report.metadata,
        }
        result["png_urls"] = [
            url for url in result["heatmap_image_urls"] + result["proportion_plot_urls"] + result["arrange_heatmap_urls"] + result["plot_heatmap_urls"]
            if str(url).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg"))
        ]
        _write_pep_analysis_viewer(report.output_base, result, report.metadata)
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="PEP Sharing Analysis Results",
            subtitle="Chains: " + ", ".join(report.metadata.get("selected_chains") or selected_chains),
            dl_extras=[
                ("shared_matrix_urls", None, "Shared Matrix CSV"),
                ("usage_urls", None, "Usage CSV"),
                ("heatmap_csv_urls", None, "Heatmap CSV"),
                ("classification_urls", None, "Classification CSV"),
                ("proportion_urls", None, "Proportion CSV"),
                ("proportion_plot_urls", None, "Proportion Plots"),
            ],
            zip_name="pep_analysis_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="pep-analysis",
            detail=f"Pep analysis completed: {len(report.shared_matrix_paths)} shared matrices, "
                   f"{len(report.heatmap_image_paths)} heatmaps, {len(report.arrange_heatmap_paths)} arrange heatmaps",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )

        # Cache usage data as project asset if project_id provided
        if project_id:
            def _cache_project_usage_assets() -> None:
                _cache_pep_usage_assets(
                    project_id=project_id,
                    job_id=report.job_id,
                    output_base=str(report.output_base),
                    selected_chains=selected_chains,
                    group_fields=group_fields,
                    pep_data_dir=pep_data_dir,
                    profile_path=profile_path,
                    projects_root=results_root.parent / "projects",
                    analysis_signature=str(result.get("analysis_signature") or ""),
                    result_id=str(result.get("result_id") or ""),
                )

            if app_context_app is not None:
                with app_context_app.app_context():
                    _cache_project_usage_assets()
            else:
                _cache_project_usage_assets()
    except Exception as exc:
        logger.error("Script hub Pep analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "pep-analysis"},
            history=history[-80:]
        )


@script_hub_bp.route("/task/<task_id>", methods=["GET"])
def get_script_hub_task_status(task_id: str):
    task = _get_task_state(task_id)
    if task is None:
        task = get_script_hub_job_service().get_job(task_id)
    else:
        _sync_job_state(task_id, task)
        job = get_script_hub_job_service().get_job(task_id) or {}
        if job.get("cancel_requested") or job.get("status") == "cancelled":
            task = _mark_script_task_cancelled(task_id)
            task = {**task, **job, "status": "cancelled", "module": job.get("module") or task.get("module")}
        else:
            task = {**job, **task, "module": job.get("module") or task.get("module")}
    if task is None:
        return jsonify({"success": False, "error": "TASK_NOT_FOUND", "message": "Task not found"}), 404
    job_id = str(task.get("job_id") or task_id)
    task_id_value = str(task.get("task_id") or task_id)
    return jsonify({"success": True, "job_id": job_id, "task_id": task_id_value, **_sanitize_nan(task)})


@script_hub_bp.route("/jobs", methods=["GET"])
def list_script_hub_jobs():
    module = request.args.get("module") or None
    project_id = request.args.get("project_id") or None
    status = request.args.get("status") or None
    limit = request.args.get("limit", default=100, type=int) or 100
    jobs = get_script_hub_job_service().list_jobs(
        module=module,
        project_id=project_id,
        status=status,
        limit=limit,
    )
    return jsonify({"success": True, "jobs": _sanitize_nan(jobs)})


@script_hub_bp.route("/jobs", methods=["POST"])
def create_script_hub_job():
    data = request.get_json() or {}
    module_name = str(data.get("module") or "").strip().lower()
    dispatch = {
        "db-alignment": run_db_alignment,
        "boxplot": run_boxplot,
        "profile": run_profile,
        "topclone": run_topclone,
        "pep-analysis": run_pep_analysis,
        "pgen-analysis": run_pgen_analysis,
        "umap": run_umap,
        "volcano": run_volcano,
        "go-kegg-enrichment": run_go_kegg_enrichment,
        "umapin": run_umapin,
        "ml-analysis": run_ml_analysis,
        "mait-nkt": run_mait_nkt,
    }
    runner = dispatch.get(module_name)
    if runner is None:
        return jsonify({
            "success": False,
            "error": "INVALID_MODULE",
            "message": f"Unsupported Script Hub module: {module_name or '-'}",
        }), 400
    return runner()


@script_hub_bp.route("/jobs/<job_id>", methods=["GET"])
def get_script_hub_job(job_id: str):
    job = get_script_hub_job_service().get_job(job_id)
    if job is None:
        job = _get_task_state(job_id)
        if job is not None:
            _sync_job_state(job_id, job)
            job = get_script_hub_job_service().get_job(job_id)
    if job is None:
        return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
    return jsonify({"success": True, "job": _sanitize_nan(job)})


@script_hub_bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel_script_hub_job(job_id: str):
    job = get_script_hub_job_service().cancel_job(job_id)
    if job is None:
        return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404

    task_id = str(job.get("task_id") or job_id)
    with _script_task_lock:
        task = _script_tasks.get(task_id)
        if task and task.get("status") not in {"completed", "failed", "cancelled"}:
            task.update({
                "status": "cancelled",
                "stage": "Cancelled",
                "detail": "Job cancelled by user.",
                "meta": {**(task.get("meta") or {}), "phase": "cancelled"},
            })
            job = dict(task, job_id=job_id, task_id=task_id)
    get_script_hub_job_service().upsert_job(job_id, job)
    return jsonify({"success": True, "job": _sanitize_nan(job)})


# ---------------------------------------------------------------------------
# UMAP endpoints
# ---------------------------------------------------------------------------

def _run_umap_task(
    task_id: str,
    *,
    results_root: Path,
    datapoint_path: str,
    classification_begin: str,
    classification_over: str,
    param_begin: str,
    param_over: str,
    pvalue_threshold: float = 0.05,
    n_neighbors: int = 6,
    min_dist: float = 0.01,
    output_name: Optional[str] = None,
    module_name: str = "umap",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "UMAP inspect", f"Reading {datapoint_path}", {"module": module_name})
        dp_path = str(datapoint_path)
        if Path(dp_path).exists():
            columns = _robust_read_csv(dp_path, nrows=0).columns.tolist()
        else:
            raise FileNotFoundError(f"Datapoint file not found: {dp_path}")
        if (not classification_begin or not classification_over) and columns:
            range_suggestions = _suggest_umap_ranges(columns)
            classification_begin = classification_begin or range_suggestions["suggested_classification_begin"]
            classification_over = classification_over or range_suggestions["suggested_classification_over"]
        if classification_begin not in columns:
            raise ValidationError(message=f"classification_begin not found: {classification_begin}")
        if classification_over not in columns:
            raise ValidationError(message=f"classification_over not found: {classification_over}")
        if param_begin not in columns:
            raise ValidationError(message=f"param_begin not found: {param_begin}")
        if param_over not in columns:
            raise ValidationError(message=f"param_over not found: {param_over}")

        _record_stage(task_id, 10, "UMAP analysis", f"Starting with {len(columns)} columns", {"module": module_name})

        service = UmapService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            datapoint_path=dp_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        pdf_urls = []
        for p in report.pdf_paths:
            rel = Path(p).relative_to(report.output_base)
            pdf_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        zip_url = ""
        if report.zip_path:
            zp = Path(report.zip_path)
            if zp.exists():
                rel = zp.relative_to(report.output_base)
                zip_url = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "pdf_urls": pdf_urls,
            "csv_urls": csv_urls,
            "zip_url": zip_url,
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="UMAP Analysis Results",
            subtitle="Profile: " + str(report.metadata.get("datapoint_path") or datapoint_path),
            dl_extras=[("csv_urls", None, "UMAP CSV"), ("pdf_urls", None, "UMAP PDF")],
            zip_name="umap_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=report.metadata.get("message") or f"UMAP generated {len(report.png_paths)} plots",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("UMAP task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="Failed",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@script_hub_bp.route("/umap/inspect", methods=["POST"])
def inspect_umap():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        dp = Path(datapoint_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="Datapoint file not found", details={"datapoint_path": datapoint_path})
        df = _robust_read_csv(dp, nrows=0)
        columns = df.columns.tolist()
        suggestions = _suggest_umap_ranges(columns)
        return jsonify({
            "success": True,
            "datapoint_path": str(dp.resolve()),
            "columns": columns,
            "column_count": len(columns),
            **suggestions,
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/umap/run", methods=["POST"])
def run_umap():
    try:
        data = request.get_json() or {}
        module_name = "umap"
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        classification_begin = str(data.get("classification_begin") or "").strip()
        classification_over = str(data.get("classification_over") or "").strip()
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required")

        dp = Path(datapoint_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="Datapoint file not found", details={"datapoint_path": datapoint_path})
        columns = _robust_read_csv(dp, nrows=0).columns.tolist()
        suggestions = _suggest_umap_ranges(columns)
        classification_begin = classification_begin or suggestions["suggested_classification_begin"]
        classification_over = classification_over or suggestions["suggested_classification_over"]
        param_begin = param_begin or suggestions["suggested_param_begin"]
        param_over = param_over or suggestions["suggested_param_over"]
        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")
        if not classification_begin or not classification_over:
            raise ValidationError(message="classification_begin and classification_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        n_neighbors = int(data.get("n_neighbors") or 6)
        min_dist = float(data.get("min_dist") or 0.01)
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json={
                "classification_begin": classification_begin,
                "classification_over": classification_over,
                "param_begin": param_begin,
                "param_over": param_over,
                "pvalue_threshold": pvalue_threshold,
                "n_neighbors": n_neighbors,
                "min_dist": min_dist,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="Queued",
                        detail="Task created", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "Queued", "Task created", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_umap_task, task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            output_name=output_name,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Volcano Analysis ----

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


def _usage_union_columns(data_dir: Path) -> List[str]:
    columns: List[str] = ["sample", "Category"]
    seen = set(columns)
    for csv_path in sorted(data_dir.glob("*.csv")):
        header = _read_header_columns(csv_path)
        if "Category" not in header:
            continue
        category_idx = header.index("Category")
        for col in header[category_idx + 1:]:
            if col not in seen:
                seen.add(col)
                columns.append(col)
    return columns


def _parse_group_comparisons(raw_value: Any) -> List[List[str]]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        pairs = []
        for line in re.split(r"[\n;]+", text):
            line = line.strip()
            if not line:
                continue
            if "_vs_" in line:
                left, right = line.split("_vs_", 1)
            elif "," in line:
                left, right = line.split(",", 1)
            else:
                continue
            pairs.append([left.strip(), right.strip()])
        return [pair for pair in pairs if pair[0] and pair[1] and pair[0] != pair[1]]
    if isinstance(raw_value, list):
        pairs = []
        for item in raw_value:
            if isinstance(item, dict):
                left = str(item.get("group1") or "").strip()
                right = str(item.get("group2") or "").strip()
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                left = str(item[0] or "").strip()
                right = str(item[1] or "").strip()
            else:
                continue
            if left and right and left != right:
                pairs.append([left, right])
        return pairs
    return []


@script_hub_bp.route("/volcano/inspect", methods=["POST"])
def inspect_volcano():
    try:
        data = request.get_json() or {}
        input_mode = str(data.get("input_mode") or "usage").strip().lower()
        if input_mode == "expression":
            expression_path = _transcriptome_path_from_request(
                data,
                "expression_path",
                "transcriptome_path",
                "profile_path",
                "datapoint_path",
            ) or ""
            if not expression_path:
                raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
            group_prefix = str(data.get("group_prefix") or "tpm_").strip()
            inspect = VolcanoService.inspect_expression_matrix(expression_path, group_prefix=group_prefix)
            return jsonify({"success": True, "input_mode": "expression", **inspect})

        data_dir = str(data.get("data_dir") or "").strip() or _resolve_project_cached_usage_path(data, preferred="volcano")
        base_path = str(data.get("base_path") or "").strip()

        if not data_dir and not base_path:
            raise ValidationError(message="data_dir or base_path is required", details={"field": "data_dir"})

        search_dir = data_dir or base_path
        dp = Path(search_dir)
        if not dp.exists():
            raise ValidationError(message=f"Directory not found: {search_dir}", details={"data_dir": search_dir})

        if dp.is_file():
            dp = dp.parent
        dp = _resolve_usage_data_dir(dp)

        file_list = sorted([str(f.resolve()) for f in list(dp.glob("df*.csv")) + list(dp.glob("df*.csv.gz")) if f.is_file()])
        if not file_list:
            file_list = sorted([str(f.resolve()) for f in list(dp.glob("*.csv")) + list(dp.glob("*.csv.gz")) if f.is_file()])

        return jsonify({
            "success": True,
            "data_dir": str(dp.resolve()),
            "file_count": len(file_list),
            "files": [Path(f).name for f in file_list[:20]],
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Volcano inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_volcano_task(
    task_id: str,
    *,
    results_root: Path,
    data_dir: str,
    input_mode: str = "usage",
    expression_path: str = "",
    group_prefix: str = "tpm_",
    comparisons: Optional[List[List[str]]] = None,
    pvalue_threshold: float = 0.05,
    logfc_cutoff: float = 1.0,
    module_name: str = "volcano",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "火山图分析", f"扫描 {expression_path or data_dir}", {"module": module_name})

        local_data_dir = data_dir

        service = VolcanoService(output_parent=results_root / _RESULT_DIR)
        if input_mode == "expression":
            report = service.generate_expression_report(
                expression_path=expression_path,
                group_prefix=group_prefix,
                comparisons=comparisons or None,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
                progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                    task_id, float(progress or 0.0), stage, detail,
                    {"module": module_name, **(meta or {})}
                )
            )
        else:
            report = service.generate_report(
                data_dir=local_data_dir,
                pvalue_threshold=pvalue_threshold,
                progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                    task_id, float(progress or 0.0), stage, detail,
                    {"module": module_name, **(meta or {})}
                )
            )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "csv_urls": csv_urls,
            "metadata": report.metadata,
        }
        # Generate viewer.html for Volcano
        _build_and_save_viewer(report.output_base, result, report.metadata,
            title="Volcano Plot Results",
            subtitle="Data: " + str(report.metadata.get("expression_path") or report.metadata.get("data_dir", "")),
            dl_extras=[("csv_urls", None, "Volcano CSV")])
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="Volcano Plot Results",
            subtitle="Data: " + str(report.metadata.get("expression_path") or report.metadata.get("data_dir", "")),
            dl_extras=[("csv_urls", None, "Volcano CSV")],
            zip_name="volcano_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"火山图分析完成，生成 {len(png_urls)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("Volcano task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@script_hub_bp.route("/volcano/run", methods=["POST"])
def run_volcano():
    try:
        data = request.get_json() or {}
        module_name = "volcano"
        input_mode = str(data.get("input_mode") or "usage").strip().lower()
        data_dir = ""
        expression_path = ""
        group_prefix = str(data.get("group_prefix") or "tpm_").strip()
        comparisons = _parse_group_comparisons(data.get("comparisons"))
        if input_mode == "expression":
            expression_path = _transcriptome_path_from_request(
                data,
                "expression_path",
                "transcriptome_path",
                "profile_path",
                "datapoint_path",
            ) or ""
            if not expression_path:
                raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
        else:
            data_dir = str(data.get("data_dir") or "").strip() or _resolve_project_cached_usage_path(data, preferred="volcano")
            if not data_dir:
                raise ValidationError(message="data_dir is required", details={"field": "data_dir"})
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        logfc_cutoff = float(data.get("logfc_cutoff") or 1.0)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "transcriptome" if input_mode == "expression" else "cached_usage", "path": expression_path or data_dir}],
            config_json={
                "input_mode": input_mode,
                "group_prefix": group_prefix if input_mode == "expression" else "",
                "comparisons": comparisons if input_mode == "expression" else [],
                "pvalue_threshold": pvalue_threshold,
                "logfc_cutoff": logfc_cutoff if input_mode == "expression" else None,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_volcano_task, task_id,
            results_root=_resolve_results_root(),
            data_dir=data_dir,
            input_mode=input_mode,
            expression_path=expression_path,
            group_prefix=group_prefix,
            comparisons=comparisons,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- GO / KEGG Enrichment ----

@script_hub_bp.route("/go-kegg-enrichment/inspect", methods=["POST"])
def inspect_go_kegg_enrichment():
    try:
        data = request.get_json() or {}
        expression_path = _transcriptome_path_from_request(
            data,
            "expression_path",
            "transcriptome_path",
            "profile_path",
            "datapoint_path",
        ) or ""
        if not expression_path:
            raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
        group_prefix = str(data.get("group_prefix") or "tpm_").strip()
        inspect = GoKeggEnrichmentService.inspect_expression_matrix(expression_path, group_prefix=group_prefix)
        return jsonify({"success": True, **inspect})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting GO/KEGG inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_go_kegg_enrichment_task(
    task_id: str,
    *,
    results_root: Path,
    expression_path: str,
    group_prefix: str = "tpm_",
    comparisons: Optional[List[List[str]]] = None,
    pvalue_threshold: float = 0.05,
    logfc_cutoff: float = 1.0,
    enrich_pvalue_cutoff: float = 0.05,
    p_adjust_method: str = "none",
    show_category: int = 20,
    simplify_go: bool = True,
    do_gsea: bool = True,
    output_name: Optional[str] = None,
    module_name: str = "go-kegg-enrichment",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 4, "GO/KEGG", f"读取表达矩阵 {expression_path}", {"module": module_name})
        service = GoKeggEnrichmentService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            expression_path=expression_path,
            group_prefix=group_prefix,
            comparisons=comparisons or None,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            enrich_pvalue_cutoff=enrich_pvalue_cutoff,
            p_adjust_method=p_adjust_method,
            show_category=show_category,
            simplify_go=simplify_go,
            do_gsea=do_gsea,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            ),
        )

        def _url(path_value: str) -> str:
            path = Path(path_value)
            rel = path.relative_to(report.output_base)
            return f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": [_url(p) for p in report.png_paths],
            "csv_urls": [_url(p) for p in report.csv_paths],
            "log_url": _url(report.log_path),
            "zip_url": _url(report.zip_path),
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="GO / KEGG Enrichment Results",
            subtitle="Expression: " + str(report.metadata.get("expression_path", "")),
            dl_extras=[("csv_urls", None, "CSV"), ("log_url", "go_kegg_enrichment.log", "Log")],
            zip_name="go_kegg_enrichment_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"GO/KEGG 富集分析完成，生成 {len(report.csv_paths)} 个表格和 {len(report.png_paths)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("GO/KEGG task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@script_hub_bp.route("/go-kegg-enrichment/run", methods=["POST"])
def run_go_kegg_enrichment():
    try:
        data = request.get_json() or {}
        module_name = "go-kegg-enrichment"
        expression_path = _transcriptome_path_from_request(
            data,
            "expression_path",
            "transcriptome_path",
            "profile_path",
            "datapoint_path",
        ) or ""
        if not expression_path:
            raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
        group_prefix = str(data.get("group_prefix") or "tpm_").strip()
        comparisons = _parse_group_comparisons(data.get("comparisons"))
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        logfc_cutoff = float(data.get("logfc_cutoff") or 1.0)
        enrich_pvalue_cutoff = float(data.get("enrich_pvalue_cutoff") or 0.05)
        p_adjust_method = str(data.get("p_adjust_method") or "none").strip() or "none"
        show_category = int(data.get("show_category") or 20)
        simplify_go = _as_bool(data.get("simplify_go"), True)
        do_gsea = _as_bool(data.get("do_gsea"), True)
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "transcriptome", "path": expression_path}],
            config_json={
                "group_prefix": group_prefix,
                "comparisons": comparisons,
                "pvalue_threshold": pvalue_threshold,
                "logfc_cutoff": logfc_cutoff,
                "enrich_pvalue_cutoff": enrich_pvalue_cutoff,
                "p_adjust_method": p_adjust_method,
                "show_category": show_category,
                "simplify_go": simplify_go,
                "do_gsea": do_gsea,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)
        _script_executor.submit(
            _run_go_kegg_enrichment_task, task_id,
            results_root=_resolve_results_root(),
            expression_path=expression_path,
            group_prefix=group_prefix,
            comparisons=comparisons,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            enrich_pvalue_cutoff=enrich_pvalue_cutoff,
            p_adjust_method=p_adjust_method,
            show_category=show_category,
            simplify_go=simplify_go,
            do_gsea=do_gsea,
            output_name=output_name,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- UMAPin Analysis ----

@script_hub_bp.route("/umapin/inspect", methods=["POST"])
def inspect_umapin():
    try:
        data = request.get_json() or {}
        data_path = str(data.get("data_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        if not data_path:
            base_path = str(data.get("base_path") or "").strip()
            if base_path:
                data_path = base_path
            else:
                raise ValidationError(message="data_path or base_path is required", details={"field": "data_path"})

        dp = Path(data_path)
        if not dp.exists():
            raise ValidationError(message=f"File not found: {data_path}", details={"data_path": data_path})

        resolved_dir = None
        union_columns: List[str] = []
        if dp.is_dir():
            dp = _resolve_usage_data_dir(dp)
            resolved_dir = dp
            found = None
            for cn in ("df_VJ_all.csv", "df_1VJusage_all.csv", "df_VJ.csv", "df_all.csv"):
                cdt = dp / cn
                if cdt.exists() and cdt.is_file():
                    found = cdt
                    break
            if found:
                dp = found
            else:
                union_columns = _usage_union_columns(dp)

        if union_columns:
            columns = union_columns
            data_path_value = str((resolved_dir or dp).resolve())
        elif not dp.is_file():
            raise ValidationError(message=f"Not a file: {dp}", details={"data_path": str(dp)})
        else:
            columns = _robust_read_csv(dp, nrows=0).columns.tolist()
            data_path_value = str(dp.resolve())

        cat_candidates = [c for c in columns if c.lower() in ("category", "group", "therapy", "disease")]
        category_col = cat_candidates[0] if cat_candidates else ""

        return jsonify({
            "success": True,
            "data_path": data_path_value,
            "columns": columns,
            "column_count": len(columns),
            "category_col": category_col,
            "suggested_param_begin": columns[2] if len(columns) > 2 else (columns[0] if columns else ""),
            "suggested_param_over": columns[-1] if columns else "",
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting UMAPin inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_umapin_task(
    task_id: str,
    *,
    results_root: Path,
    data_path: str,
    param_begin: str,
    param_over: str,
    category_col: str = "Category",
    n_neighbors: int = 6,
    min_dist: float = 0.01,
    do_fdr: bool = False,
    module_name: str = "umapin",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "UMAPin", f"读取 {data_path}", {"module": module_name})

        dp = data_path

        service = UmapinService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            data_path=dp,
            param_begin=param_begin,
            param_over=param_over,
            category_col=category_col,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            do_fdr=do_fdr,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "csv_urls": csv_urls,
            "metadata": report.metadata,
        }
        # Generate viewer.html for UMAPin
        _build_and_save_viewer(report.output_base, result, report.metadata,
            title="UMAPin Dimensionality Reduction Results",
            subtitle="Features: " + str(report.metadata.get("feature_count", "")) + " | Groups: " + ", ".join(report.metadata.get("unique_groups", [])),
            dl_extras=[("csv_urls", None, "UMAPin CSV")])
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="UMAPin Dimensionality Reduction Results",
            subtitle="Features: " + str(report.metadata.get("feature_count", "")) + " | Groups: " + ", ".join(report.metadata.get("unique_groups", [])),
            dl_extras=[("csv_urls", None, "UMAPin CSV")],
            zip_name="umapin_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"UMAPin 完成，{len(png_urls)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("UMAPin task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@script_hub_bp.route("/umapin/run", methods=["POST"])
def run_umapin():
    try:
        data = request.get_json() or {}
        module_name = "umapin"
        data_path = str(data.get("data_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        if not data_path:
            raise ValidationError(message="data_path is required", details={"field": "data_path"})

        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()
        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        category_col = str(data.get("category_col") or "Category").strip()
        n_neighbors = int(data.get("n_neighbors") or 6)
        min_dist = float(data.get("min_dist") or 0.01)
        do_fdr = bool(data.get("do_fdr") or False)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "cached_usage", "path": data_path}],
            config_json={
                "param_begin": param_begin,
                "param_over": param_over,
                "category_col": category_col,
                "n_neighbors": n_neighbors,
                "min_dist": min_dist,
                "do_fdr": do_fdr,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_umapin_task, task_id,
            results_root=_resolve_results_root(),
            data_path=data_path,
            param_begin=param_begin,
            param_over=param_over,
            category_col=category_col,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            do_fdr=do_fdr,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Machine Learning Analysis ----

def _suggest_ml_label(columns: List[str]) -> str:
    preferred = ["group_type", "timepoint", "Category", "category", "group", "disease", "therapy"]
    lower_map = {str(col).lower(): col for col in columns}
    for key in preferred:
        if key.lower() in lower_map:
            return lower_map[key.lower()]
    non_sample = [col for col in columns if str(col).strip().lower() not in {"sample", "sample_id", "id"}]
    return non_sample[0] if non_sample else (columns[0] if columns else "")


def _suggest_ml_sample(columns: List[str]) -> str:
    lower_map = {str(col).lower(): col for col in columns}
    for key in ("sample", "sample_id", "sampleid", "id"):
        if key in lower_map:
            return lower_map[key]
    return columns[0] if columns else "Sample"


def _list_payload(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _ml_profile_feature_candidates(
    profile_file: Path,
    columns: List[str],
    *,
    sample_col: str,
    label_col: str,
    filter_col: str = "",
) -> List[str]:
    excluded = {sample_col, label_col}
    if filter_col:
        excluded.add(filter_col)
    try:
        preview_df = _robust_read_csv(profile_file, nrows=200, low_memory=False)
    except TypeError:
        preview_df = _robust_read_csv(profile_file, nrows=200)
    except Exception:
        preview_df = pd.DataFrame(columns=columns)
    candidates: List[str] = []
    for col in columns:
        if col in excluded:
            continue
        if col in preview_df.columns:
            numeric = pd.to_numeric(preview_df[col], errors="coerce")
            if not numeric.notna().any():
                continue
        candidates.append(col)
    return candidates


def _ml_usage_feature_range(
    *,
    profile_path: str,
    usage_path: str,
    sample_col: str,
    param_begin: str,
    param_over: str,
) -> List[str]:
    profile_file = Path(profile_path)
    profile_df = _robust_read_csv(profile_file, low_memory=False)
    sample_source_col = sample_col if sample_col in profile_df.columns else _suggest_ml_sample(profile_df.columns.tolist())
    profile_samples = set(profile_df[sample_source_col].dropna().astype(str))
    candidates = MLAnalysisService.collect_usage_feature_candidates(
        profile_samples=profile_samples,
        usage_path=usage_path,
        sample_col=sample_source_col,
    )
    values = [str(item.get("value") or "").strip() for item in candidates if str(item.get("value") or "").strip()]
    if not values:
        return []
    if not param_begin or not param_over:
        return values
    if param_begin not in values or param_over not in values:
        raise ValidationError(
            message="VJ usage param_begin or param_over not found in usage features",
            details={"param_begin": param_begin, "param_over": param_over},
        )
    start = values.index(param_begin)
    end = values.index(param_over)
    if start > end:
        start, end = end, start
    return values[start:end + 1]


@script_hub_bp.route("/ml-analysis/inspect", methods=["POST"])
def inspect_ml_analysis():
    try:
        data = request.get_json() or {}
        project_id = str(data.get("project_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")
        if not profile_path:
            raise ValidationError(message="Profile file is required", details={"field": "profile_path"})

        profile_file = Path(profile_path)
        if not profile_file.exists():
            raise ValidationError(message=f"Profile file not found: {profile_path}", details={"profile_path": profile_path})

        columns = _read_table_columns(profile_file)
        if not columns:
            raise ValidationError(message="No columns detected from Profile file", details={"profile_path": profile_path})

        usage_path = str(data.get("usage_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        cached_usage_assets = _collect_project_cached_usage_assets(project_id) if project_id else []
        suggestions = _suggest_profile_ranges(columns)
        label_col = str(data.get("label_col") or "").strip() or _suggest_ml_label(columns)
        sample_col = str(data.get("sample_col") or "").strip() or _suggest_ml_sample(columns)
        filter_col = str(data.get("filter_col") or "").strip()

        filter_candidates = [
            col for col in columns
            if col not in {sample_col}
            and len(col) < 80
        ]
        profile_feature_candidates = _ml_profile_feature_candidates(
            profile_file,
            columns,
            sample_col=sample_col,
            label_col=label_col,
            filter_col=filter_col,
        )
        usage_feature_candidates: List[Dict[str, str]] = []
        if usage_path:
            try:
                profile_df = _robust_read_csv(profile_file, low_memory=False)
                sample_source_col = sample_col if sample_col in profile_df.columns else _suggest_ml_sample(profile_df.columns.tolist())
                profile_samples = set(profile_df[sample_source_col].dropna().astype(str))
                usage_feature_candidates = MLAnalysisService.collect_usage_feature_candidates(
                    profile_samples=profile_samples,
                    usage_path=usage_path,
                    sample_col=sample_source_col,
                )
            except Exception:
                logger.warning("Failed to inspect ML usage feature candidates", exc_info=True)

        return jsonify({
            "success": True,
            "profile_path": str(profile_file.resolve()),
            "usage_path": usage_path,
            "columns": columns,
            "column_count": len(columns),
            "sample_col": sample_col,
            "label_col": label_col,
            "filter_candidates": filter_candidates,
            "profile_feature_candidates": profile_feature_candidates,
            "usage_feature_candidates": usage_feature_candidates,
            "suggested_param_begin": suggestions.get("param_begin") or (columns[0] if columns else ""),
            "suggested_param_over": suggestions.get("param_over") or (columns[-1] if columns else ""),
            "cached_usage_assets": cached_usage_assets[:20],
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting ML inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_ml_analysis_task(
    task_id: str,
    *,
    results_root: Path,
    profile_path: str,
    mode: str,
    label_col: str,
    sample_col: str,
    param_begin: str,
    param_over: str,
    usage_path: str,
    filter_col: str,
    filter_value: str,
    feature_cols: List[str],
    usage_feature_cols: List[str],
    custom_threshold: float,
    cv_splits: int,
    roc_cv_splits: int,
    module_name: str = "ml-analysis",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "机器学习分析", f"读取 Profile: {profile_path}", {"module": module_name})

        service = MLAnalysisService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            profile_path=profile_path,
            mode=mode,
            label_col=label_col,
            sample_col=sample_col,
            param_begin=param_begin,
            param_over=param_over,
            usage_path=usage_path,
            filter_col=filter_col,
            filter_value=filter_value,
            feature_cols=feature_cols,
            usage_feature_cols=usage_feature_cols,
            custom_threshold=custom_threshold,
            cv_splits=cv_splits,
            roc_cv_splits=roc_cv_splits,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            ),
        )

        def _urls(paths: List[str]) -> List[str]:
            urls: List[str] = []
            for path in paths:
                rel = Path(path).relative_to(report.output_base)
                urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            return urls

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": _urls(report.png_paths),
            "csv_urls": _urls(report.csv_paths),
            "text_urls": _urls(report.text_paths),
            "metadata": report.metadata,
        }
        subtitle = (
            "Mode: " + str(report.metadata.get("mode", ""))
            + " | Label: " + str(report.metadata.get("label_col", ""))
            + " | Features: " + str(report.metadata.get("selected_feature_number", ""))
        )
        _build_and_save_viewer(
            report.output_base,
            result,
            report.metadata,
            title="Machine Learning Analysis Results",
            subtitle=subtitle,
            dl_extras=[("csv_urls", None, "ML CSV"), ("text_urls", None, "ML Text")],
        )
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="Machine Learning Analysis Results",
            subtitle=subtitle,
            dl_extras=[("csv_urls", None, "ML CSV"), ("text_urls", None, "ML Text")],
            zip_name="ml_analysis_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"机器学习分析完成，生成 {len(result['png_urls'])} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("ML analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@script_hub_bp.route("/ml-analysis/run", methods=["POST"])
def run_ml_analysis():
    try:
        data = request.get_json() or {}
        module_name = "ml-analysis"
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})

        mode = str(data.get("mode") or "profile").strip().lower()
        usage_path = str(data.get("usage_path") or "").strip()
        if mode == "vj-usage":
            usage_path = usage_path or _resolve_project_cached_usage_path(data, preferred="umapin")
            if not usage_path:
                raise ValidationError(message="usage_path is required for VJ usage ML", details={"field": "usage_path"})

        label_col = str(data.get("label_col") or "").strip()
        if not label_col:
            raise ValidationError(message="label_col is required", details={"field": "label_col"})

        sample_col = str(data.get("sample_col") or "Sample").strip() or "Sample"
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()
        filter_col = str(data.get("filter_col") or "").strip()
        filter_value = str(data.get("filter_value") or "").strip()
        feature_cols = _list_payload(data.get("feature_cols"))
        usage_feature_cols = _list_payload(data.get("usage_feature_cols"))
        if mode == "profile":
            feature_cols = []
            if not param_begin or not param_over:
                raise ValidationError(message="param_begin and param_over are required for Profile ML", details={"fields": ["param_begin", "param_over"]})
            usage_feature_cols = []
        if mode == "vj-usage":
            if not param_begin or not param_over:
                raise ValidationError(message="param_begin and param_over are required for VJ usage ML", details={"fields": ["param_begin", "param_over"]})
            usage_feature_cols = _ml_usage_feature_range(
                profile_path=profile_path,
                usage_path=usage_path,
                sample_col=sample_col,
                param_begin=param_begin,
                param_over=param_over,
            )
            if not usage_feature_cols:
                raise ValidationError(message="No VJ usage features found in selected parameter range", details={"field": "param_begin,param_over"})
        custom_threshold = float(data.get("custom_threshold") or 0.003)
        cv_splits = int(data.get("cv_splits") or 3)
        roc_cv_splits = int(data.get("roc_cv_splits") or 7)
        project_id = str(data.get("project_id") or "").strip() or None

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "profile", "path": profile_path},
                *([{"asset_type": "cached_usage", "path": usage_path}] if usage_path else []),
            ],
            config_json={
                "mode": mode,
                "label_col": label_col,
                "sample_col": sample_col,
                "param_begin": param_begin,
                "param_over": param_over,
                "filter_col": filter_col,
                "filter_value": filter_value,
                **({"feature_cols": feature_cols} if mode != "profile" else {}),
                "usage_feature_cols": usage_feature_cols,
                "custom_threshold": custom_threshold,
                "cv_splits": cv_splits,
                "roc_cv_splits": roc_cv_splits,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_ml_analysis_task, task_id,
            results_root=_resolve_results_root(),
            profile_path=profile_path,
            mode=mode,
            label_col=label_col,
            sample_col=sample_col,
            param_begin=param_begin,
            param_over=param_over,
            usage_path=usage_path,
            filter_col=filter_col,
            filter_value=filter_value,
            feature_cols=feature_cols,
            usage_feature_cols=usage_feature_cols,
            custom_threshold=custom_threshold,
            cv_splits=cv_splits,
            roc_cv_splits=roc_cv_splits,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error running ML analysis: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/cached-usage/<asset_id>/inspect", methods=["GET"])
def inspect_cached_usage(asset_id: str):
    try:
        from flask_app.models.database import ProjectAsset

        asset = ProjectAsset.query.filter(ProjectAsset.id == asset_id).first()
        metadata: Dict[str, Any] = {}
        storage_path_value = ""
        if asset is not None and asset.asset_type == "cached_usage":
            metadata = asset.metadata_json or {}
            storage_path_value = asset.storage_path
        else:
            try:
                from bson import ObjectId
                from flask_app.services.mongo_service import cache_col
                mongo_doc = cache_col().find_one({"_id": ObjectId(asset_id)})
            except Exception:
                mongo_doc = None
            if not mongo_doc:
                raise ValidationError(message="Cached usage asset not found", details={"asset_id": asset_id})
            metadata = mongo_doc.get("metadata_json") if isinstance(mongo_doc.get("metadata_json"), dict) else {}
            usage_types_from_doc = mongo_doc.get("usage_types") if isinstance(mongo_doc.get("usage_types"), dict) else {}
            metadata = {
                **metadata,
                "source": "mongodb",
                "source_job_id": mongo_doc.get("source_job_id", ""),
                "usage_scope": mongo_doc.get("usage_scope") or metadata.get("usage_scope", ""),
                "group_field": mongo_doc.get("group_field") or metadata.get("group_field", ""),
                "chains": mongo_doc.get("chains") or metadata.get("chains", []),
                "group_fields": mongo_doc.get("group_fields") or metadata.get("group_fields", []),
                "usage_types": usage_types_from_doc or metadata.get("usage_types", {}),
            }
            storage_path_value = str(mongo_doc.get("storage_path") or metadata.get("storage_path") or "")

        storage_path = Path(storage_path_value)
        usage_types = metadata.get("usage_types") if isinstance(metadata.get("usage_types"), dict) else {}
        vj_usage_path = (
            str(metadata.get("volcano_data_dir") or "").strip()
            or str(metadata.get("usage_1vj_path") or "").strip()
            or str(metadata.get("vj_usage_path") or "").strip()
            or str(usage_types.get("1VJusage") or usage_types.get("0VJusage") or "").strip()
            or str(_resolve_usage_data_dir(storage_path))
        )

        df_vj_all_path = str(
            metadata.get("umapin_data_path")
            or metadata.get("df_vj_all_path")
            or metadata.get("df_VJ_all_path")
            or metadata.get("df_1vj_all_path")
            or ""
        ).strip()
        if not df_vj_all_path:
            for root in [storage_path, Path(vj_usage_path)]:
                for name in ("df_VJ_all.csv", "df_1VJusage_all.csv", "df_VJ.csv", "df_all.csv"):
                    candidate = root / name
                    if candidate.exists() and candidate.is_file():
                        df_vj_all_path = str(candidate.resolve())
                        break
                if df_vj_all_path:
                    break

        return jsonify({
            "success": True,
            "asset_id": asset_id,
            "storage_path": str(storage_path),
            "exists": storage_path.exists(),
            "metadata": metadata,
            "usage_types": usage_types,
            "vj_usage_path": str(Path(vj_usage_path).resolve()) if vj_usage_path and Path(vj_usage_path).exists() else vj_usage_path,
            "df_vj_all_path": df_vj_all_path,
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting cached usage asset: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_CACHED_USAGE_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/results/<job_id>/<path:relative_path>", methods=["GET"])
def get_script_hub_result_file(job_id: str, relative_path: str):
    try:
        target_relative = Path(relative_path)
        if target_relative.is_absolute() or ".." in target_relative.parts:
            raise ValidationError(message="Invalid result path", details={"relative_path": relative_path})

        target_path: Optional[Path] = None
        for result_root in candidate_job_roots(_resolve_results_root(), _RESULT_DIR, job_id):
            result_root = result_root.resolve()
            candidate_path = (result_root / target_relative).resolve()
            if result_root not in candidate_path.parents and candidate_path != result_root:
                continue
            if candidate_path.exists() and candidate_path.is_file():
                target_path = candidate_path
                break
        if target_path is None:
            raise ValidationError(message="Result file not found", details={"relative_path": relative_path})
        if target_path.name not in _RESULT_FILES and target_path.suffix.lower() not in {".csv", ".html", ".json", ".zip", ".png", ".jpg", ".pdf", ".txt", ".log"}:
            raise ValidationError(message="Unsupported result file", details={"relative_path": relative_path})
        as_attachment = target_path.suffix.lower() in {".zip", ".pdf", ".txt", ".log"}
        return send_file(target_path, as_attachment=as_attachment)
    except ValidationError as exc:
        logger.warning("Validation error serving script hub result file: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error serving script hub result file: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RESULT_ERROR", "message": str(exc)}), 500


# ── MAIT/NKT analysis ─────────────────────────────────────────────────

@script_hub_bp.route("/mait-nkt/inspect", methods=["POST"])
def inspect_mait_nkt():
    try:
        data = request.get_json() or {}
        tra_source = str(data.get("tra_source") or "upload").strip()
        tra_path = str(data.get("tra_path") or "").strip()
        source_job_id = str(data.get("source_job_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path")

        # Resolve TRA data source
        tra_df = None
        resolved_tra_path = ""
        resolved_source_job_id = source_job_id
        resolved_source_kind = tra_source
        resolved_output_base = ""
        if tra_source == "pep_analysis" and tra_path and Path(tra_path).exists() and Path(tra_path).is_file():
            resolved_tra_path = str(PathAccessService.validate_read_path(tra_path))
            resolved_source_kind = "pep_analysis_resolved_path"
            tra_df = _robust_read_csv(Path(resolved_tra_path))
        elif tra_source == "pep_analysis":
            resolved = _resolve_pep_analysis_tra_source(data)
            resolved_tra_path = resolved["path"]
            resolved_source_job_id = str(resolved.get("source_job_id") or source_job_id)
            resolved_source_kind = str(resolved.get("source_kind") or "pep_analysis")
            resolved_output_base = str(resolved.get("output_base") or "")
            tra_df = resolved["dataframe"]
        elif tra_path:
            dp = Path(tra_path)
            if not dp.exists() or not dp.is_file():
                raise ValidationError(message="TRA file not found", details={"file_path": tra_path})
            resolved_tra_path = tra_path
            tra_df = _robust_read_csv(dp)
        else:
            raise ValidationError(
                message="请提供 TRA CSV 文件路径或选择 PEP 共享分析结果",
                details={"tra_source": tra_source},
            )

        # Detect sample columns
        sample_cols = []
        has_category_row = False
        if tra_df is not None and len(tra_df.columns) > 1:
            sample_cols = [str(c) for c in tra_df.columns[1:]]
            if len(tra_df) >= 1:
                second_row = tra_df.iloc[0, 1:]
                if _looks_like_category_row(second_row):
                    has_category_row = True

        # Load profile for group values
        profile_groups: Dict[str, Any] = {}
        if profile_path:
            pp = Path(profile_path)
            if pp.exists():
                pf = _robust_read_csv(pp)
                for col in pf.columns:
                    vals = sorted(set(str(v) for v in pf[col].dropna()))
                    profile_groups[col] = vals

        return jsonify(_sanitize_nan({
            "success": True,
            "tra_source": tra_source,
            "resolved_tra_path": resolved_tra_path,
            "source_job_id": resolved_source_job_id,
            "source_kind": resolved_source_kind,
            "pep_output_base": resolved_output_base,
            "sample_columns": sample_cols,
            "sample_count": len(sample_cols),
            "has_category_row": has_category_row,
            "profile_groups": profile_groups,
        }))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_mait_nkt: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting MAIT/NKT inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/mait-nkt/run", methods=["POST"])
def run_mait_nkt():
    try:
        data = request.get_json() or {}
        module_name = "mait-nkt"

        tra_source = str(data.get("tra_source") or "upload").strip()
        tra_path = str(data.get("tra_path") or "").strip()
        source_job_id = str(data.get("source_job_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path") or ""
        group_field = str(data.get("group_field") or "").strip()
        group_order = str(data.get("group_order") or "").strip() or None

        if not profile_path:
            raise ValidationError(message="profile_path is required", details={"field": "profile_path"})
        if not group_field:
            raise ValidationError(message="group_field is required", details={"field": "group_field"})

        project_id = str(data.get("project_id") or "").strip() or None
        resolved_tra_path = tra_path
        resolved_source_job_id = source_job_id
        if tra_source == "pep_analysis" and tra_path and Path(tra_path).exists() and Path(tra_path).is_file():
            resolved_tra_path = str(PathAccessService.validate_read_path(tra_path))
        elif tra_source == "pep_analysis":
            resolved = _resolve_pep_analysis_tra_source(data)
            resolved_tra_path = resolved["path"]
            resolved_source_job_id = str(resolved.get("source_job_id") or source_job_id)

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "tra", "path": resolved_tra_path} if tra_source == "upload" else {"asset_type": "pep_analysis_tra", "path": resolved_tra_path, "source_job_id": resolved_source_job_id},
                {"asset_type": "profile", "path": profile_path},
            ],
            config_json={"group_field": group_field, "group_order": group_order, "tra_source": tra_source},
        )
        if not _force_rerun_requested(data):
            cached = _try_reuse_script_result(cache_context, module_name)
            if cached:
                return jsonify(_sanitize_nan(cached))

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(
            task_id,
            status="queued",
            module=module_name,
            progress=0.0,
            stage="Queued",
            detail="MAIT/NKT analysis task queued",
            created_at=datetime.now().strftime("%H:%M:%S"),
            history=[_history_entry(0, "Queued", "MAIT/NKT analysis task queued")],
            **cache_context,
        )

        analysis_signature = cache_context.get("analysis_signature", "")

        _script_executor.submit(
            _run_mait_nkt_task,
            task_id,
            results_root=Path(current_app.config.get("RESULTS_FOLDER", "flask_app/data/results")),
            tra_source=tra_source,
            tra_path=resolved_tra_path,
            source_job_id=resolved_source_job_id,
            profile_path=profile_path,
            group_field=group_field,
            group_order=group_order,
            project_id=project_id,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify(_sanitize_nan({
            "success": True,
            "task_id": task_id,
            "status": "queued",
            "module": module_name,
            "status_url": f"/api/script-hub/task/{task_id}",
            "analysis_signature": analysis_signature,
        }))
    except ValidationError as exc:
        logger.warning("Validation error in run_mait_nkt: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error running MAIT/NKT analysis: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _run_mait_nkt_task(
    task_id: str,
    *,
    results_root: Path,
    tra_source: str,
    tra_path: str,
    source_job_id: str,
    profile_path: str,
    group_field: str,
    group_order: Optional[str],
    project_id: Optional[str] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 2, "Loading", "Reading TRA data")
        tra_df = None
        resolved_tra_path = tra_path
        if tra_source == "pep_analysis":
            dp = Path(tra_path) if tra_path else None
            if dp and dp.exists() and dp.is_file():
                tra_df = _robust_read_csv(dp)
                resolved_tra_path = str(dp)
            else:
                resolved = _resolve_pep_analysis_tra_source({
                    "project_id": project_id or "",
                    "source_job_id": source_job_id,
                })
                tra_df = resolved["dataframe"]
                resolved_tra_path = resolved["path"]
        else:
            dp = Path(tra_path)
            if not dp.exists():
                raise ValidationError(message="TRA file not found", details={"file_path": tra_path})
            tra_df = _robust_read_csv(dp)

        _record_stage(task_id, 8, "Loading", "Reading profile data")
        pp = Path(profile_path)
        if not pp.exists():
            raise ValidationError(message="Profile file not found", details={"file_path": profile_path})
        profile_df = _robust_read_csv(pp)

        group_order_list = None
        if group_order:
            group_order_list = [x.strip() for x in group_order.split(",") if x.strip()]

        service = MaitNktService(output_parent=results_root / _RESULT_DIR)

        def _progress(percent, stage, detail):
            _record_stage(task_id, percent, stage, detail)

        report = service.generate_report(
            tra_df=tra_df,
            profile_df=profile_df,
            group_field=group_field,
            group_order=group_order_list,
            progress_callback=_progress,
            job_id=task_id,
            datapoint_path=resolved_tra_path or tra_path,
        )

        # Build result URLs
        png_urls = []
        for png in report.png_paths:
            rel = Path(png).relative_to(report.output_base).as_posix()
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel}")

        result = {
            "module": "mait-nkt",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "viewer_url": f"/api/script-hub/results/{report.job_id}/viewer.html",
            "png_urls": png_urls,
            "zip_url": f"/api/script-hub/results/{report.job_id}/mait_nkt_results.zip",
            "metadata": report.metadata,
        }

        normalized = _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="MAIT/NKT 分析",
            subtitle=f"分组字段: {group_field}",
            dl_extras=[],
            zip_name="mait_nkt_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="mait-nkt",
            detail=f"MAIT/NKT 分析完成，生成 {len(png_urls)} 张图",
            result=normalized,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("MAIT/NKT task %s failed: %s", task_id, exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="失败",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "mait-nkt"},
            history=history[-80:],
        )


# ── helper: looks like category row ────────────────────────────────────

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


@script_hub_bp.route("/read-table-preview", methods=["POST"])
def read_table_preview():
    """Read first 5 rows and all columns from a table file (CSV/TSV/XLSX)."""
    try:
        data = request.get_json() or {}
        file_path = str(data.get("file_path") or "").strip()
        if not file_path:
            raise ValidationError(message="file_path is required", details={"field": "file_path"})
        dp = Path(file_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="File not found", details={"file_path": file_path})
        df = _robust_read_csv(dp, nrows=5)
        return jsonify(_sanitize_nan({
            "success": True,
            "file_path": str(dp.resolve()),
            "columns": df.columns.tolist(),
            "column_count": len(df.columns),
            "rows": df.values.tolist(),
            "row_count": len(df),
        }))
    except ValidationError as exc:
        logger.warning("read_table_preview validation: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("read_table_preview error: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_READ_ERROR", "message": str(exc)}), 500
