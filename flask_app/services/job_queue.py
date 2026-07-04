"""Queue boundary for background analysis jobs.

This adapter keeps the current in-process thread pool behavior while giving the
API layer a stable seam for the Phase 3 move to Redis/RQ/Celery workers.

Queue backend selection::

    Backend       Config key                   Requires
    ───────────   ───────────────────────────  ────────
    threadpool    (default, no config needed)  nothing
    redis         JOB_QUEUE=redis              Redis + rq package

When ``JOB_QUEUE=redis`` is set, ``RedisJobQueue`` is used. Otherwise the
process falls back to ``ThreadPoolJobQueue`` backed by the existing
``BackgroundJobService`` thread pool.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from flask_app.services.background_job_service import BackgroundJobService, get_background_job_service


class JobQueue(Protocol):
    def submit(self, job_id: str, runner: Callable[..., Any], **kwargs: Any) -> None:
        """Submit a job runner to the configured queue backend."""


def _job_module(job_id: str, explicit_module: str = "") -> str:
    module = str(explicit_module or "").strip()
    if module:
        return module
    job = get_background_job_service().get_job(job_id)
    return str((job or {}).get("module") or "").strip()


def _worker_for_module(module: str) -> Callable[[str], Any] | None:
    if not module:
        return None
    try:
        from analysis_workers.main import get_worker
        from analysis_workers.tasks.generic import run_generic_job
    except ImportError:
        return None
    worker = get_worker(module)
    return worker if worker is not run_generic_job else None


@dataclass
class ThreadPoolJobQueue:
    """Queue adapter backed by the existing BackgroundJobService thread pool."""

    service: BackgroundJobService

    def submit(self, job_id: str, runner: Callable[..., Any], **kwargs: Any) -> None:
        """Submit a job runner. If runner is the generic run_api_job, try to use a module-specific worker."""
        module = _job_module(job_id, kwargs.pop("module", ""))
        worker = _worker_for_module(module)
        if worker is not None:
            self.service.submit(job_id, lambda ctx: worker(ctx.job_id))
            return

        # Default: use the provided runner (backwards compatible)
        self.service.submit(job_id, runner, **kwargs)


@dataclass
class RedisJobQueue:
    """Queue adapter backed by Redis + RQ.

    This is a Phase 3 implementation that replaces the in-process thread pool
    with a Redis-backed worker queue.  Workers run in separate processes and
    receive only ``job_id``, reading inputs from the database and writing back
    progress / results / registered assets.
    """

    redis_url: str = field(default_factory=lambda: os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    fallback: ThreadPoolJobQueue | None = None
    _queue: Any = field(default=None, init=False, repr=False)
    _connection: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        try:
            from redis import Redis  # type: ignore[import-untyped]
            from rq import Queue  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "RedisJobQueue requires the 'redis' and 'rq' packages. "
                "Install them with: pip install redis rq"
            ) from exc
        self._connection = Redis.from_url(self.redis_url)
        self._connection.ping()
        self._queue = Queue(connection=self._connection)

    def _has_workers(self) -> bool:
        try:
            from rq import Worker  # type: ignore[import-untyped]

            return int(Worker.count(connection=self._connection)) > 0
        except Exception:
            return False

    def submit(self, job_id: str, runner: Callable[..., Any], **kwargs: Any) -> None:
        if self._queue is None:
            raise RuntimeError("RedisJobQueue is not connected — check REDIS_URL")
        module = _job_module(job_id, kwargs.pop("module", ""))
        if not self._has_workers() and self.fallback is not None:
            get_background_job_service().upsert_job(job_id, {
                "stage": "Starting local worker",
                "detail": "No active RQ worker detected; running with in-process thread pool.",
            })
            self.fallback.submit(job_id, runner, module=module, **kwargs)
            return
        if module:
            from analysis_workers.main import execute
            self._queue.enqueue(execute, module, job_id)
            return
        self._queue.enqueue(runner, job_id)


def get_job_queue() -> JobQueue:
    backend = os.environ.get("JOB_QUEUE", "").strip().lower()
    threadpool = ThreadPoolJobQueue(get_background_job_service())

    if backend == "redis":
        try:
            return RedisJobQueue(fallback=threadpool)
        except Exception:
            return threadpool

    return threadpool
