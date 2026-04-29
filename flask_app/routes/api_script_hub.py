"""
API routes for unified script-style analysis modules.
Currently exposes the DB alignment workflow as an asset-driven script entry.
"""

from __future__ import annotations

import io
import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from flask import Blueprint, current_app, jsonify, request, send_file

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
from flask_app.services.db_alignment_service import DBAlignmentService
from flask_app.services.remote_data_source_service import get_remote_data_source_service
from flask_app.services.ssh_file_provider import build_ssh_file_provider
from flask_app.services.boxplot_service import BoxPlotService

logger = logging.getLogger(__name__)

script_hub_bp = Blueprint("script_hub", __name__, url_prefix="/api/script-hub")
_script_executor = ThreadPoolExecutor(max_workers=2)
_script_task_lock = threading.Lock()
_script_tasks: Dict[str, Dict[str, Any]] = {}

_RESULT_DIR = "script_hub"
_ALLOWED_MODULES = {"db-alignment", "boxplot", "profile"}
_COLUMN_HINTS = {
    "cdr3_column": ["cdr3(pep)", "cdr3_pep", "cdr3aa", "cdr3_aa", "cdr3", "aminoacid", "sequence"],
    "copy_column": ["copy", "copies", "count", "reads", "umis", "umi", "frequency"],
}
_SUPPORTED_CHAINS = {"TRA", "TRB"}
_RESULT_FILES = {"viewer.html", "metadata.json", "db_alignment_bundle.zip", "specify_ratio.csv", "specify_ratio_with_profile.csv", "alignment_summary.csv"}


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
        task.update(updates)


def _get_task_state(task_id: str) -> Dict[str, Any] | None:
    with _script_task_lock:
        task = _script_tasks.get(task_id)
        return dict(task) if task else None


