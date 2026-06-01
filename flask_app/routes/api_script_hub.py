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
from flask_app.services.boxplot_service import BoxPlotService
from flask_app.services.pep_analysis_service import PepAnalysisService
from flask_app.services.topclone_service import TopCloneService
from flask_app.services.umap_service import UmapService
from flask_app.services.volcano_service import VolcanoService
from flask_app.services.umapin_service import UmapinService

logger = logging.getLogger(__name__)

script_hub_bp = Blueprint("script_hub", __name__, url_prefix="/api/script-hub")
_script_executor = ThreadPoolExecutor(max_workers=2)
_script_task_lock = threading.Lock()
_script_tasks: Dict[str, Dict[str, Any]] = {}

_RESULT_DIR = "script_hub"
_ALLOWED_MODULES = {"db-alignment", "boxplot", "topclone", "pep-analysis", "umap", "volcano", "umapin"}
_COLUMN_HINTS = {
    "cdr3_column": ["cdr3(pep)", "cdr3_pep", "cdr3aa", "cdr3_aa", "cdr3", "aminoacid", "sequence"],
    "copy_column": ["copy", "copies", "count", "reads", "umis", "umi", "frequency"],
}
_SUPPORTED_CHAINS = {"TRA", "TRB"}
_SUPPORTED_CHAINS_WIDE = {"IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"}
_RESULT_FILES = {"viewer.html", "metadata.json", "db_alignment_bundle.zip", "specify_ratio.csv", "specify_ratio_with_profile.csv", "alignment_summary.csv", "pep_analysis_metadata.json", "pep_analysis_results.zip", "boxplot_results.zip", "topclone_results.zip"}


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


def _sanitize_nan(obj: Any) -> Any:
    """Recursively replace float('nan')/inf with None for JSON compliance."""
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_nan(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
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
    pathology_values: List[str]
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
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="Completed",
            detail="DB alignment report generated",
            meta={"phase": "completed", "module": "db-alignment"},
            result=result,
            history=history[-80:]
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
    grouptype_fields: Optional[List[str]] = None,
    param_begin: str,
    param_over: str,
    group_order: Optional[str] = None,
    pvalue_threshold: float = 0.05,
    output_name: Optional[str] = None,
    module_name: str = "boxplot"
) -> None:
    try:
        _record_stage(task_id, 5, "Inspect assets", f"Reading datapoint from {datapoint_path}", {"module": module_name})
        dp_path = str(datapoint_path)
        if not Path(dp_path).exists():
            raise FileNotFoundError(f"Datapoint file not found: {dp_path}")
        columns = pd.read_csv(dp_path, nrows=0).columns.tolist()

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

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "pvalue_urls": pvalue_urls,
            "csv_urls": csv_urls,
            "significant_urls": sig_urls,
            "zip_url": zip_url,
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
            history=history[-80:]
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
                df = pd.read_csv(target, nrows=0)
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
                    "key": "charts",
                    "label": "综合图表报告",
                    "status": "available",
                    "description": "复用项目数据选择流程，进入 Heatmap / Treemap / Chord 的图表报告配置。",
                },
                {
                    "key": "db-alignment",
                    "label": "数据库比对",
                    "status": "available",
                    "description": "基于 pep 和 Profile 数据，与 VDJdb / McPAS-TCR 公共数据库做精确匹配分析。",
                },
                {
                    "key": "boxplot",
                    "label": "箱线图分析",
                    "status": "available",
                    "description": "从 Datapoint CSV 生成分组箱线图，附带 Mann-Whitney U 统计检验。",
                },
                {
                    "key": "pep-analysis",
                    "label": "CDR3 共享分析",
                    "status": "available",
                    "description": "CDR3 共享矩阵、V/J/VJ 使用频率、分组比较热图和 CDR3 分类。",
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
                    "description": "对 VJ usage 数据做两组间差异比较，生成火山图（log2FC vs -log10 p-value）。",
                },
                {
                    "key": "umapin",
                    "label": "UMAPin 降维",
                    "status": "available",
                    "description": "基于 VJ usage 拼接数据做 UMAP 降维投影，可选 FDR 多重检验校正。",
                },
            ],
        }
    )


