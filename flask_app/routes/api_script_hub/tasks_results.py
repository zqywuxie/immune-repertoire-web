"""Task status, job management, result serving, and table preview routes."""

import io
import json
import os
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request, send_file

from flask_app.exceptions import ValidationError
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.result_path_resolver import scoped_results_root, candidate_job_roots
from ._common import (
    _RESULT_DIR,
    _RESULT_FILES,
    _collect_project_cached_usage_assets,
    _get_task_state,
    _is_readable_table_asset,
    _looks_like_category_row,
    _mark_script_task_cancelled,
    _normalize_chain,
    _normalize_script_result,
    _read_header_columns,
    _resolve_project_cached_usage_path,
    _resolve_results_root,
    _resolve_usage_data_dir,
    _robust_read_csv,
    _sanitize_nan,
    _script_task_lock,
    _script_tasks,
    _set_task_state,
    _sync_job_state,
    get_script_hub_job_service,
    logger,
)

bp = Blueprint("script_hub_tasks", __name__)

@bp.route("/task/<task_id>", methods=["GET"])
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


@bp.route("/jobs", methods=["GET"])
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


@bp.route("/jobs", methods=["POST"])
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


@bp.route("/jobs/<job_id>", methods=["GET"])
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


@bp.route("/jobs/<job_id>/cancel", methods=["POST"])
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

@bp.route("/cached-usage/<asset_id>/inspect", methods=["GET"])
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


@bp.route("/results/<job_id>/<path:relative_path>", methods=["GET"])
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


@bp.route("/read-table-preview", methods=["POST"])
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
