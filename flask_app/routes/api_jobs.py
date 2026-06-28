"""Global background job API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request
from flask_login import login_user

from flask_app.models.database import ProjectAsset, User
from flask_app.services.background_job_service import TERMINAL_STATUSES, get_background_job_service
from flask_app.services.user_scope import current_user_id, is_admin


jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


ALLOWED_API_JOBS: Dict[str, Dict[str, str]] = {
    "charts.combined": {"endpoint": "", "path": ""},
    "analysis.execute": {"endpoint": "analysis.execute_analysis", "path": "/api/analysis/execute"},
    "analysis.batch": {"endpoint": "analysis.execute_batch_analysis", "path": "/api/analysis/batch"},
    "analysis.execute-unified": {"endpoint": "analysis.execute_unified_analysis", "path": "/api/analysis/execute-unified"},
    "statistical.analyze": {"endpoint": "statistical.analyze_groups", "path": "/api/statistical/analyze"},
    "statistical.boxplot": {"endpoint": "statistical.create_boxplot", "path": "/api/statistical/boxplot"},
    "statistical.analyze-multiple": {"endpoint": "statistical.analyze_multiple", "path": "/api/statistical/analyze-multiple"},
    "statistical.summary-boxplot": {"endpoint": "statistical.create_summary_boxplot", "path": "/api/statistical/summary-boxplot"},
    "statistical.analyze-batch": {"endpoint": "statistical.analyze_batch", "path": "/api/statistical/analyze-batch"},
    "statistical.analyze-direct": {"endpoint": "statistical.analyze_direct", "path": "/api/statistical/analyze-direct"},
    "auto-heatmap.generate-heatmap": {"endpoint": "auto_heatmap.generate_heatmap", "path": "/api/auto-heatmap/generate-heatmap"},
    "auto-heatmap.generate-pipeline-report": {"endpoint": "auto_heatmap.generate_pipeline_report", "path": "/api/auto-heatmap/generate-pipeline-report"},
    "auto-heatmap.generate-heatmap-report": {"endpoint": "auto_heatmap.generate_heatmap_report", "path": "/api/auto-heatmap/generate-heatmap-report"},
    "auto-heatmap.export-shared-cdr3": {"endpoint": "auto_heatmap.export_shared_cdr3", "path": "/api/auto-heatmap/export-shared-cdr3"},
    "treemap.generate": {"endpoint": "treemap.generate_treemap", "path": "/api/treemap/generate"},
    "chord.generate": {"endpoint": "chord.generate_chord", "path": "/api/chord/generate"},
    "ppt.scan-images": {"endpoint": "ppt.scan_images", "path": "/api/ppt/scan-images"},
    "ppt.load-image": {"endpoint": "ppt.load_image", "path": "/api/ppt/load-image"},
    "ppt.render-slides": {"endpoint": "ppt.render_slides", "path": "/api/ppt/render-slides"},
    "ppt-comparison.scan-heatmaps": {"endpoint": "ppt_comparison.scan_heatmaps", "path": "/api/ppt-comparison/scan-heatmaps"},
    "ppt-comparison.generate": {"endpoint": "ppt_comparison.generate_comparison_ppt", "path": "/api/ppt-comparison/generate"},
}


def _normalize_response(value: Any) -> Dict[str, Any]:
    if isinstance(value, tuple):
        response = value[0]
        status_code = value[1] if len(value) > 1 else 200
    else:
        response = value
        status_code = getattr(value, "status_code", 200)

    if hasattr(response, "get_json"):
        data = response.get_json(silent=True)
        if data is not None:
            if status_code and int(status_code) >= 400:
                raise RuntimeError(data.get("message") or data.get("error") or json.dumps(data, ensure_ascii=False))
            return data

    if hasattr(response, "get_data"):
        text = response.get_data(as_text=True)
        if status_code and int(status_code) >= 400:
            raise RuntimeError(text[:1000])
        return {"response_text": text}

    return {"value": response}


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


def _call_json_endpoint(module: str, payload: Dict[str, Any], user_id: int | None) -> Dict[str, Any]:
    spec = ALLOWED_API_JOBS[module]
    app = current_app._get_current_object()
    endpoint = spec["endpoint"]
    view_func = app.view_functions.get(endpoint)
    if view_func is None:
        raise RuntimeError(f"Endpoint not available: {endpoint}")

    with app.test_request_context(spec["path"], method="POST", json=payload):
        if user_id is not None:
            user = User.query.get(user_id)
            if user is not None:
                login_user(user)
        return _normalize_response(view_func())


def _run_api_job(context, *, module: str, payload: Dict[str, Any], user_id: int | None) -> Dict[str, Any]:
    context.update(5, "Preparing", f"Preparing {module}")
    context.raise_if_cancelled()
    context.update(15, "Running", f"Executing {module}")
    data = _call_json_endpoint(module, payload, user_id)
    context.update(95, "Finalizing", f"{module} completed")
    return {
        "module": module,
        "payload_module": module,
        "data": data,
    }


def _wait_child_job(context, child_id: str, label: str, start: float, span: float) -> Dict[str, Any]:
    service = get_background_job_service()
    for _ in range(720):
        context.raise_if_cancelled()
        job = service.get_job(child_id)
        if not job:
            raise RuntimeError(f"{label} child task not found: {child_id}")
        child_progress = float(job.get("progress") or 0.0)
        progress = start + (child_progress / 100.0) * span
        context.update(progress, label, job.get("detail") or job.get("stage") or "")
        if job.get("status") == "completed":
            return job.get("result") or {}
        if job.get("status") in {"failed", "cancelled", "interrupted"}:
            raise RuntimeError(job.get("error") or job.get("detail") or f"{label} failed")
        time.sleep(1.5)
    raise RuntimeError(f"{label} did not complete before timeout")


def _run_combined_charts_job(context, *, payload: Dict[str, Any], user_id: int | None) -> Dict[str, Any]:
    selected = [str(item) for item in payload.get("selected_modules") or ["heatmap", "treemap", "chord"]]
    samples = payload.get("samples") or []
    chains = payload.get("selected_chains") or []
    field_mapping = payload.get("field_mapping") or {}
    output_name = payload.get("output_name")
    transcriptome_path = str(payload.get("transcriptome_path") or "").strip()
    if not selected:
        raise RuntimeError("No chart module selected")
    results = []
    step_span = 90.0 / max(1, len(selected))

    for index, key in enumerate(selected):
        start = 5.0 + index * step_span
        label = {"heatmap": "相似性热图", "treemap": "Treemap", "chord": "Chord"}.get(key, key)
        context.update(start, label, f"Starting {label}")
        context.raise_if_cancelled()

        if key == "heatmap":
            heatmap_payload = {
                "samples": samples,
                "file_pattern": None,
                "selected_chains": chains,
                "field_mapping": {
                    "cdr3_column": field_mapping.get("cdr3_column"),
                    "copy_column": field_mapping.get("copy_column"),
                },
                "groups": [],
                "config": {
                    "title": output_name or "Similarity Heatmap",
                    "plot_type": "heatmap",
                    "color_scheme": "viridis",
                    "annotation": True,
                },
            }
            heatmap_data = _call_json_endpoint("auto-heatmap.generate-heatmap", heatmap_payload, user_id)
            report_data = _call_json_endpoint("auto-heatmap.generate-heatmap-report", {
                "heatmap_result": heatmap_data,
                "output_name": output_name,
                "create_archive": True,
                "report_context": {
                    "source": "background_charts_combined",
                    "selected_chains": chains,
                    "sample_count": len(samples),
                },
            }, user_id)
            results.append({
                "key": key,
                "label": label,
                "status": "completed",
                "job_id": report_data.get("job_id"),
                "viewer_url": report_data.get("report_url"),
                "zip_url": report_data.get("archive_url"),
                "metadata_url": report_data.get("metadata_url"),
            })
            continue

        module_name = "treemap" if key == "treemap" else "chord"
        child = _call_json_endpoint(f"{module_name}.generate", {
            "samples": samples,
            "selected_chains": chains,
            "field_mapping": field_mapping,
            "config": {
                "output_name": output_name,
                **({"layout_mode": "tetris", "canvas_shape": "portrait"} if key == "treemap" else {}),
                "_parent_job_id": context.job_id,
                "_hidden_from_default_list": True,
                "_child_label": label,
            },
        }, user_id)
        child_id = child.get("task_id") or child.get("job_id")
        if not child_id:
            raise RuntimeError(f"{label} did not return a task id")
        child_result = _wait_child_job(context, child_id, label, start, step_span)
        results.append({
            "key": key,
            "label": label,
            "status": "completed",
            **child_result,
        })

    first_viewer = next((item.get("viewer_url") for item in results if item.get("viewer_url")), "")
    first_zip = next((item.get("zip_url") for item in results if item.get("zip_url")), "")
    result = {
        "module": "charts.combined",
        "job_id": context.job_id,
        "chart_results": results,
        "viewer_url": first_viewer,
        "zip_url": first_zip,
        "output_base": next((item.get("output_base") for item in results if item.get("output_base")), ""),
        "metadata": {
            "selected_modules": selected,
            "selected_chains": chains,
            "sample_count": len(samples),
            "transcriptome_path": transcriptome_path,
            "chart_results": results,
        },
    }
    signature = str(payload.get("analysis_signature") or "")
    project_id = str(payload.get("project_id") or payload.get("_project_id") or "").strip()
    if project_id and signature:
        try:
            from flask_app.services.mongo_service import save_result
            save_result(
                project_id=project_id,
                analysis_type="charts.combined",
                job_id=context.job_id,
                files=[
                    {"kind": "viewer_url", "url": result.get("viewer_url", "")},
                    {"kind": "zip_url", "url": result.get("zip_url", "")},
                ],
                metadata_json={
                    **result["metadata"],
                    "metadata": result["metadata"],
                    "analysis_signature": signature,
                },
                analysis_signature=signature,
                input_assets=payload.get("input_assets") if isinstance(payload.get("input_assets"), list) else [],
                config_json=payload.get("config_json") if isinstance(payload.get("config_json"), dict) else {},
                viewer_url=str(result.get("viewer_url") or ""),
                zip_url=str(result.get("zip_url") or ""),
                output_base=str(result.get("output_base") or ""),
                status="completed",
            )
        except Exception:
            current_app.logger.warning("Failed to persist combined charts result", exc_info=True)
    return result


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
    runner = _run_combined_charts_job if module == "charts.combined" else _run_api_job
    if module == "charts.combined":
        service.submit(job["job_id"], runner, payload=payload, user_id=user_id)
    else:
        service.submit(job["job_id"], runner, module=module, payload=payload, user_id=user_id)
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