def _record_stage(task_id: str, progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> None:
    history_item = _history_entry(progress, stage, detail, meta)
    with _script_task_lock:
        task = _script_tasks.setdefault(task_id, {})
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


def _resolve_results_root() -> Path:
    results_root = Path(current_app.config.get("RESULTS_FOLDER", Path(current_app.root_path) / "data" / "results"))
    if not results_root.is_absolute():
        results_root = Path(current_app.root_path) / results_root
    return results_root.resolve()


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


def _resolve_profile_path(base_path: str, profile_path: Optional[str]) -> Optional[Path]:
    explicit = Path(str(profile_path or "").strip()) if str(profile_path or "").strip() else None
    if explicit and explicit.exists() and explicit.is_file():
        return explicit.resolve()

    base = Path(str(base_path or "").strip())
    if not base.exists():
        return None

    candidates: List[Path] = []
    search_roots = [base]
    if base.parent != base:
        search_roots.append(base.parent)
    for root in search_roots:
        candidates.extend([root / "Profile_All.csv", root / "Profile.csv"])
        candidates.extend(sorted(root.glob("Profile*.csv"))[:5])

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    return None


def _collect_asset_hints(base_path: str, profile_path: Optional[str]) -> Dict[str, Any]:
    base = Path(base_path)
    profile_file = _resolve_profile_path(base_path, profile_path)
    profile_columns: List[str] = []
    if profile_file is not None:
        try:
            profile_columns = pd.read_csv(profile_file, nrows=0).columns.tolist()
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


def _discover_remote_profile_csvs(ssh_provider, remote_path: str) -> List[str]:
    candidates: List[str] = []
    search_dirs = [remote_path]
    remote_dir = remote_path.rstrip("/")
    parent = "/" + "/".join(p for p in remote_dir.split("/") if p)[:-1] if remote_dir != "/" else None
    if parent:
        search_dirs.append(parent)

    for search_dir in search_dirs:
        try:
            found = ssh_provider.search_files(search_dir, "*.csv")
            for f in found:
                if f not in candidates:
                    candidates.append(f)
        except Exception:
            continue

    profile_candidates = []
    other_candidates = []
    for f in candidates:
        basename = f.rsplit("/", 1)[-1].lower()
        if "profile" in basename:
            profile_candidates.append(f)
        else:
            other_candidates.append(f)
    return profile_candidates[:10] + other_candidates[:10]


def _discover_db_alignment_inputs_remote(
    source_id: str,
    remote_path: str,
    profile_path: Optional[str],
    requested_mapping: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not str(source_id or "").strip():
        raise ValidationError(message="source_id is required", details={"field": "source_id"})
    if not str(remote_path or "").strip():
        raise ValidationError(message="remote_path is required", details={"field": "remote_path"})

    source = get_remote_data_source_service().get_source(source_id)
    provider = build_ssh_file_provider(source)
    dir_listing = provider.list_dir(remote_path)

    filtered_samples: List[Dict[str, Any]] = []
    discovered_chains: set[str] = set()
    preview_columns: List[str] = []
    preview_rows: List[List[Any]] = []
    preview_file_path = ""
    sample_files: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for entry in dir_listing.get("entries") or []:
        name = entry["name"]
        chain = _infer_chain_from_filename(name)
        normalized_chain = _normalize_chain(chain)
        if normalized_chain not in _SUPPORTED_CHAINS:
            continue

        sample_name = name.rsplit("__", 1)[0] if "__" in name else Path(name).stem
        if sample_name not in sample_files:
            sample_files[sample_name] = {}
        if normalized_chain not in sample_files[sample_name]:
            sample_files[sample_name][normalized_chain] = {
                "filename": name,
                "filepath": entry["path"],
                "size": entry.get("size", 0),
                "rows": 0,
                "columns": [],
            }
            discovered_chains.add(normalized_chain)
            if not preview_file_path:
                preview_file_path = entry["path"]

    for sample_name, chain_files in sample_files.items():
        filtered_samples.append({
            "original_name": sample_name,
            "display_name": sample_name,
            "folder_path": remote_path,
            "data_files": list(chain_files.values()),
        })

    if not filtered_samples:
        raise ValidationError(
            message="No TRA/TRB pep files were detected under the selected remote path",
            details={"source_id": source_id, "remote_path": remote_path},
        )

    if preview_file_path:
        try:
            preview_bytes = provider.read_file_bytes(preview_file_path)
            preview_df = pd.read_csv(io.BytesIO(preview_bytes), nrows=20, low_memory=False)
            preview_columns = list(preview_df.columns)
            preview_rows = preview_df.head(10).values.tolist()
            suggested_mapping = {
                "cdr3_column": _find_matching_column(preview_columns, _COLUMN_HINTS["cdr3_column"]),
                "copy_column": _find_matching_column(preview_columns, _COLUMN_HINTS["copy_column"]),
            }
        except Exception:
            preview_file_path = ""
            preview_columns = []
            preview_rows = []
            suggested_mapping = {"cdr3_column": "", "copy_column": ""}
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
            details={"missing_fields": missing_mapping, "available_columns": preview_columns},
        )

    chain_list = sorted(discovered_chains)

    profile_candidates = _discover_remote_profile_csvs(provider, remote_path)
    profile_columns: List[str] = []
    if profile_path and profile_path in profile_candidates:
        try:
            profile_bytes = provider.read_file_bytes(profile_path)
            profile_columns = pd.read_csv(io.BytesIO(profile_bytes), nrows=0).columns.tolist()
        except Exception:
            pass

    sample_preview = [
        {
            "sample_name": sample["display_name"] or sample["original_name"],
            "chains": sorted(chain_files.keys()),
            "file_count": len(chain_files),
        }
        for sample in filtered_samples[:20]
    ]

    return {
        "source_id": source_id,
        "remote_path": remote_path,
        "samples": filtered_samples,
        "sample_count": len(filtered_samples),
        "pep_file_count": sum(len(s["data_files"]) for s in filtered_samples),
        "selected_chains": chain_list,
        "sample_preview": sample_preview,
        "preview_file_path": preview_file_path,
        "preview_columns": preview_columns,
        "preview_rows": preview_rows,
        "suggested_field_mapping": suggested_mapping,
        "resolved_field_mapping": resolved_mapping,
        "profile_candidates": profile_candidates,
        "profile_path": profile_path or "",
        "profile_columns": profile_columns,
        "available_categories": [column for column in profile_columns if str(column).strip().lower() != "sample"],
        "datapoint_candidates": [],
        "source_name": source.name,
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
            details={"base_path": base_path},
        )

    if not discovered_chains:
        raise ValidationError(
            message="DB alignment currently supports TRA/TRB files only",
            details={"base_path": base_path},
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
            },
        )

    invalid_mapping = [value for value in resolved_mapping.values() if value not in preview_columns]
    if invalid_mapping:
        raise ValidationError(
            message="Selected field mapping does not exist in the detected pep file",
            details={"invalid_columns": invalid_mapping, "available_columns": preview_columns},
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
    source_id: Optional[str] = None,
    remote_path: Optional[str] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "Inspect assets", "Scanning pep/Profile inputs for DB alignment", {"module": "db-alignment"})

        if source_id and remote_path:
            discovery = _discover_db_alignment_inputs_remote(source_id, remote_path, profile_path, field_mapping)
            source = get_remote_data_source_service().get_source(source_id)
            ssh_provider = build_ssh_file_provider(source)
        else:
            discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping)
            ssh_provider = None

        _record_stage(
            task_id,
            12,
            "Inspect assets",
            f"Detected {discovery['sample_count']} sample(s) and {len(discovery['selected_chains'])} chain(s)",
            {
                "module": "db-alignment",
                "sample_count": discovery["sample_count"],
                "selected_chains": discovery["selected_chains"],
            },
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
            ssh_file_provider=ssh_provider,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                max(12.0, float(progress or 0.0)),
                stage,
                detail,
                {"module": "db-alignment", **(meta or {})},
            ),
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
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="Completed",
            detail="DB alignment report generated",
            meta={"phase": "completed", "module": "db-alignment"},
            result=result,
            history=history[-80:],
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
            history=history[-80:],
        )