@script_hub_bp.route("/db-alignment/inspect", methods=["POST"])
def inspect_db_alignment():
    try:
        data = request.get_json() or {}
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

        if not base_path:
            raise ValidationError(message="base_path is required", details={"field": "base_path"})

        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else {}
        output_name = str(data.get("output_name") or "").strip() or None
        profile_path = str(data.get("profile_path") or "").strip() or None
        categories = [str(item).strip() for item in (data.get("categories") or []) if str(item).strip()]
        pathology_values = [str(item).strip() for item in (data.get("pathology_values") or []) if str(item).strip()]
        contained_pathology = _as_bool(data.get("contained_pathology"), False)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "base_path": base_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)]
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
            pathology_values=pathology_values
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
        datapoint_path = str(data.get("datapoint_path") or "").strip() or None
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path)
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
        df = pd.read_csv(dp)

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
        df = pd.read_csv(dp)

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

        datapoint_path = str(data.get("datapoint_path") or "").strip()

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

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "datapoint_path": datapoint_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)]
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
            module_name="boxplot"
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
    except ValidationError as exc:
        logger.warning("Validation error in run_boxplot: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing BoxPlot task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---------------------------------------------------------------------------
# TopClone task
# ---------------------------------------------------------------------------

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
    output_name: Optional[str] = None,
    module_name: str = "topclone"
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
            "per_sample_count": len(report.per_sample_files),
            "metadata": report.metadata,
        }

        if report.topclone_csv_path:
            rel = Path(report.topclone_csv_path).relative_to(report.output_base)
            result["topclone_csv_url"] = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        if report.boxplot_report:
            bp = report.boxplot_report
            for png_path in bp.png_paths:
                rel = Path(png_path).relative_to(bp.output_base)
                result["png_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            for pv_path in bp.pvalue_paths:
                rel = Path(pv_path).relative_to(bp.output_base)
                result["pvalue_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            for csv_path in bp.csv_paths:
                rel = Path(csv_path).relative_to(bp.output_base)
                result["csv_urls"].append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="Completed",
            detail=f"TopClone generated {len(result['png_urls'])} boxplots",
            meta={"phase": "completed", "module": module_name},
            result=result,
            history=history[-80:]
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
        pep_data_path = str(data.get("pep_data_path") or "").strip()
        if not pep_data_path:
            raise ValidationError(message="pep_data_path is required", details={"field": "pep_data_path"})
        datapoint_path = str(data.get("datapoint_path") or "").strip()

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

        pep_data_path = str(data.get("pep_data_path") or "").strip()
        datapoint_path = str(data.get("datapoint_path") or "").strip()
        mode = str(data.get("mode") or "trace").strip()
        top_n = int(data.get("top_n") or 10)
        group_field = str(data.get("group_field") or "").strip() or None
        group_order = str(data.get("group_order") or "").strip() or None
        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        output_name = str(data.get("output_name") or "").strip() or None

        if not pep_data_path:
            raise ValidationError(message="pep_data_path is required", details={"field": "pep_data_path"})
        if mode == "trace" and not datapoint_path:
            raise ValidationError(message="datapoint_path is required for trace mode", details={"field": "datapoint_path"})

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_path": pep_data_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)]
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
            output_name=output_name,
            module_name=module_name
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
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


@script_hub_bp.route("/profile/inspect", methods=["POST"])
def inspect_profile():
    try:
        data = request.get_json() or {}
        datapoint_path = str(data.get("datapoint_path") or "").strip() or None
        base_path = str(data.get("base_path") or "").strip()

        discovery = _discover_boxplot_inputs(base_path, datapoint_path)
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


        if is_remote:
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

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)]
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
            module_name="profile"
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
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
        base_path = str(data.get("base_path") or "").strip()

        # Discover pep files: {Sample}__{Chain}.csv
        discovered_chains: set[str] = set()
        sample_names: set[str] = set()
        pep_file_count = 0

        if not discovered_chains:
            raise ValidationError(
                message="No pep files detected. Expected format: {Sample}__{Chain}.csv",
                details={"base_path": base_path}
            )

        chain_list = sorted(discovered_chains)
        return jsonify({
            "success": True,
            "base_path": base_path,
            "chains": chain_list,
            "chain_count": len(chain_list),
            "sample_count": len(sample_names),
            "pep_file_count": pep_file_count,
            "profile_candidates": profile_candidates[:10],
            "profile_columns": profile_columns,
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

        pep_data_dir = str(data.get("pep_data_dir") or "").strip()
        profile_path = str(data.get("profile_path") or "").strip()
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
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "pep_data_dir": pep_data_dir}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)]
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
            output_name=output_name,
            project_id=project_id
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
    except ValidationError as exc:
        logger.warning("Validation error in run_pep_analysis: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error queuing Pep analysis task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _cache_pep_usage_assets(
    project_id: str,
    job_id: str,
    output_base: str,
    selected_chains: List[str],
    group_fields: List[str],
    pep_data_dir: str,
    profile_path: str,
    projects_root: Path
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
        usage_types = {}
        for sub in ["1Vusage", "1Jusage", "1VJusage", "0Vusage", "0Jusage", "0VJusage"]:
            sub_path = usage_dir / sub
            if sub_path.exists() and sub_path.is_dir():
                usage_types[sub] = str(sub_path)

        if not usage_types:
            logger.info("No usage subdirectories found in %s", usage_dir)
            return

        metadata = {
            "source_job_id": job_id,
            "source_module": "pep-analysis",
            "chains": selected_chains,
            "group_fields": group_fields,
            "usage_types": usage_types,
            "pep_data_dir": pep_data_dir,
            "profile_path": profile_path,
        }

        asset = asset_service.register_cached_asset(
            project=project,
            asset_type="cached_usage",
            storage_path=str(usage_dir),
            metadata=metadata,
            original_name=f"pep_usage_{job_id}"
        )
        logger.info("Cached pep usage asset %s for project %s", asset.id, project_id)
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
    output_name: Optional[str] = None,
    project_id: Optional[str] = None
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
            "arrange_heatmap_urls": [_url(p) for p in report.arrange_heatmap_paths],
            "zip_url": _url(report.zip_path),
            "metadata_url": f"/api/script-hub/results/{report.job_id}/pep_analysis_metadata.json",
            "metadata": report.metadata,
        }

        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="completed",
            progress=100.0,
            stage="Completed",
            detail=f"Pep analysis completed: {len(report.shared_matrix_paths)} shared matrices, "
                   f"{len(report.heatmap_image_paths)} heatmaps, {len(report.arrange_heatmap_paths)} arrange heatmaps",
            meta={"phase": "completed", "module": "pep-analysis"},
            result=result,
            history=history[-80:]
        )

        # Cache usage data as project asset if project_id provided
        if project_id:
            _cache_pep_usage_assets(
                project_id=project_id,
                job_id=report.job_id,
                output_base=str(report.output_base),
                selected_chains=selected_chains,
                group_fields=group_fields,
                pep_data_dir=pep_data_dir,
                profile_path=profile_path,
                projects_root=results_root.parent / "projects"
            )
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
        return jsonify({"success": False, "error": "TASK_NOT_FOUND", "message": "Task not found"}), 404
    return jsonify({"success": True, **_sanitize_nan(task)})


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
    module_name: str = "umap"
) -> None:
    try:
        _record_stage(task_id, 5, "UMAP inspect", f"Reading {datapoint_path}", {"module": module_name})
        dp_path = str(datapoint_path)
        if Path(dp_path).exists():
            columns = pd.read_csv(dp_path, nrows=0).columns.tolist()
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
            "csv_urls": csv_urls,
            "zip_url": zip_url,
            "metadata": report.metadata,
        }
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="completed", progress=100.0, stage="Completed",
                        detail=f"UMAP generated {len(report.png_paths)} plots",
                        meta={"phase": "completed", "module": module_name},
                        result=result, history=history[-80:])
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
        datapoint_path = str(data.get("datapoint_path") or "").strip()
        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required")

        columns = df.columns.tolist()
        return jsonify({
            "success": True,
            "datapoint_path": resolved_path,
            "columns": columns,
            "column_count": len(columns),
            "suggested_param_begin": columns[0] if columns else "",
            "suggested_param_over": columns[-1] if columns else "",
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
        datapoint_path = str(data.get("datapoint_path") or "").strip()
        classification_begin = str(data.get("classification_begin") or "").strip()
        classification_over = str(data.get("classification_over") or "").strip()
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not datapoint_path:
            raise ValidationError(message="datapoint_path is required")
        if not param_begin or not param_over:
            raise ValidationError(message="param_begin and param_over are required")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        n_neighbors = int(data.get("n_neighbors") or 6)
        min_dist = float(data.get("min_dist") or 0.01)
        output_name = str(data.get("output_name") or "").strip() or None

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="Queued",
                        detail="Task created", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "Queued", "Task created", {"phase": "queued", "module": module_name})])

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
            module_name=module_name
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Volcano Analysis ----

