from datetime import datetime, timedelta, timezone
import json
import time

import pytest
from flask_app.models.database import AnalysisJob, db
from flask_app.services.background_job_service import get_background_job_service
from flask_app.tests.test_persistent_queue import application


def test_historical_utc_job_fields_keep_the_same_instant(application):
    moment = datetime(2026, 10, 3, 0, 18, 29, 123456)
    job = AnalysisJob(id="legacy-clock", job_type="script_hub", module="profile", status="completed", progress=100,
                      created_at=moment, updated_at=moment, started_at=moment, completed_at=moment)
    db.session.add(job)
    db.session.commit()
    for key in ("created_at", "updated_at", "started_at", "completed_at", "finished_at"):
        value = job.to_dict()[key]
        assert value == "2026-10-03T00:18:29.123456Z"
        assert datetime.fromisoformat(value).timestamp() == moment.replace(tzinfo=timezone.utc).timestamp()
    assert job.created_at.tzinfo is None  # serialization does not rewrite historical database values


def test_aware_job_serialization_normalizes_the_offset():
    moment = datetime(2026, 10, 3, 8, 18, 29, tzinfo=timezone(timedelta(hours=8)))
    job = AnalysisJob(id="aware-clock", job_type="script_hub", module="profile", status="running", progress=25,
                      created_at=moment, updated_at=moment)
    assert job.to_dict()["created_at"] == "2026-10-03T00:18:29Z"
    assert job.to_dict()["completed_at"] is None


@pytest.mark.parametrize("server_timezone", ["UTC", "Asia/Shanghai"])
def test_new_progress_and_fallback_timestamps_are_unambiguous(application, monkeypatch, server_timezone):
    from flask_app.routes.api_script_hub._common import _history_entry as script_history
    from flask_app.services.script_hub_job_service import _now_iso
    monkeypatch.setenv("TZ", server_timezone)
    time.tzset()
    try:
        before = datetime.now(timezone.utc)
        job = get_background_job_service().create_job(job_type="script_hub", module="profile")
        values = [job["created_at"], job["history"][0]["timestamp"], script_history(25, "执行中", "计算中")["timestamp"], _now_iso()]
        after = datetime.now(timezone.utc)
        for value in values:
            parsed = datetime.fromisoformat(value)
            assert parsed.utcoffset() == timedelta(0)
            assert before - timedelta(seconds=1) <= parsed <= after
    finally:
        monkeypatch.undo()
        time.tzset()


def test_task_list_detail_result_and_event_share_timezone(application):
    moment = datetime(2026, 10, 3, 0, 18, 29)
    job = AnalysisJob(id="clock-api", job_type="script_hub", module="profile", status="completed", progress=100,
                      created_at=moment, updated_at=moment, started_at=moment, completed_at=moment)
    db.session.add(job)
    db.session.commit()
    client = application.test_client()
    for path in ("/api/jobs/clock-api", "/api/jobs/clock-api/results", "/api/script-hub/jobs/clock-api", "/api/script-hub/task/clock-api"):
        response = client.get(path)
        assert response.status_code == 200, response.json
        snapshot = response.json.get("job", response.json)
        assert snapshot["created_at"] == "2026-10-03T00:18:29Z"
        assert snapshot["completed_at"] == "2026-10-03T00:18:29Z"
    response = client.get("/api/jobs")
    assert response.json["jobs"][0]["updated_at"] == "2026-10-03T00:18:29Z"
    stream = client.get("/api/jobs/clock-api/events?max_events=1").get_data(as_text=True)
    payload = json.loads(next(line[6:] for line in stream.splitlines() if line.startswith("data: ")))
    assert payload["job"]["completed_at"] == "2026-10-03T00:18:29Z"
