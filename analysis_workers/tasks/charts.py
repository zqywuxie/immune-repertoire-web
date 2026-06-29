"""Charts combined analysis job runner.

Handles ``charts.combined`` module jobs with MongoDB result caching.
"""

from __future__ import annotations

from typing import Any, Dict


def run_charts_job(job_id: str) -> Dict[str, Any]:
    """Run a charts.combined analysis job.

    Reads job from DB, delegates to the charts.combined runner (which handles
    Mongo cache internally), and writes the result back.
    """
    from flask_app.app import create_app
    from flask_app.services.background_job_service import (
        get_background_job_service,
        JobContext,
    )

    app = create_app()
    with app.app_context():
        service = get_background_job_service()
        job = service.get_job(job_id)
        if job is None:
            return {"success": False, "error": "JOB_NOT_FOUND"}

        try:
            service.upsert_job(job_id, {
                "status": "running",
                "progress": 0,
                "stage": "executing",
            })

            context = JobContext(service, job_id)
            from flask_app.services.api_job_runner import run_combined_charts_job
            data = run_combined_charts_job(context)

            service.complete_job(job_id, data)
            return {"success": True, "job_id": job_id, "data": data}
        except Exception as exc:
            service.fail_job(job_id, str(exc))
            return {"success": False, "job_id": job_id, "error": str(exc)}
