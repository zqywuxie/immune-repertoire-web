"""Statistical analysis worker tasks."""

from __future__ import annotations

from typing import Any, Dict


def _run_statistical_module(job_id: str, module: str, stage: str) -> Dict[str, Any]:
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
            service.upsert_job(job_id, status="running", progress=0, stage=stage)
            data = call_json_endpoint(module, payload, user_id)
            service.complete_job(job_id, result=data)
            return {"success": True, "job_id": job_id}
        except Exception as exc:
            import traceback
            service.fail_job(job_id, error=f"{exc}\n{traceback.format_exc()}")
            return {"success": False, "job_id": job_id, "error": str(exc)}


def run_statistical_analyze_job(job_id: str) -> Dict[str, Any]:
    return _run_statistical_module(job_id, "statistical.analyze", "analyzing-groups")


def run_statistical_boxplot_job(job_id: str) -> Dict[str, Any]:
    return _run_statistical_module(job_id, "statistical.boxplot", "creating-boxplot")


def run_statistical_analyze_multiple_job(job_id: str) -> Dict[str, Any]:
    return _run_statistical_module(job_id, "statistical.analyze-multiple", "analyzing-multiple")


def run_statistical_summary_boxplot_job(job_id: str) -> Dict[str, Any]:
    return _run_statistical_module(job_id, "statistical.summary-boxplot", "creating-summary-boxplot")


def run_statistical_analyze_batch_job(job_id: str) -> Dict[str, Any]:
    return _run_statistical_module(job_id, "statistical.analyze-batch", "batch-analyzing")


def run_statistical_analyze_direct_job(job_id: str) -> Dict[str, Any]:
    return _run_statistical_module(job_id, "statistical.analyze-direct", "direct-analyzing")
