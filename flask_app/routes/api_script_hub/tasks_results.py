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
    _pep_tra_candidates_from_output_base,
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
    _validate_selected_samples_against_group_values,
    get_script_hub_job_service,
    logger,
)
from .boxplot import run_boxplot
from .enrichment import (
    run_go_kegg_enrichment,
    run_mait_nkt,
    run_ml_analysis,
    run_umap,
    run_umapin,
    run_volcano,
)
from .modules_config import run_db_alignment
from .profile_analysis import (
    run_pep_analysis,
    run_pgen_analysis,
    run_profile,
    run_topclone,
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
    group_error = _validate_required_group_field(module_name, data)
    if group_error:
        return jsonify({
            "success": False,
            "error": "MISSING_GROUP_FIELD",
            "message": "Please select group field / 请选择分组字段",
            "details": group_error,
        }), 400
    cache_error = _validate_required_cache_inputs(module_name, data)
    if cache_error:
        return jsonify({
            "success": False,
            "error": "MISSING_CACHE_INPUT",
            "message": cache_error.get("message") or "Please select required cache input",
            "details": cache_error,
        }), 400
    try:
        _validate_selected_samples_against_group_values(data)
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    return runner()


def _validate_required_group_field(module_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    required_keys = {
        "db-alignment": ["categories"],
        "profile": ["grouptype_fields", "group_fields", "grouping_begin"],
        "boxplot": ["grouptype_fields", "classification_begin"],
        "pep-analysis": ["group_fields", "grouptype_fields"],
        "pgen-analysis": ["distribution_category_col", "group_field"],
        "topclone": ["group_field"],
        "umap": ["group_field", "classification_begin"],
        "umapin": ["category_col"],
        "ml-analysis": ["label_col"],
        "mait-nkt": ["group_field"],
    }.get(module_name, [])
    if not required_keys:
        return {}
    for key in required_keys:
        value = data.get(key)
        if isinstance(value, list) and any(str(item or "").strip() for item in value):
            return {}
        if not isinstance(value, list) and str(value or "").strip():
            return {}
    return {"module": module_name, "accepted_fields": required_keys}


def _validate_required_cache_inputs(module_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if module_name == "volcano" and str(data.get("input_mode") or "").strip() == "usage":
        if not str(data.get("data_dir") or "").strip():
            return {"module": module_name, "field": "data_dir", "message": "Please select PEP VJ usage cache / 请选择 PEP VJ usage 缓存"}
    if module_name == "umapin" and not str(data.get("data_path") or "").strip():
        return {"module": module_name, "field": "data_path", "message": "Please select PEP UMAPin cache / 请选择 PEP UMAPin 缓存"}
    if module_name == "mait-nkt":
        tra_source = str(data.get("tra_source") or "upload").strip()
        if tra_source == "pep_analysis" and not str(data.get("tra_path") or data.get("source_job_id") or "").strip():
            return {"module": module_name, "field": "tra_path", "message": "Please select PEP TRA cache / 请选择 PEP TRA 缓存"}
        if tra_source == "upload" and not str(data.get("tra_path") or "").strip():
            return {"module": module_name, "field": "tra_path", "message": "Please enter TRA CSV path / 请输入 TRA CSV 路径"}
        if data.get("mait_nkt_inspect_ok") is False:
            return {"module": module_name, "field": "mait_nkt_inspect_ok", "message": "MAIT/NKT inspect failed. Please select a valid TRA source before running / MAIT/NKT 检查失败，请先选择有效 TRA 来源"}
    return {}


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


@bp.route("/pep-cache-candidates", methods=["GET"])
def list_pep_cache_candidates():
    project_id = str(request.args.get("project_id") or "").strip()
    cache_type = str(request.args.get("cache_type") or "").strip().lower()
    if not project_id:
        return jsonify({"success": True, "candidates": []})

    accepted = _pep_cache_type_filter(cache_type)
    candidates = _build_pep_cache_candidates(project_id)
    if accepted:
        candidates = [item for item in candidates if item.get("cache_type") in accepted]
    candidates.sort(key=lambda item: (item.get("status") != "available", str(item.get("created_at") or ""), str(item.get("label") or "")))
    return jsonify({"success": True, "candidates": _sanitize_nan(candidates)})


def _pep_cache_type_filter(cache_type: str) -> set[str]:
    mapping = {
        "volcano": {"vj_usage"},
        "vj_usage": {"vj_usage"},
        "usage": {"usage", "vj_usage"},
        "umapin": {"umapin_table", "vj_usage"},
        "umapin_table": {"umapin_table"},
        "mait-nkt": {"tra_shared"},
        "mait": {"tra_shared"},
        "tra": {"tra_shared"},
        "tra_shared": {"tra_shared"},
        "ml-analysis": {"profile", "vj_usage", "umapin_table"},
        "ml-profile": {"profile"},
        "ml-vj": {"vj_usage", "umapin_table"},
        "profile": {"profile"},
    }
    return mapping.get(cache_type, set())


def _build_pep_cache_candidates(project_id: str) -> List[Dict[str, Any]]:
    assets = _collect_project_cached_usage_assets(project_id)
    seen: set[str] = set()
    candidates: List[Dict[str, Any]] = []

    def append_manifest_candidate(candidate: Dict[str, Any]) -> None:
        key = f"{candidate.get('cache_type')}|{candidate.get('usage_type')}|{str(candidate.get('path') or '').lower()}"
        if key in seen:
            return
        seen.add(key)
        candidates.append(candidate)

    for manifest_candidate in _build_pep_manifest_cache_candidates(project_id):
        append_manifest_candidate(manifest_candidate)

    def add_candidate(
        path_value: Any,
        *,
        asset: Dict[str, Any],
        meta: Dict[str, Any],
        cache_type: str,
        usage_type: str,
        label: str = "",
    ) -> None:
        raw = str(path_value or "").strip()
        if not raw:
            return
        path = Path(raw)
        key = f"{cache_type}|{usage_type}|{str(path).lower()}"
        if key in seen:
            return
        seen.add(key)
        file_count = _pep_cache_file_count(path)
        source_job_id = str(meta.get("source_job_id") or meta.get("job_id") or "").strip()
        chain_values = meta.get("chains") if isinstance(meta.get("chains"), list) else []
        candidates.append({
            "id": f"{asset.get('id') or source_job_id or 'pep-cache'}:{len(candidates) + 1}",
            "asset_id": asset.get("id"),
            "job_id": source_job_id,
            "source": asset.get("source") or meta.get("source") or "project",
            "source_module": meta.get("source_module") or "pep-analysis",
            "cache_type": cache_type,
            "usage_type": usage_type,
            "label": label or _pep_cache_label(source_job_id, usage_type, cache_type),
            "path": str(path.resolve()) if path.exists() else raw,
            "path_summary": _pep_cache_path_summary(path),
            "file_count": file_count,
            "status": "available" if file_count > 0 else "missing",
            "chains": chain_values,
            "group_field": meta.get("group_field") or "",
            "group_fields": meta.get("group_fields") if isinstance(meta.get("group_fields"), list) else [],
            "created_at": asset.get("created_at") or meta.get("created_at") or "",
        })

    for asset in assets:
        meta = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
        if str(meta.get("source_module") or "pep-analysis").strip() != "pep-analysis":
            continue
        storage_path = str(asset.get("storage_path") or meta.get("storage_path") or "").strip()
        usage_types = meta.get("usage_types") if isinstance(meta.get("usage_types"), dict) else {}
        for usage_name, usage_path in usage_types.items():
            usage_key = str(usage_name or "").strip()
            cache_type = "vj_usage" if "VJ" in usage_key.upper() else "usage"
            add_candidate(usage_path, asset=asset, meta=meta, cache_type=cache_type, usage_type=usage_key)

        for key, usage_type in (
            ("volcano_data_dir", "VJ usage"),
            ("usage_1vj_path", "1VJusage"),
            ("usage_0vj_path", "0VJusage"),
        ):
            add_candidate(meta.get(key), asset=asset, meta=meta, cache_type="vj_usage", usage_type=usage_type)

        for key, usage_type in (
            ("umapin_data_path", "VJ summary"),
            ("df_vj_all_path", "df_VJ_all"),
            ("df_VJ_all_path", "df_VJ_all"),
            ("df_1vj_all_path", "df_1VJusage_all"),
        ):
            add_candidate(meta.get(key), asset=asset, meta=meta, cache_type="umapin_table", usage_type=usage_type)

        for key, usage_type in (
            ("pep_shared_TRA_path", "TRA shared"),
            ("pep_shared_cate_TRA_path", "TRA shared by group"),
        ):
            add_candidate(meta.get(key), asset=asset, meta=meta, cache_type="tra_shared", usage_type=usage_type)

        for base_key in ("pep_output_base", "output_base", "output_dir"):
            base_raw = str(meta.get(base_key) or "").strip()
            if not base_raw:
                continue
            for tra_path in _pep_tra_candidates_from_output_base(Path(base_raw)):
                add_candidate(tra_path, asset=asset, meta=meta, cache_type="tra_shared", usage_type="TRA shared")

        if storage_path:
            base = Path(storage_path)
            for usage_dir in (base, base / "1VJusage", base / "0VJusage", base.parent / "0VJusage", base.parent / "1VJusage"):
                add_candidate(usage_dir, asset=asset, meta=meta, cache_type="vj_usage", usage_type=usage_dir.name or "VJ usage")

    return candidates


def _build_pep_manifest_cache_candidates(project_id: str) -> List[Dict[str, Any]]:
    registry_entries = _read_pep_cache_registry(project_id)
    candidates: List[Dict[str, Any]] = []
    for entry in registry_entries:
        manifest = _read_pep_cache_manifest(entry)
        if not manifest:
            continue
        output_files = manifest.get("output_files") if isinstance(manifest.get("output_files"), dict) else {}
        chains = manifest.get("chains") if isinstance(manifest.get("chains"), list) else []
        group_fields = manifest.get("group_fields") if isinstance(manifest.get("group_fields"), list) else []
        base = {
            "asset_id": manifest.get("cache_id") or entry.get("cache_id") or "",
            "job_id": manifest.get("job_id") or entry.get("job_id") or "",
            "source": "cache_manifest",
            "source_module": "pep-analysis",
            "chains": chains,
            "group_fields": group_fields,
            "group_field": group_fields[0] if group_fields else "",
            "created_at": manifest.get("created_at") or entry.get("created_at") or "",
            "sample_count": manifest.get("sample_count") or entry.get("sample_count") or 0,
            "data_types": _pep_manifest_data_types(manifest),
            "available_for": [
                key for key, enabled in (manifest.get("downstream") or {}).items()
                if enabled
            ],
            "status": "available",
        }

        profile_path = str(manifest.get("profile_path") or "").strip()
        if profile_path:
            candidates.append(_manifest_candidate(base, profile_path, "profile", "Profile", "Profile metadata"))

        usage_types = output_files.get("usage_types") if isinstance(output_files.get("usage_types"), dict) else {}
        for usage_type, path_value in usage_types.items():
            usage_key = str(usage_type or "").strip()
            cache_type = "vj_usage" if "VJ" in usage_key.upper() else "usage"
            candidates.append(_manifest_candidate(base, path_value, cache_type, usage_key, usage_key))

        umapin_tables = output_files.get("umapin_tables") if isinstance(output_files.get("umapin_tables"), dict) else {}
        for usage_type, path_value in umapin_tables.items():
            if str(path_value or "").strip():
                candidates.append(_manifest_candidate(base, path_value, "umapin_table", usage_type, usage_type))

        pep_shared = output_files.get("pep_shared") if isinstance(output_files.get("pep_shared"), dict) else {}
        if pep_shared.get("TRA"):
            candidates.append(_manifest_candidate(base, pep_shared.get("TRA"), "tra_shared", "TRA shared", "TRA shared"))

    return candidates


def _manifest_candidate(base: Dict[str, Any], path_value: Any, cache_type: str, usage_type: str, label: str) -> Dict[str, Any]:
    raw = str(path_value or "").strip()
    path = Path(raw)
    job_id = str(base.get("job_id") or "")
    file_count = _pep_cache_file_count(path)
    status = "available" if file_count > 0 else "missing"
    if cache_type == "profile" and path.exists() and path.is_file():
        file_count = 1
        status = "available"
    return {
        **base,
        "id": f"{base.get('asset_id') or job_id or 'pep-cache'}:{cache_type}:{usage_type}",
        "cache_type": cache_type,
        "usage_type": usage_type,
        "label": f"{job_id or 'PEP cache'} {label}",
        "path": str(path.resolve()) if path.exists() else raw,
        "path_summary": _pep_cache_path_summary(path),
        "file_count": file_count,
        "status": status,
    }


def _read_pep_cache_registry(project_id: str) -> List[Dict[str, Any]]:
    registry_path = _resolve_results_root() / _RESULT_DIR / "cache_registry.json"
    entries: List[Dict[str, Any]] = []
    try:
        if registry_path.exists():
            loaded = json.loads(registry_path.read_text(encoding="utf-8"))
            raw_entries = loaded.get("entries") if isinstance(loaded, dict) else loaded
            if isinstance(raw_entries, list):
                entries = [item for item in raw_entries if isinstance(item, dict)]
    except Exception:
        logger.warning("Failed to read PEP cache registry %s", registry_path, exc_info=True)
    project_key = str(project_id or "").strip()
    return [
        item for item in entries
        if not str(item.get("project_id") or "").strip() or str(item.get("project_id") or "").strip() == project_key
    ]


def _read_pep_cache_manifest(entry: Dict[str, Any]) -> Dict[str, Any]:
    for value in (entry.get("manifest_path"), Path(str(entry.get("output_base") or "")) / "cache_manifest.json"):
        path = Path(str(value or ""))
        try:
            if path.exists() and path.is_file():
                loaded = json.loads(path.read_text(encoding="utf-8"))
                return loaded if isinstance(loaded, dict) else {}
        except Exception:
            logger.warning("Failed to read PEP cache manifest %s", path, exc_info=True)
    return {}


def _pep_manifest_data_types(manifest: Dict[str, Any]) -> List[str]:
    values = []
    if manifest.get("has_profile"):
        values.append("Profile")
    if manifest.get("has_vj_usage"):
        values.append("VJ usage")
    if manifest.get("has_mait_nkt_tra"):
        values.append("TRA")
    return values


def _pep_cache_label(source_job_id: str, usage_type: str, cache_type: str) -> str:
    prefix = source_job_id or "PEP cache"
    if cache_type == "tra_shared":
        return f"{prefix} TRA"
    if cache_type == "umapin_table":
        return f"{prefix} UMAPin"
    return f"{prefix} {usage_type or 'usage'}"


def _pep_cache_file_count(path: Path) -> int:
    try:
        if path.exists() and path.is_file():
            return 1 if path.suffix.lower() in {".csv", ".gz", ".tsv", ".xlsx"} else 0
        if path.exists() and path.is_dir():
            return len([item for item in path.iterdir() if item.is_file() and item.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz", ".xlsx"))])
    except OSError:
        return 0
    return 0


def _pep_cache_path_summary(path: Path) -> str:
    parts = [part for part in path.parts if part not in ("\\", "/")]
    return str(Path(*parts[-4:])) if parts else str(path)


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
