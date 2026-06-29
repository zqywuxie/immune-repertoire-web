"""Queue boundary for background analysis jobs.

This adapter keeps the current in-process thread pool behavior while giving the
API layer a stable seam for the Phase 3 move to Redis/RQ/Celery workers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from flask_app.services.background_job_service import BackgroundJobService, get_background_job_service


class JobQueue(Protocol):
    def submit(self, job_id: str, runner: Callable[..., Any], **kwargs: Any) -> None:
        """Submit a job runner to the configured queue backend."""


@dataclass
class ThreadPoolJobQueue:
    """Queue adapter backed by the existing BackgroundJobService thread pool."""

    service: BackgroundJobService

    def submit(self, job_id: str, runner: Callable[..., Any], **kwargs: Any) -> None:
        self.service.submit(job_id, runner, **kwargs)


def get_job_queue() -> JobQueue:
    return ThreadPoolJobQueue(get_background_job_service())