def _discover_boxplot_inputs(base_path: str, datapoint_path: Optional[str], source_id: Optional[str] = None, remote_path: Optional[str] = None) -> Dict[str, Any]:
    if source_id and remote_path:
        if not str(source_id or "").strip():
            raise ValidationError(message="source_id is required", details={"field": "source_id"})
        if not str(remote_path or "").strip():
            raise ValidationError(message="remote_path is required", details={"field": "remote_path"})
        source = get_remote_data_source_service().get_source(source_id)
        provider = build_ssh_file_provider(source)
        file_candidates: List[str] = []
        seen_remote: set[str] = set()
        for pat in ["*.csv", "*.tsv"]:
            found = provider.search_files(remote_path, pat) or []
            for f in found:
                if f not in seen_remote:
                    seen_remote.add(f)
                    file_candidates.append(f)
                    if len(file_candidates) >= 50:
                        break
            if len(file_candidates) >= 50:
                break

        if datapoint_path and datapoint_path.startswith("/") and datapoint_path in seen_remote:
            dp_path = datapoint_path
        elif file_candidates:
            dp_path = file_candidates[0]
        else:
            raise ValidationError(
                message="No CSV/TSV files found under the selected remote path",
                details={"source_id": source_id, "remote_path": remote_path},
            )
        dp_bytes = provider.read_file_bytes(dp_path)
        df = pd.read_csv(io.BytesIO(dp_bytes), nrows=0)
        columns = df.columns.tolist()
        return {
            "source_id": source_id,
            "remote_path": remote_path,
            "datapoint_path": dp_path,
            "columns": columns,
            "column_count": len(columns),
            "suggested_param_begin": columns[0] if columns else "",
            "suggested_param_over": columns[-1] if columns else "",
            "source_name": source.name,
            "file_candidates": file_candidates,
        }

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
            details={"base_path": base_path, "datapoint_path": datapoint_path},
        )
    df = pd.read_csv(datapoint, nrows=0)
    columns = df.columns.tolist()
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
    param_begin: str,
    param_over: str,
    pvalue_threshold: float = 0.05,
    output_name: Optional[str] = None,
    source_id: Optional[str] = None,
    remote_path: Optional[str] = None,
    module_name: str = "boxplot",
) -> None:
    try:
        _record_stage(task_id, 5, "Inspect assets", f"Reading datapoint from {datapoint_path}", {"module": module_name})
        dp_path = str(datapoint_path)
        # Prefer local file; fall back to remote SSH if the file doesn't exist locally
        if Path(dp_path).exists():
            columns = pd.read_csv(dp_path, nrows=0).columns.tolist()
        elif source_id and remote_path:
            source = get_remote_data_source_service().get_source(source_id)
            provider = build_ssh_file_provider(source)
            if not dp_path.startswith("/"):
                dp_path = (Path(remote_path) / dp_path).as_posix() if dp_path else remote_path
            dp_bytes = provider.read_file_bytes(dp_path)
            df = pd.read_csv(io.BytesIO(dp_bytes), nrows=0)
            columns = df.columns.tolist()
            # Write to a local temp file so BoxPlotService can read it
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
            tmp.write(dp_bytes)
            tmp.close()
            dp_path = tmp.name
        else:
            raise FileNotFoundError(f"Datapoint file not found: {dp_path}")

        classification_begin = classification_begin.strip() if classification_begin else columns[0]
        classification_over = classification_over.strip() if classification_over else classification_begin
        if classification_begin not in columns:
            raise ValidationError(message=f"classification_begin column not found: {classification_begin}", details={"available_columns": columns})
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
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                float(progress or 0.0),
                stage,
                detail,
                {"module": module_name, **(meta or {})},
            ),
        )

        png_urls: List[str] = []
        for png_path in report.png_paths:
            rel = Path(png_path).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        pvalue_urls: List[str] = []
        for pv_path in report.pvalue_paths:
            rel = Path(pv_path).relative_to(report.output_base)
            pvalue_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "pvalue_urls": pvalue_urls,
            "metadata_url": f"/api/script-hub/results/{report.job_id}/boxplot_metadata.json",
            "metadata": report.metadata,
        }
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="Completed",
            detail=f"{module_name.title()} generated {len(report.png_paths)} plots",
            meta={"phase": "completed", "module": module_name},
            result=result,
            history=history[-80:],
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
            history=history[-80:],
        )


