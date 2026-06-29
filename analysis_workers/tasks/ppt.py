"""PPT processing worker tasks."""

from __future__ import annotations

from typing import Any, Dict


def run_ppt_scan_images_job(job_id: str) -> Dict[str, Any]:
    """Run a ppt.scan-images analysis job."""
    return _run_ppt_module(job_id, "ppt.scan-images", "scanning-ppt-images")


def run_ppt_load_image_job(job_id: str) -> Dict[str, Any]:
    """Run a ppt.load-image analysis job."""
    return _run_ppt_module(job_id, "ppt.load-image", "loading-ppt-image")


def run_ppt_render_slides_job(job_id: str) -> Dict[str, Any]:
    """Run a ppt.render-slides analysis job."""
    return _run_ppt_module(job_id, "ppt.render-slides", "rendering-ppt-slides")


def run_ppt_comparison_scan_job(job_id: str) -> Dict[str, Any]:
    """Run a ppt-comparison.scan-heatmaps analysis job."""
    return _run_ppt_module(job_id, "ppt-comparison.scan-heatmaps", "scanning-ppt-heatmaps")


def run_ppt_comparison_generate_job(job_id: str) -> Dict[str, Any]:
    """Run a ppt-comparison.generate analysis job."""
    return _run_ppt_module(job_id, "ppt-comparison.generate", "generating-ppt-comparison")


def _run_ppt_module(job_id: str, module: str, stage: str) -> Dict[str, Any]:
    from flask_app.app import create_app
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.api_job_runner import call_json_endpoint

    app = create_app()
    with app.app_context():
        service = get_background_job_service()
        job = service.get_job(job_id)
        if job is None:
            return {"success": False, "error": "JOB_NOT_FOUND"}

        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        user_id = job.get("user_id")

        try:
            service.upsert_job(job_id, {
                "status": "running",
                "progress": 0,
                "stage": stage,
            })
            data = call_json_endpoint(module, payload, user_id)
            service.complete_job(job_id, result=data)
            return {"success": True, "job_id": job_id}
        except Exception as exc:
            import traceback
            service.fail_job(job_id, error=f"{exc}\n{traceback.format_exc()}")
            return {"success": False, "job_id": job_id, "error": str(exc)}
