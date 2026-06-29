"""Generic analysis job runner.

All modules except "charts.combined" use this runner.  It reads the job
payload from the database, calls the corresponding Flask endpoint via
``api_job_runner.call_json_endpoint``, and writes the result back.
"""

from __future__ import annotations

from typing import Any, Dict


def run_generic_job(job_id: str) -> Dict[str, Any]:
    """Run any registered analysis job by its job_id.

    This is the main entry point for RQ workers.  The worker receives only
    ``job_id`` and must read/write everything via the database.
    """
    from flask_app.app import create_app
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.api_job_runner import call_json_endpoint

    app = create_app()
    with app.app_context():
        service = get_background_job_service()
        job = service.get_job(job_id)
        if job is None:
            return {"success": False, "error": "JOB_NOT_FOUND"}

        module = job.get("module") or ""
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        user_id = job.get("user_id")

        try:
            service.upsert_job(job_id, {
                "status": "running",
                "progress": 0,
                "stage": "executing",
            })
            data = call_json_endpoint(module, payload, user_id)
            service.complete_job(job_id, data)
            return {"success": True, "job_id": job_id, "data": data}
        except Exception as exc:
            service.fail_job(job_id, str(exc))
            return {"success": False, "job_id": job_id, "error": str(exc)}