@script_hub_bp.route("/modules", methods=["GET"])
def list_modules():
    return jsonify(
        {
            "success": True,
            "modules": [
                {
                    "key": "db-alignment",
                    "label": "DB Alignment",
                    "status": "available",
                    "description": "Run VDJdb / McPAS-TCR exact-match analysis directly from pep and Profile assets.",
                },
                {
                    "key": "boxplot",
                    "label": "BoxPlot Analysis",
                    "status": "available",
                    "description": "Generate statistical boxplots with Mann-Whitney U tests from Datapoint CSV output.",
                },
            ],
        }
    )


@script_hub_bp.route("/db-alignment/inspect", methods=["POST"])
def inspect_db_alignment():
    try:
        data = request.get_json() or {}
        source_id = str(data.get("source_id") or "").strip() or None
        remote_path = str(data.get("remote_path") or "").strip() or None

        if source_id and remote_path:
            profile_path = str(data.get("profile_path") or "").strip() or None
            field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else None
            discovery = _discover_db_alignment_inputs_remote(source_id, remote_path, profile_path, field_mapping)
            return jsonify({"success": True, **discovery})

        base_path = str(data.get("base_path") or "").strip()
        profile_path = str(data.get("profile_path") or "").strip() or None
        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else None
        discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping)
        return jsonify({"success": True, **discovery})
    except ValidationError as exc:
        logger.warning("Validation error in inspect_db_alignment: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error inspecting DB alignment inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/db-alignment/run", methods=["POST"])
def run_db_alignment():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "db-alignment").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        base_path = str(data.get("base_path") or "").strip()
        source_id = str(data.get("source_id") or "").strip() or None
        remote_path = str(data.get("remote_path") or "").strip() or None

        if not base_path and not (source_id and remote_path):
            raise ValidationError(message="base_path or source_id+remote_path is required", details={"field": "base_path"})

        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else {}
        output_name = str(data.get("output_name") or "").strip() or None
        profile_path = str(data.get("profile_path") or "").strip() or None
        categories = [str(item).strip() for item in (data.get("categories") or []) if str(item).strip()]
        pathology_values = [str(item).strip() for item in (data.get("pathology_values") or []) if str(item).strip()]
        contained_pathology = _as_bool(data.get("contained_pathology"), False)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "base_path": base_path, "remote_path": remote_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
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
            source_id=source_id,
            remote_path=remote_path,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
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
        source_id = str(data.get("source_id") or "").strip() or None
        remote_path = str(data.get("remote_path") or "").strip() or None
        datapoint_path = str(data.get("datapoint_path") or "").strip() or None
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path, source_id, remote_path)
        return jsonify({"success": True, **discovery})
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

        source_id = str(data.get("source_id") or "").strip() or None
        is_remote = bool(source_id and file_path.startswith("/"))

        if is_remote:
            source = get_remote_data_source_service().get_source(source_id)
            provider = build_ssh_file_provider(source)
            dp_bytes = provider.read_file_bytes(file_path)
            df = pd.read_csv(io.BytesIO(dp_bytes), nrows=0)
        else:
            dp = Path(file_path)
            if not dp.exists() or not dp.is_file():
                raise ValidationError(message="File not found", details={"file_path": file_path})
            df = pd.read_csv(dp, nrows=0)

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


