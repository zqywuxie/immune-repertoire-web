"""Script Hub failures retain actual work progress across both task read modes."""
import uuid
from pathlib import Path

import pytest

from flask_app.routes.api_script_hub import _common
from flask_app.services.background_job_service import get_background_job_service
from flask_app.tests.test_profile_workflow import profile_app


@pytest.fixture
def task_id():
    identifier = "script-failure-" + uuid.uuid4().hex[:12]
    yield identifier
    with _common._script_task_lock:
        _common._script_tasks.pop(identifier, None)


@pytest.mark.parametrize("queue_mode", ["threadpool", "redis"])
@pytest.mark.parametrize("incoming_progress", [0., 100.])
def test_failed_updates_keep_last_reported_progress(profile_app, monkeypatch, task_id, queue_mode, incoming_progress):
    monkeypatch.setenv("JOB_QUEUE", queue_mode)
    payload = {"sample_ids": ["001", "002"], "group_values": ["01", "02"], "threshold": 0}
    _common._set_task_state(task_id, status="queued", progress=0., module="profile", payload=payload)
    _common._record_stage(task_id, 37.5, "计算指标", "已核对原始分组")
    history = _common._get_task_state(task_id)["history"]
    original_payload = get_background_job_service().get_job(task_id)["payload"]
    _common._set_task_state(task_id, status="failed", progress=incoming_progress,
                           stage="分析失败", detail="合成执行异常", error="原始异常")
    service = get_background_job_service()
    stored = service.get_job(task_id)
    assert stored["status"] == "failed"
    assert stored["progress"] == 37.5
    assert stored["history"] == history
    assert stored["payload"] == original_payload
    assert all(stored["payload"][key] == value for key, value in payload.items())
    assert stored["error"] == "原始异常"
    assert stored["completed_at"]
    client = profile_app.test_client()
    for endpoint in ["/api/script-hub/task/" + task_id, "/api/script-hub/jobs/" + task_id]:
        response = client.get(endpoint)
        assert response.status_code == 200, response.json
        task = response.json.get("job", response.json)
        assert task["status"] == "failed" and task["progress"] == 37.5
    assert _common._get_task_state(task_id)["progress"] == 37.5


def test_failure_before_work_does_not_create_full_progress(profile_app, monkeypatch, task_id):
    monkeypatch.setenv("JOB_QUEUE", "threadpool")
    _common._set_task_state(task_id, status="failed", progress=100., stage="提交失败", error="合成异常")
    assert _common._get_task_state(task_id)["progress"] == 0
    assert get_background_job_service().get_job(task_id)["progress"] == 0


def test_failure_restores_persisted_progress_and_owner_without_local_state(profile_app, monkeypatch, task_id):
    monkeypatch.setenv("JOB_QUEUE", "threadpool")
    from flask_app.models.database import User, db
    owner = User(username="script-owner", email="script-owner@test.invalid", password_hash="unused")
    db.session.add(owner)
    db.session.commit()
    service = get_background_job_service()
    original = service.create_job(job_id=task_id, job_type="script_hub", module="profile",
                                  user_id=owner.id, payload={"samples": ["001"], "group": "01"})
    service.update_progress(task_id, 76.25, "绘制图表", "已处理当前数据")
    assert task_id not in _common._script_tasks
    _common._set_task_state(task_id, status="failed", progress=100., stage="失败", error="合成异常")
    stored = service.get_job(task_id)
    assert stored["progress"] == 76.25
    assert stored["user_id"] == owner.id
    assert stored["payload"] == original["payload"]
    assert _common._get_task_state(task_id)["progress"] == 76.25


def test_real_profile_failure_preserves_actual_stage_and_source(profile_app, monkeypatch, task_id, tmp_path):
    monkeypatch.setenv("JOB_QUEUE", "threadpool")
    from flask_app.routes.api_script_hub.boxplot import _run_boxplot_task
    source = tmp_path / "Profile.csv"
    source.write_text("sample,group,metric\n001,01,1\n002,01,2\n003,02,8\n004,02,9\n", encoding="utf-8")
    before = source.read_bytes()
    _common._set_task_state(task_id, status="queued", progress=0., module="profile",
                           config_json={"selected_samples": ["missing"]})
    _run_boxplot_task(task_id, results_root=Path(profile_app.config["RESULTS_FOLDER"]),
        datapoint_path=str(source), classification_begin="group", classification_over="group",
        grouptype_fields=["group"], param_begin="metric", param_over="metric",
        selected_samples=["missing"], module_name="profile")
    task = _common._get_task_state(task_id)
    assert task["status"] == "failed" and task["progress"] == 10
    assert [entry["progress"] for entry in task["history"]] == [5, 10]
    assert task["history"][-1]["stage"] == "指标分组分析"
    assert "Selected samples did not match" in task["error"]
    assert source.read_bytes() == before
    client = profile_app.test_client()
    response = client.get("/api/script-hub/task/" + task_id)
    assert response.status_code == 200
    assert response.json["status"] == "failed" and response.json["progress"] == 10
    assert not response.json.get("result")