@script_hub_bp.route("/volcano/inspect", methods=["POST"])
def inspect_volcano():
    try:
        data = request.get_json() or {}
        data_dir = str(data.get("data_dir") or "").strip()

        return jsonify({
            "success": True,
            "data_dir": data_dir,
            "file_count": len(file_list),
            "files": file_list[:20],
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
    pvalue_threshold: float = 0.05,
    module_name: str = "volcano"
) -> None:
    try:
        _record_stage(task_id, 5, "火山图分析", f"扫描 {data_dir}", {"module": module_name})

        local_data_dir = data_dir

        service = VolcanoService(output_parent=results_root / _RESULT_DIR)
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
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="completed", progress=100.0, stage="完成",
                        detail=f"火山图分析完成，生成 {len(png_urls)} 张图",
                        meta={"phase": "completed", "module": module_name},
                        result=result, history=history[-80:])
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
        data_dir = str(data.get("data_dir") or "").strip()
        if not data_dir:
            raise ValidationError(message="data_dir is required", details={"field": "data_dir"})

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})])

        _script_executor.submit(
            _run_volcano_task, task_id,
            results_root=_resolve_results_root(),
            data_dir=data_dir,
            pvalue_threshold=pvalue_threshold,
            module_name=module_name
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- UMAPin Analysis ----

@script_hub_bp.route("/umapin/inspect", methods=["POST"])
def inspect_umapin():
    try:
        data = request.get_json() or {}
        data_path = str(data.get("data_path") or "").strip()
        if not data_path:
            base_path = str(data.get("base_path") or "").strip()
            if base_path:
                data_path = base_path
            else:
                raise ValidationError(message="data_path or base_path is required", details={"field": "data_path"})


        columns = df.columns.tolist()
        cat_candidates = [c for c in columns if c.lower() in ("category", "group", "therapy", "disease")]
        category_col = cat_candidates[0] if cat_candidates else ""

        return jsonify({
            "success": True,
            "data_path": resolved_path,
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
    module_name: str = "umapin"
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
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="completed", progress=100.0, stage="完成",
                        detail=f"UMAPin 完成，{len(png_urls)} 张图",
                        meta={"phase": "completed", "module": module_name},
                        result=result, history=history[-80:])
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
        data_path = str(data.get("data_path") or "").strip()
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

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})])

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
            module_name=module_name
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}"})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


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
        if target_path.name not in _RESULT_FILES and target_path.suffix.lower() not in {".csv", ".html", ".json", ".zip", ".png", ".jpg"}:
            raise ValidationError(message="Unsupported result file", details={"relative_path": relative_path})
        if not target_path.exists() or not target_path.is_file():
            raise ValidationError(message="Result file not found", details={"relative_path": relative_path})
        as_attachment = target_path.suffix.lower() == ".zip"
        return send_file(target_path, as_attachment=as_attachment)
    except ValidationError as exc:
        logger.warning("Validation error serving script hub result file: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error serving script hub result file: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RESULT_ERROR", "message": str(exc)}), 500
