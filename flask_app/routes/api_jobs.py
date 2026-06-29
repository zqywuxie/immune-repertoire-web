"""Global background job API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from flask_app.models.database import ProjectAsset
from flask_app.services.background_job_service import TERMINAL_STATUSES, get_background_job_service
from flask_app.services.api_job_runner import ALLOWED_API_JOBS, get_job_runner
from flask_app.services.job_queue import get_job_queue
from flask_app.services.user_scope import current_user_id, is_admin


jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_error(error_code: str, message: str, status_code: int = 500, **details: Any):
    payload = {
        "success": False,
        "error": error_code,
        "message": message,
    }
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


def _sse_event(event: str, data: Dict[str, Any], *, event_id: str = "") -> str:
    parts = []
    if event_id:
        parts.append(f"id: {event_id}")
    if event:
        parts.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, default=str)
    for line in payload.splitlines() or [""]:
        parts.append(f"data: {line}")
    return "\n".join(parts) + "\n\n"


def _sse_comment(value: str) -> str:
    return f": {value}\n\n"


def _event_stream_interval() -> float:
    try:
        requested = float(request.args.get("interval", 1.0))
    except (TypeError, ValueError):
        requested = 1.0
    return max(0.2, min(requested, 30.0))


def _event_stream_max_events() -> int:
    try:
        requested = int(request.args.get("max_events", 300))
    except (TypeError, ValueError):
        requested = 300
    return max(1, min(requested, 1000))


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


def _build_charts_cache_context(project_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    project_id = str(project_id or "").strip()
    selected = [str(item) for item in payload.get("selected_modules") or ["heatmap", "treemap", "chord"]]
    samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
    input_paths: List[str] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        for file_info in sample.get("data_files") or []:
            if isinstance(file_info, dict) and str(file_info.get("filepath") or "").strip():
                input_paths.append(str(file_info.get("filepath")).strip())
        if str(sample.get("folder_path") or "").strip():
            input_paths.append(str(sample.get("folder_path")).strip())
    input_assets = [
        _analysis_input_descriptor(path, "sample")
        for path in sorted(dict.fromkeys(input_paths))
    ]
    transcriptome_path = str(payload.get("transcriptome_path") or "").strip()
    if transcriptome_path:
        input_assets.append(_analysis_input_descriptor(transcriptome_path, "transcriptome"))
    config_json = {
        "selected_modules": sorted(selected),
        "selected_chains": [str(item) for item in payload.get("selected_chains") or []],
        "field_mapping": payload.get("field_mapping") if isinstance(payload.get("field_mapping"), dict) else {},
        "sample_count": len(samples),
        "sample_keys": sorted(str(sample.get("sample_key") or sample.get("display_name") or sample.get("original_name") or "") for sample in samples if isinstance(sample, dict)),
        "has_transcriptome": bool(transcriptome_path),
    }
    if not project_id:
        return {"project_id": "", "analysis_signature": "", "input_assets": input_assets, "config_json": config_json}
    try:
        from flask_app.services.mongo_service import build_analysis_signature
        analysis_signature = build_analysis_signature(
            project_id=project_id,
            analysis_type="charts.combined",
            input_assets=input_assets,
            config_json=config_json,
        )
    except Exception:
        analysis_signature = ""
    return {
        "project_id": project_id,
        "analysis_signature": analysis_signature,
        "input_assets": input_assets,
        "config_json": config_json,
    }


def _mongo_result_to_charts_result(doc: Dict[str, Any]) -> Dict[str, Any]:
    metadata = doc.get("metadata_json") if isinstance(doc.get("metadata_json"), dict) else {}
    return {
        "module": "charts.combined",
        "job_id": doc.get("job_id", ""),
        "viewer_url": doc.get("viewer_url", ""),
        "zip_url": doc.get("zip_url", ""),
        "output_base": doc.get("output_base", ""),
        "chart_results": metadata.get("chart_results", []),
        "metadata": metadata.get("metadata", metadata),
        "analysis_signature": doc.get("analysis_signature", ""),
        "result_id": str(doc.get("_id") or ""),
        "reused_result": True,
    }


def _find_reusable_charts_result(cache_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    project_id = cache_context.get("project_id") or ""
    signature = cache_context.get("analysis_signature") or ""
    if not project_id or not signature:
        return None
    try:
        from flask_app.services.mongo_service import find_result_by_signature
        doc = find_result_by_signature(project_id, "charts.combined", signature)
    except Exception:
        return None
    return _mongo_result_to_charts_result(doc) if doc else None


def _can_access_job(job: Dict[str, Any]) -> bool:
    return is_admin() or job.get("user_id") in {None, current_user_id()}


def _append_output(outputs: List[Dict[str, Any]], seen: set[str], *, label: str, url: str, kind: str) -> None:
    url = str(url or "").strip()
    if not url or url in seen:
        return
    seen.add(url)
    outputs.append({
        "label": label,
        "url": url,
        "kind": kind,
    })


def _collect_result_outputs(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    _append_output(outputs, seen, label="Viewer", url=result.get("viewer_url", ""), kind="html")
    _append_output(outputs, seen, label="Bundle", url=result.get("zip_url", ""), kind="zip")
    for item in result.get("chart_results") or []:
        if not isinstance(item, dict):
            continue
        module = str(item.get("module") or item.get("name") or "Result")
        _append_output(outputs, seen, label=f"{module} viewer", url=item.get("viewer_url", ""), kind="html")
        _append_output(outputs, seen, label=f"{module} bundle", url=item.get("zip_url", ""), kind="zip")
    for item in result.get("files") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or item.get("kind") or "File")
        _append_output(outputs, seen, label=label, url=item.get("url", ""), kind=str(item.get("kind") or "file"))
    return outputs


def _job_result_assets(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    project_id = str(job.get("project_id") or "").strip()
    if not project_id:
        return []
    candidates = ProjectAsset.query.filter(
        ProjectAsset.project_id == project_id,
        ProjectAsset.asset_type == "processed_result",
    ).order_by(ProjectAsset.uploaded_at.desc()).limit(100).all()
    matched: List[Dict[str, Any]] = []
    job_id = str(job.get("job_id") or job.get("id") or "").strip()
    module = str(job.get("module") or "").strip()
    for asset in candidates:
        metadata = asset.metadata_json or {}
        if metadata.get("job_id") == job_id or metadata.get("task_id") == job_id or metadata.get("analysis_type") == module:
            item = asset.to_dict()
            item["preview_url"] = f"/api/assets/{asset.id}/preview"
            item["download_url"] = f"/api/assets/{asset.id}/download"
            matched.append(item)
    return matched


@jobs_bp.route("", methods=["POST"])
def create_job():
    data = request.get_json() or {}
    module = str(data.get("module") or "").strip()
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    project_id = str(data.get("project_id") or payload.get("project_id") or "").strip() or None
    if module not in ALLOWED_API_JOBS:
        return jsonify({
            "success": False,
            "error": "UNSUPPORTED_JOB_MODULE",
            "message": f"Unsupported background job module: {module or '-'}",
            "supported_modules": sorted(ALLOWED_API_JOBS),
        }), 400

    service = get_background_job_service()
    user_id = current_user_id()
    if module == "charts.combined":
        cache_context = _build_charts_cache_context(project_id, payload)
        if not _truthy(data.get("force_rerun")) and not _truthy(payload.get("force_rerun")):
            cached_result = _find_reusable_charts_result(cache_context)
            if cached_result:
                return jsonify({
                    "success": True,
                    "job_id": cached_result.get("job_id"),
                    "task_id": cached_result.get("job_id"),
                    "status": "completed",
                    "reused_result": True,
                    "analysis_signature": cache_context.get("analysis_signature", ""),
                    "result_id": cached_result.get("result_id", ""),
                    "result": cached_result,
                })
        payload = {
            **payload,
            **cache_context,
            "_project_id": project_id,
        }
    job = service.create_job(
        job_type="api_request",
        module=module,
        payload=payload,
        user_id=user_id,
        project_id=project_id,
    )
    queue = get_job_queue()
    queue.submit(job["job_id"], get_job_runner(module))
    return jsonify({
        "success": True,
        "job_id": job["job_id"],
        "task_id": job["job_id"],
        "status_url": f"/api/jobs/{job['job_id']}",
        "status": job["status"],
    })


@jobs_bp.route("", methods=["GET"])
def list_jobs():
    try:
        service = get_background_job_service()
        include_children = _truthy(request.args.get("include_children"))
        jobs = service.list_jobs(
            module=request.args.get("module") or None,
            project_id=request.args.get("project_id") or None,
            status=request.args.get("status") or None,
            user_id=current_user_id(),
            include_admin_scope=is_admin(),
            include_children=include_children,
            limit=request.args.get("limit", default=100, type=int) or 100,
        )
        return jsonify({"success": True, "jobs": jobs})
    except Exception as exc:
        current_app.logger.error("Failed to list background jobs: %s", exc, exc_info=True)
        return _json_error(
            "JOBS_LIST_ERROR",
            "Failed to load background jobs. If this is a local database, run migrations/add_analysis_jobs.py --apply and restart the server.",
            detail=str(exc),
        )


@jobs_bp.route("/modules", methods=["GET"])
def list_job_modules():
    labels = {
        "charts.combined": "综合图表",
    }
    visible_modules = ["charts.combined"]
    return jsonify({
        "success": True,
        "modules": [
            {"key": key, "label": labels.get(key, key.replace(".", " / "))}
            for key in visible_modules
            if key in ALLOWED_API_JOBS
        ],
    })


@jobs_bp.route("/<job_id>", methods=["GET"])
def get_job(job_id: str):
    try:
        job = get_background_job_service().get_job(job_id)
        if job is None:
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if not _can_access_job(job):
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        return jsonify({"success": True, "job": job, **job})
    except Exception as exc:
        current_app.logger.error("Failed to get background job %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_GET_ERROR", "Failed to load background job.", detail=str(exc))


@jobs_bp.route("/<job_id>/events", methods=["GET"])
def stream_job_events(job_id: str):
    service = get_background_job_service()
    job = service.get_job(job_id)
    if job is None:
        return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
    if not _can_access_job(job):
        return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404

    interval = _event_stream_interval()
    max_events = _event_stream_max_events()

    @stream_with_context
    def generate():
        last_payload = ""
        sent_events = 0
        while sent_events < max_events:
            current = service.get_job(job_id)
            if current is None:
                yield _sse_event("error", {
                    "success": False,
                    "error": "JOB_NOT_FOUND",
                    "message": "Job not found",
                }, event_id=job_id)
                break

            status = str(current.get("status") or "")
            event_name = "completed" if status in TERMINAL_STATUSES else "update"
            payload = {
                "success": True,
                "job": current,
                "status": status,
            }
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            if serialized != last_payload:
                yield _sse_event(event_name, payload, event_id=job_id)
                last_payload = serialized
                sent_events += 1
            else:
                yield _sse_comment("heartbeat")

            if status in TERMINAL_STATUSES:
                break
            time.sleep(interval)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@jobs_bp.route("/<job_id>/results", methods=["GET"])
def get_job_results(job_id: str):
    try:
        job = get_background_job_service().get_job(job_id)
        if job is None:
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if not _can_access_job(job):
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404

        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        outputs = _collect_result_outputs(result)
        assets = _job_result_assets(job)
        return jsonify({
            "success": True,
            "job": job,
            "status": job.get("status"),
            "result": result,
            "outputs": outputs,
            "assets": assets,
        })
    except Exception as exc:
        current_app.logger.error("Failed to get background job results %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_RESULTS_ERROR", "Failed to load background job results.", detail=str(exc))


@jobs_bp.route("/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    try:
        job = get_background_job_service().get_job(job_id)
        if job is None:
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if not _can_access_job(job):
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        updated = get_background_job_service().request_cancel(job_id)
        return jsonify({"success": True, "job": updated})
    except Exception as exc:
        current_app.logger.error("Failed to cancel background job %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_CANCEL_ERROR", "Failed to cancel background job.", detail=str(exc))


@jobs_bp.route("/<job_id>", methods=["DELETE"])
def delete_job(job_id: str):
    try:
        service = get_background_job_service()
        job = service.get_job(job_id)
        if job is None:
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if not _can_access_job(job):
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if job.get("status") not in TERMINAL_STATUSES:
            return jsonify({
                "success": False,
                "error": "JOB_NOT_TERMINAL",
                "message": "Running or queued jobs must be cancelled before they can be deleted.",
            }), 409
        deleted_children = 0
        if not job.get("parent_job_id"):
            deleted_children = service.delete_child_jobs(job_id)
        deleted = service.delete_job(job_id)
        return jsonify({"success": True, "deleted_job": deleted, "deleted_children": deleted_children})
    except Exception as exc:
        current_app.logger.error("Failed to delete background job %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_DELETE_ERROR", "Failed to delete background job.", detail=str(exc))
