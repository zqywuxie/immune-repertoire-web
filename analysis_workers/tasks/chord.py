"""Chord diagram analysis worker task.

.. attention:: **LEGACY BRIDGE**

   This worker still calls Flask endpoints via ``call_json_endpoint``
   and requires a Flask app context.  See ``analysis_workers/results.py``
   for the standalone replacement pattern.
"""

from __future__ import annotations

from typing import Any, Dict


def run_chord_job(job_id: str) -> Dict[str, Any]:
    """Run a chord.generate analysis job."""
    from flask_app.app import create_app
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.api_job_runner import call_json_endpoint

    app = create_app()
    with app.app_context():
        service = get_background_job_service()
        job = service.get_job(job_id)
        if job is None:
            return {"success": False, "error": "JOB_NOT_FOUND"}

        module = "chord.generate"
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        user_id = job.get("user_id")

        try:
            service.upsert_job(job_id, {
                "status": "running",
                "progress": 0,
                "stage": "generating-chord",
            })
            data = call_json_endpoint(module, payload, user_id)
            service.complete_job(job_id, result=data)
            return {"success": True, "job_id": job_id}
        except Exception as exc:
            import traceback
            service.fail_job(job_id, error=f"{exc}\n{traceback.format_exc()}")
            return {"success": False, "job_id": job_id, "error": str(exc)}
