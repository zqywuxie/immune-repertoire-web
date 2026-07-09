"""Auto-heatmap analysis worker tasks.

.. attention:: **LEGACY BRIDGE**

   These workers still call Flask endpoints via ``call_json_endpoint``
   and require a Flask app context.  See ``analysis_workers/results.py``
   for the standalone replacement pattern.
"""

from __future__ import annotations

from typing import Any, Dict


def _run_heatmap_module(job_id: str, module: str, stage: str) -> Dict[str, Any]:
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


def run_heatmap_generate_job(job_id: str) -> Dict[str, Any]:
    return _run_heatmap_module(job_id, "auto-heatmap.generate-heatmap", "generating-heatmap")


def run_heatmap_pipeline_report_job(job_id: str) -> Dict[str, Any]:
    return _run_heatmap_module(job_id, "auto-heatmap.generate-pipeline-report", "generating-pipeline-report")


def run_heatmap_report_job(job_id: str) -> Dict[str, Any]:
    return _run_heatmap_module(job_id, "auto-heatmap.generate-heatmap-report", "generating-heatmap-report")


def run_heatmap_export_cdr3_job(job_id: str) -> Dict[str, Any]:
    return _run_heatmap_module(job_id, "auto-heatmap.export-shared-cdr3", "exporting-shared-cdr3")
