"""Persistent background job service for all analysis modules."""

from __future__ import annotations

import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional

from flask import has_app_context
from sqlalchemy import or_

from flask_app.models.database import AnalysisJob, db


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "interrupted"}


def _now() -> datetime:
    return datetime.utcnow()


def _history_entry(progress: float, stage: str, detail: str, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "progress": round(float(progress or 0.0), 2),
        "stage": stage or "",
        "detail": detail or "",
        "meta": meta or {},
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }


class JobContext:
    """Small helper passed to background task callables."""

    def __init__(self, service: "BackgroundJobService", job_id: str) -> None:
        self.service = service
        self.job_id = job_id

    def update(self, progress: float, stage: str, detail: str = "", meta: Optional[Dict[str, Any]] = None) -> None:
        self.service.update_progress(self.job_id, progress, stage, detail, meta=meta)

    def is_cancel_requested(self) -> bool:
        job = self.service.get_job(self.job_id)
        return bool(job and job.get("cancel_requested"))

    def raise_if_cancelled(self) -> None:
        if self.is_cancel_requested():
            raise RuntimeError("Job cancelled by user")


class BackgroundJobService:
    """Thread-pool backed persistent job catalog."""

    def __init__(self, app=None, max_workers: int = 4) -> None:
        self.app = None
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        if app is not None:
            self.init_app(app)

    def init_app(self, app) -> None:
        self.app = app

    @contextmanager
    def _ctx(self):
        if has_app_context():
            yield
            return
        if self.app is None:
            raise RuntimeError("BackgroundJobService is not initialized with a Flask app")
        with self.app.app_context():
            yield

    def create_job(
        self,
        *,
        job_type: str,
        module: str,
        payload: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        project_id: Optional[str] = None,
        job_id: Optional[str] = None,
        stage: str = "Queued",
        detail: str = "Task created and waiting to start",
        history: Optional[list[Dict[str, Any]]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._ctx():
            job = AnalysisJob(
                id=job_id or f"job_{uuid.uuid4().hex[:12]}",
                job_type=job_type,
                module=module,
                status="queued",
                progress=0.0,
                stage=stage,
                detail=detail,
                history=history or [_history_entry(0, stage, detail, {"module": module})],
                payload=payload or {},
                user_id=user_id,
                project_id=project_id,
            )
            if extra:
                payload_data = dict(job.payload or {})
                payload_data.update(extra)
                job.payload = payload_data
            db.session.add(job)
            db.session.commit()
            return job.to_dict()

    def upsert_job(self, job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        if not job_id:
            raise ValueError("job_id is required")
        clean = dict(updates or {})
        clean.pop("success", None)
        with self._ctx():
            job = AnalysisJob.query.get(job_id)
            if job is None:
                job = AnalysisJob(
                    id=job_id,
                    job_type=str(clean.get("job_type") or "analysis"),
                    module=str(clean.get("module") or (clean.get("meta") or {}).get("module") or "analysis"),
                    status=str(clean.get("status") or "queued"),
                    progress=float(clean.get("progress") or 0.0),
                    stage=str(clean.get("stage") or "Queued"),
                    detail=str(clean.get("detail") or ""),
                    history=clean.get("history") if isinstance(clean.get("history"), list) else [],
                    payload={},
                )
                db.session.add(job)
            elif job.status in TERMINAL_STATUSES:
                incoming_status = str(clean.get("status") or "")
                if incoming_status and incoming_status != job.status:
                    return job.to_dict()

            for key in ("job_type", "module", "status", "progress", "stage", "detail", "history", "payload", "result", "error", "project_id", "user_id"):
                if key not in clean:
                    continue
                setattr(job, key, clean[key])
            payload_updates = {
                key: value for key, value in clean.items()
                if key not in {"job_id", "task_id", "id", "job_type", "module", "status", "progress", "stage", "detail", "history", "payload", "result", "error", "project_id", "user_id"}
            }
            if payload_updates:
                payload = dict(job.payload or {})
                payload.update(payload_updates)
                job.payload = payload
            if clean.get("status") == "running" and not job.started_at:
                job.started_at = _now()
            if clean.get("status") in TERMINAL_STATUSES and not job.completed_at:
                job.completed_at = _now()
            job.updated_at = _now()
            if isinstance(job.history, list) and len(job.history) > 100:
                job.history = job.history[-100:]
            db.session.commit()
            return job.to_dict()

    def submit(self, job_id: str, func: Callable[..., Any], *args, **kwargs) -> None:
        self._executor.submit(self._run, job_id, func, args, kwargs)

    def _run(self, job_id: str, func: Callable[..., Any], args: tuple, kwargs: Dict[str, Any]) -> None:
        try:
            self.mark_running(job_id)
            context = JobContext(self, job_id)
            with self._ctx():
                result = func(context, *args, **kwargs)
            if self.get_job(job_id, include_payload=False).get("cancel_requested"):
                self.cancel_job(job_id)
                return
            self.complete_job(job_id, result if isinstance(result, dict) else {"value": result})
        except Exception as exc:
            if "cancelled" in str(exc).lower():
                self.cancel_job(job_id, detail=str(exc))
            else:
                self.fail_job(job_id, str(exc), traceback.format_exc())

    def mark_running(self, job_id: str) -> None:
        self.upsert_job(job_id, {
            "status": "running",
            "progress": 1.0,
            "stage": "Running",
            "detail": "Task started",
        })

    def update_progress(
        self,
        job_id: str,
        progress: float,
        stage: str,
        detail: str = "",
        *,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        with self._ctx():
            job = AnalysisJob.query.get(job_id)
            if job is None:
                raise ValueError(f"Job not found: {job_id}")
            if job.cancel_requested or job.status in TERMINAL_STATUSES:
                return job.to_dict()
            history = list(job.history or [])
            history.append(_history_entry(progress, stage, detail, meta))
            job.status = "running" if job.status == "queued" else job.status
            job.progress = max(0.0, min(100.0, float(progress or 0.0)))
            job.stage = stage
            job.detail = detail
            job.history = history[-100:]
            if not job.started_at:
                job.started_at = _now()
            job.updated_at = _now()
            db.session.commit()
            return job.to_dict()

    def complete_job(self, job_id: str, result: Optional[Dict[str, Any]] = None, detail: str = "Task completed") -> Dict[str, Any]:
        return self.upsert_job(job_id, {
            "status": "completed",
            "progress": 100.0,
            "stage": "Completed",
            "detail": detail,
            "result": result or {},
        })

    def fail_job(self, job_id: str, error: str, detail: str = "") -> Dict[str, Any]:
        return self.upsert_job(job_id, {
            "status": "failed",
            "progress": 100.0,
            "stage": "Failed",
            "detail": detail or error,
            "error": error,
        })

    def cancel_job(self, job_id: str, detail: str = "Job cancelled by user.") -> Optional[Dict[str, Any]]:
        with self._ctx():
            job = AnalysisJob.query.get(job_id)
            if job is None:
                return None
            if job.status in TERMINAL_STATUSES:
                return job.to_dict()
            job.cancel_requested = True
            job.status = "cancelled"
            job.progress = max(float(job.progress or 0.0), 0.0)
            job.stage = "Cancelled"
            job.detail = detail
            job.completed_at = _now()
            job.updated_at = _now()
            db.session.commit()
            return job.to_dict()

    def request_cancel(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._ctx():
            job = AnalysisJob.query.get(job_id)
            if job is None:
                return None
            job.cancel_requested = True
            if job.status not in TERMINAL_STATUSES:
                was_queued = job.status == "queued"
                job.status = "cancelled"
                job.stage = "Cancelled"
                job.detail = "Job cancelled before start." if was_queued else "Job cancellation requested."
                job.completed_at = _now()
            job.updated_at = _now()
            db.session.commit()
            return job.to_dict()

    def get_job(self, job_id: str, *, include_payload: bool = True) -> Optional[Dict[str, Any]]:
        with self._ctx():
            job = AnalysisJob.query.get(job_id)
            if not job:
                return None
            data = job.to_dict()
            if not include_payload:
                data.pop("payload", None)
            return data

    def list_jobs(
        self,
        *,
        module: Optional[str] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
        include_admin_scope: bool = False,
        include_children: bool = False,
        limit: int = 100,
    ) -> list[Dict[str, Any]]:
        with self._ctx():
            query = AnalysisJob.query
            if module:
                query = query.filter(AnalysisJob.module == module)
            if project_id:
                query = query.filter(AnalysisJob.project_id == str(project_id))
            if status:
                query = query.filter(AnalysisJob.status == status)
            if user_id is not None and not include_admin_scope:
                query = query.filter(or_(AnalysisJob.user_id == user_id, AnalysisJob.user_id.is_(None)))
            requested_limit = max(1, min(int(limit or 100), 500))
            fetch_limit = 500 if not include_children else requested_limit
            id_rows = query.with_entities(AnalysisJob.id).order_by(
                AnalysisJob.updated_at.desc(),
                AnalysisJob.id.desc(),
            ).limit(fetch_limit).all()
            job_ids = [row[0] for row in id_rows]
            if not job_ids:
                return []

            rows = AnalysisJob.query.filter(AnalysisJob.id.in_(job_ids)).all()
            rows_by_id = {job.id: job for job in rows}
            jobs = [
                rows_by_id[job_id].to_dict()
                for job_id in job_ids
                if job_id in rows_by_id
            ]
            if not include_children:
                jobs = [
                    job for job in jobs
                    if not job.get("hidden_from_default_list") and not job.get("parent_job_id")
                ]
            return jobs[:requested_limit]

    def delete_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._ctx():
            job = AnalysisJob.query.get(job_id)
            if job is None:
                return None
            data = job.to_dict()
            db.session.delete(job)
            db.session.commit()
            return data

    def delete_child_jobs(self, parent_job_id: str) -> int:
        with self._ctx():
            deleted = 0
            for job in AnalysisJob.query.all():
                payload = job.payload or {}
                if payload.get("parent_job_id") != parent_job_id:
                    continue
                db.session.delete(job)
                deleted += 1
            if deleted:
                db.session.commit()
            return deleted

    def clear(self) -> None:
        with self._ctx():
            AnalysisJob.query.delete()
            db.session.commit()


_background_job_service = BackgroundJobService()


def init_background_job_service(app) -> None:
    _background_job_service.init_app(app)


def get_background_job_service() -> BackgroundJobService:
    return _background_job_service
