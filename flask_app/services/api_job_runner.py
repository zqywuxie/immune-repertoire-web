"""Worker-side runners for jobs submitted through the unified API."""

from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict

from flask import current_app
from flask_login import login_user

from flask_app.models.database import User
from flask_app.services.background_job_service import get_background_job_service


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


def normalize_response(value: Any) -> Dict[str, Any]:
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


def call_json_endpoint(module: str, payload: Dict[str, Any], user_id: int | None) -> Dict[str, Any]:
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
        return normalize_response(view_func())


def load_job_context(job_id: str) -> Dict[str, Any]:
    job = get_background_job_service().get_job(job_id)
    if not job:
        raise RuntimeError(f"Job not found: {job_id}")
    return job


def run_api_job(context) -> Dict[str, Any]:
    job = load_job_context(context.job_id)
    module = str(job.get("module") or "").strip()
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    user_id = job.get("user_id")
    context.update(5, "Preparing", f"Preparing {module}")
    context.raise_if_cancelled()
    context.update(15, "Running", f"Executing {module}")
    data = call_json_endpoint(module, payload, user_id)
    context.update(95, "Finalizing", f"{module} completed")
    return {
        "module": module,
        "payload_module": module,
        "data": data,
    }


def wait_child_job(context, child_id: str, label: str, start: float, span: float) -> Dict[str, Any]:
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


def run_combined_charts_job(context) -> Dict[str, Any]:
    job = load_job_context(context.job_id)
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    user_id = job.get("user_id")
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
            heatmap_data = call_json_endpoint("auto-heatmap.generate-heatmap", heatmap_payload, user_id)
            report_data = call_json_endpoint("auto-heatmap.generate-heatmap-report", {
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
        child = call_json_endpoint(f"{module_name}.generate", {
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
        child_result = wait_child_job(context, child_id, label, start, step_span)
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


def get_job_runner(module: str) -> Callable[..., Dict[str, Any]]:
    if module == "charts.combined":
        return run_combined_charts_job
    if module in ALLOWED_API_JOBS:
        return run_api_job
    raise KeyError(module)