@script_hub_bp.route("/boxplot/run", methods=["POST"])
def run_boxplot():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "boxplot").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        datapoint_path = str(data.get("datapoint_path") or "").strip()
        source_id = str(data.get("source_id") or "").strip() or None
        remote_path = str(data.get("remote_path") or "").strip() or None

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        classification_begin = str(data.get("classification_begin") or "").strip()
        classification_over = str(data.get("classification_over") or "").strip()
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        output_name = str(data.get("output_name") or "").strip() or None

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "datapoint_path": datapoint_path, "remote_path": remote_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
        )

        _script_executor.submit(
            _run_boxplot_task,
            task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            source_id=source_id,
            remote_path=remote_path,
            module_name="boxplot",
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
    except ValidationError as exc:
        logger.warning("Validation error in run_boxplot: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing BoxPlot task: %s", exc, exc_info=True)
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


@script_hub_bp.route("/profile/inspect", methods=["POST"])
def inspect_profile():
    try:
        data = request.get_json() or {}
        source_id = str(data.get("source_id") or "").strip() or None
        remote_path = str(data.get("remote_path") or "").strip() or None
        datapoint_path = str(data.get("datapoint_path") or "").strip() or None
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path, source_id, remote_path)
        suggestions = _suggest_profile_ranges(discovery["columns"])
        discovery.update(suggestions)
        return jsonify({"success": True, **discovery})
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

        source_id = str(data.get("source_id") or "").strip() or None
        is_remote = bool(source_id and file_path.startswith("/"))

        if is_remote:
            source = get_remote_data_source_service().get_source(source_id)
            provider = build_ssh_file_provider(source)
            dp_bytes = provider.read_file_bytes(file_path)
            df = pd.read_csv(io.BytesIO(dp_bytes), nrows=0)
        else:
            dp = Path(file_path)
            if not dp.exists() or not dp.is_file():
                raise ValidationError(message="File not found", details={"file_path": file_path})
            df = pd.read_csv(dp, nrows=0)

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
        datapoint_path = str(data.get("datapoint_path") or "").strip()
        source_id = str(data.get("source_id") or "").strip() or None
        remote_path = str(data.get("remote_path") or "").strip() or None

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required", details={"field": "datapoint_path"})

        grouping_begin = str(data.get("grouping_begin") or "").strip()
        grouping_over = str(data.get("grouping_over") or "").strip()
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        output_name = str(data.get("output_name") or "").strip() or None

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "datapoint_path": datapoint_path, "remote_path": remote_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
        )

        _script_executor.submit(
            _run_boxplot_task,
            task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=grouping_begin,
            classification_over=grouping_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            output_name=output_name,
            source_id=source_id,
            remote_path=remote_path,
            module_name="profile",
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
    except ValidationError as exc:
        logger.warning("Validation error in run_profile: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Profile task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


@script_hub_bp.route("/task/<task_id>", methods=["GET"])
def get_script_hub_task_status(task_id: str):
    task = _get_task_state(task_id)
    if task is None:
        return jsonify({"success": False, "error": "TASK_NOT_FOUND", "message": "Task not found"}), 404
    return jsonify({"success": True, **task})


@script_hub_bp.route("/results/<job_id>/<path:relative_path>", methods=["GET"])
def get_script_hub_result_file(job_id: str, relative_path: str):
    try:
        target_relative = Path(relative_path)
        if target_relative.is_absolute() or ".." in target_relative.parts:
            raise ValidationError(message="Invalid result path", details={"relative_path": relative_path})

        result_root = _resolve_results_root() / _RESULT_DIR / job_id
        target_path = (result_root / target_relative).resolve()
        if result_root.resolve() not in target_path.parents and target_path != result_root.resolve():
            raise ValidationError(message="Invalid result path", details={"relative_path": relative_path})
        if target_path.name not in _RESULT_FILES and target_path.suffix.lower() not in {".csv", ".html", ".json", ".zip", ".png"}:
            raise ValidationError(message="Unsupported result file", details={"relative_path": relative_path})
        if not target_path.exists() or not target_path.is_file():
            raise ValidationError(message="Result file not found", details={"relative_path": relative_path})
        return send_file(target_path)
    except ValidationError as exc:
        logger.warning("Validation error serving script hub result file: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error serving script hub result file: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RESULT_ERROR", "message": str(exc)}), 500
