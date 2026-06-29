"""Tests for the background job queue boundary."""

import os

os.environ.setdefault("FLASK_CONFIG", "testing")

from flask_app.app import create_app
from flask_app.models.database import db
from flask_app.routes import api_jobs
from flask_app.services.background_job_service import JobContext, get_background_job_service
from flask_app.services.job_queue import ThreadPoolJobQueue


class FakeBackgroundJobService:
    def __init__(self):
        self.calls = []

    def submit(self, job_id, runner, **kwargs):
        self.calls.append((job_id, runner, kwargs))


def test_thread_pool_job_queue_delegates_to_background_service():
    service = FakeBackgroundJobService()
    queue = ThreadPoolJobQueue(service)

    def runner():
        return {"ok": True}

    queue.submit("job-1", runner, module="charts.combined", payload={"a": 1})

    assert service.calls == [
        ("job-1", runner, {"module": "charts.combined", "payload": {"a": 1}})
    ]


def test_create_job_uses_queue_adapter(monkeypatch):
    app = create_app("testing")
    captured = []

    class FakeQueue:
        def submit(self, job_id, runner, **kwargs):
            captured.append((job_id, runner.__name__, kwargs))

    monkeypatch.setattr(api_jobs, "get_job_queue", lambda: FakeQueue())

    with app.app_context():
        response = app.test_client().post("/api/jobs", json={
            "module": "analysis.execute",
            "payload": {"file_id": "file-1"},
        })
        payload = response.get_json()
        db.session.remove()

    assert response.status_code == 200
    assert payload["success"] is True
    assert captured == [
        (payload["job_id"], "_run_api_job", {})
    ]


def test_api_job_runner_loads_context_from_persisted_job(monkeypatch):
    app = create_app("testing")
    calls = []

    def fake_call_json_endpoint(module, payload, user_id):
        calls.append((module, payload, user_id))
        return {"success": True}

    monkeypatch.setattr(api_jobs, "_call_json_endpoint", fake_call_json_endpoint)

    with app.app_context():
        service = get_background_job_service()
        job = service.create_job(
            job_type="api_request",
            module="analysis.execute",
            payload={"file_id": "file-1"},
            user_id=42,
        )
        context = JobContext(service, job["job_id"])

        result = api_jobs._run_api_job(context)
        db.session.remove()

    assert result == {
        "module": "analysis.execute",
        "payload_module": "analysis.execute",
        "data": {"success": True},
    }
    assert calls == [("analysis.execute", {"file_id": "file-1"}, 42)]
