"""Process-local Script Hub job index.

This is a compatibility layer over the existing Script Hub task executor. It
keeps module-specific ``/run`` endpoints stable while giving the UI one place to
list and read background jobs.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, List, Optional

from flask_app.services.background_job_service import TERMINAL_STATUSES, get_background_job_service


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ScriptHubJobService:
    """Compatibility wrapper over the global background job catalog."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def upsert_job(self, job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not job_id:
            raise ValueError("job_id is required")

        clean_updates = dict(updates or {})
        clean_updates.pop("success", None)
        clean_updates["job_id"] = job_id
        clean_updates.setdefault("task_id", job_id)
        clean_updates.setdefault("job_type", "script_hub")
        clean_updates.setdefault("module", clean_updates.get("module") or (clean_updates.get("meta") or {}).get("module") or "script-hub")

        try:
            return get_background_job_service().upsert_job(job_id, clean_updates)
        except Exception:
            timestamp = _now_iso()
            job = self._jobs.setdefault(job_id, {
                "job_id": job_id,
                "task_id": clean_updates.get("task_id") or job_id,
                "status": "queued",
                "progress": 0.0,
                "stage": "Queued",
                "detail": "",
                "history": [],
                "created_at": timestamp,
                "updated_at": timestamp,
            })
            job.update(clean_updates)
            job["updated_at"] = timestamp
            if job.get("status") in TERMINAL_STATUSES:
                job.setdefault("completed_at", timestamp)

            history = job.get("history")
            if isinstance(history, list) and len(history) > 80:
                job["history"] = history[-80:]

            return deepcopy(job)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            return get_background_job_service().get_job(job_id)
        except Exception:
            pass
        with self._lock:
            job = self._jobs.get(job_id)
            return deepcopy(job) if job else None

    def list_jobs(
        self,
        *,
        module: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        try:
            return get_background_job_service().list_jobs(
                module=module,
                project_id=project_id,
                status=status,
                limit=limit,
            )
        except Exception:
            pass
        with self._lock:
            jobs = [deepcopy(job) for job in self._jobs.values()]

        if module:
            jobs = [job for job in jobs if job.get("module") == module or (job.get("meta") or {}).get("module") == module]
        if project_id:
            jobs = [job for job in jobs if str(job.get("project_id") or "") == str(project_id)]
        if status:
            jobs = [job for job in jobs if job.get("status") == status]

        jobs.sort(key=lambda job: str(job.get("updated_at") or job.get("created_at") or ""), reverse=True)
        return jobs[: max(1, min(int(limit or 100), 500))]

    def cancel_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        try:
            return get_background_job_service().request_cancel(job_id)
        except Exception:
            pass
        job = self.get_job(job_id)
        if not job:
            return None
        if job.get("status") in TERMINAL_STATUSES:
            return job
        return self.upsert_job(job_id, {
            "status": "cancelled",
            "progress": job.get("progress", 0.0),
            "stage": "Cancelled",
            "detail": "Job cancelled by user.",
            "meta": {**(job.get("meta") or {}), "phase": "cancelled"},
        })

    def clear(self) -> None:
        try:
            get_background_job_service().clear()
            return
        except Exception:
            pass
        with self._lock:
            self._jobs.clear()


_script_hub_job_service = ScriptHubJobService()


def get_script_hub_job_service() -> ScriptHubJobService:
    return _script_hub_job_service
