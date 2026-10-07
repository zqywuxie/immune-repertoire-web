"""Batch plans must end with their confirmed failed RQ owner, including unsubmitted items."""
import copy
import importlib
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from flask_app.app import create_app
from flask_app.models.database import db
from flask_app.services.background_job_service import get_background_job_service
from flask_app.services import persistent_queue, analysis_batch_service

@pytest.fixture
def application(monkeypatch):
    monkeypatch.setenv("JOB_QUEUE", "threadpool")
    app = create_app("testing")
    app.config["INTERNAL_MODE"] = True
    monkeypatch.setattr(importlib.import_module("flask_app.app"), "app", app)
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()

def seed():
    service = get_background_job_service()
    items = analysis_batch_service.validate_batch({"items": [
        {"module":"profile", "payload":{"metric":"saved"}},
        {"module":"umapin", "payload":{"category_col":"Category"}},
        {"module":"volcano", "payload":{"input_mode":"usage"}, "depends_on":[1]},
        {"module":"profile", "payload":{"metric":"independent"}},
    ]})
    parent = service.create_job(job_type="analysis_batch", module="analysis-batch",
        payload={"asset_set":"Set2", "task_name":"保留原批次", "items":items})
    done = service.create_job(job_type="script_hub", module="profile",
        payload={"parent_job_id":parent["job_id"], "hidden_from_default_list":True})
    service.complete_job(done["job_id"], {"output":"preserve-result", "sample_count":12})
    active = service.create_job(job_type="script_hub", module="umapin",
        payload={"parent_job_id":parent["job_id"], "script_call":{"saved":True}})
    service.update_progress(active["job_id"],35,"分析计算","已完成真实记录的阶段")
    items[0].update(status="completed",job_id=done["job_id"])
    items[1].update(status="running",job_id=active["job_id"])
    service.upsert_job(parent["job_id"],{"status":"running","progress":25,"items":items,"result":{"custom":"preserved"}})
    unrelated = service.create_job(job_type="script_hub", module="profile")
    return service, parent["job_id"], done["job_id"], active["job_id"], unrelated["job_id"]

def assert_stopped(service, parent_id, done_id, active_id, unrelated_id, status):
    stored = service.get_job(parent_id)
    assert stored["status"] == status
    assert stored["progress"] == 25
    assert [item["status"] for item in stored["payload"]["items"]] == ["completed","interrupted","interrupted","interrupted"]
    assert "尚未执行" in stored["payload"]["items"][2]["error"]
    assert stored["payload"]["items"][2]["depends_on"] == [1]
    assert stored["result"]["completed_count"] == 1
    assert stored["result"]["total_count"] == 4
    assert stored["result"]["partial_success"] is True
    assert stored["result"]["custom"] == "preserved"
    assert stored["result"]["items"] == stored["payload"]["items"]
    assert service.get_job(done_id)["status"] == "completed"
    assert service.get_job(done_id)["result"] == {"output":"preserve-result","sample_count":12}
    assert service.get_job(active_id)["status"] == "interrupted"
    assert service.get_job(active_id)["progress"] == 35
    assert service.get_job(active_id)["payload"]["script_call"] == {"saved":True}
    assert service.get_job(unrelated_id)["status"] == "queued"
    return stored

@pytest.mark.parametrize("callback", ["record_failure","record_killed"])
def test_callback_ends_unsubmitted_plan_items_and_preserves_results(application, callback):
    service, parent_id, done_id, active_id, unrelated_id = seed()
    task = SimpleNamespace(meta={"analysis_job_id":parent_id})
    if callback == "record_failure":
        persistent_queue.record_failure(task,None,RuntimeError,RuntimeError("worker stopped"),None)
    else:
        persistent_queue.record_killed(task,123,9,None)
    assert_stopped(service,parent_id,done_id,active_id,unrelated_id,"failed" if callback=="record_failure" else "interrupted")

def test_confirmed_queue_stop_settles_plan_through_real_task_api(application, monkeypatch):
    service, parent_id, done_id, active_id, unrelated_id = seed()
    task = Mock(meta={"analysis_job_id":parent_id})
    task.get_status.return_value = "stopped"
    queue = Mock()
    queue.fetch_job.return_value = task
    monkeypatch.setattr(persistent_queue,"redis_queue",lambda:queue)
    service.upsert_job(parent_id,{"queue_backend":"redis","rq_job_id":"rq-owned"})
    response = application.test_client().get("/api/jobs/"+parent_id)
    assert response.status_code == 200, response.json
    assert [item["status"] for item in response.json["job"]["payload"]["items"]] == ["completed","interrupted","interrupted","interrupted"]
    assert_stopped(service,parent_id,done_id,active_id,unrelated_id,"interrupted")

def test_unavailable_queue_does_not_end_waiting_plan(application, monkeypatch):
    from redis.exceptions import ConnectionError
    service, parent_id, done_id, active_id, unrelated_id = seed()
    monkeypatch.setattr(persistent_queue,"redis_queue",Mock(side_effect=ConnectionError("temporary offline")))
    service.upsert_job(parent_id,{"queue_backend":"redis","rq_job_id":"rq-owned"})
    stored=service.get_job(parent_id)
    assert stored["status"] == "running"
    assert [item["status"] for item in stored["payload"]["items"]] == ["completed","running","queued","queued"]
    assert service.get_job(active_id)["status"] == "running"

def test_retry_has_clean_plan_and_original_result_and_dependencies_survive(application, monkeypatch):
    service, parent_id, done_id, active_id, unrelated_id = seed()
    persistent_queue.record_killed(SimpleNamespace(meta={"analysis_job_id":parent_id}),123,9,None)
    original=assert_stopped(service,parent_id,done_id,active_id,unrelated_id,"interrupted")
    saved=copy.deepcopy(original)
    enqueue=Mock()
    monkeypatch.setattr(persistent_queue,"enqueue",enqueue)
    response=application.test_client().post("/api/jobs/"+parent_id+"/retry")
    assert response.status_code == 200, response.json
    fresh=service.get_job(response.json["job_id"])
    assert fresh["job_id"] != parent_id
    assert fresh["payload"]["retry_of"] == parent_id
    assert fresh["payload"]["asset_set"] == "Set2"
    assert fresh["payload"]["items"][2]["depends_on"] == [1]
    assert all(item["status"]=="queued" and not item["job_id"] and not item["error"] for item in fresh["payload"]["items"])
    assert service.get_job(parent_id) == saved
    enqueue.assert_called_once()

def test_duplicate_stop_keeps_existing_terminal_items_and_summary(application):
    service, parent_id, done_id, active_id, unrelated_id = seed()
    task=SimpleNamespace(meta={"analysis_job_id":parent_id})
    persistent_queue.record_killed(task,123,9,None)
    first=assert_stopped(service,parent_id,done_id,active_id,unrelated_id,"interrupted")
    persistent_queue.record_killed(task,123,9,None)
    second=service.get_job(parent_id)
    assert second["payload"]["items"] == first["payload"]["items"]
    assert second["result"] == first["result"]
    assert second["completed_at"] == first["completed_at"]

def test_enqueue_failure_ends_unsubmitted_plan(application, monkeypatch):
    service=get_background_job_service()
    parent=service.create_job(job_type="analysis_batch",module="analysis-batch",payload={
        "asset_set":"Set2","items":analysis_batch_service.validate_batch({"items":[
            {"module":"profile","payload":{}},{"module":"profile","payload":{}}
        ]})
    })
    monkeypatch.setattr(persistent_queue,"redis_queue",Mock(side_effect=RuntimeError("queue rejected")))
    with pytest.raises(RuntimeError,match="queue rejected"):
        persistent_queue.enqueue(analysis_batch_service.execute_batch,parent["job_id"],parent["job_id"])
    stored=service.get_job(parent["job_id"])
    assert stored["status"]=="failed" and stored["progress"]==0
    assert all(item["status"]=="interrupted" and "尚未执行" in item["error"] for item in stored["payload"]["items"])
    assert stored["result"]["completed_count"]==0
    assert stored["result"]["partial_success"] is False

def test_worker_stop_recovers_completed_child_before_plan_write(application):
    service, parent_id, done_id, active_id, unrelated_id = seed()
    items = copy.deepcopy(service.get_job(parent_id)["payload"]["items"])
    # The worker completed its real child but exited before saving the plan outcome.
    items[0].update(status="running", error="old placeholder")
    service.upsert_job(parent_id, {"items":items})
    persistent_queue.record_killed(SimpleNamespace(meta={"analysis_job_id":parent_id}),123,9,None)
    stored = assert_stopped(service,parent_id,done_id,active_id,unrelated_id,"interrupted")
    assert stored["payload"]["items"][0]["error"] == ""

def test_worker_stop_keeps_actual_child_failure_and_existing_blocked_reason(application):
    service, parent_id, done_id, active_id, unrelated_id = seed()
    service.fail_job(active_id, "实际子分析失败原因")
    items = copy.deepcopy(service.get_job(parent_id)["payload"]["items"])
    items[2].update(status="failed", error="前置结果不可用", blocked_by=[1])
    service.upsert_job(parent_id, {"items":items})
    persistent_queue.record_killed(SimpleNamespace(meta={"analysis_job_id":parent_id}),123,9,None)
    stored = service.get_job(parent_id)
    assert [item["status"] for item in stored["payload"]["items"]] == ["completed","failed","failed","interrupted"]
    assert stored["payload"]["items"][1]["error"] == "实际子分析失败原因"
    assert stored["payload"]["items"][2] == items[2]
    assert stored["result"]["completed_count"] == 1 and stored["result"]["partial_success"] is True
    assert service.get_job(active_id)["progress"] == 35
    assert service.get_job(unrelated_id)["status"] == "queued"

def test_dispatch_binds_completed_reused_child_to_current_batch(application, monkeypatch):
    from flask import jsonify
    service, parent_id, done_id, active_id, unrelated_id = seed()
    reused = service.create_job(job_type="script_hub", module="profile", payload={"reused_result":True})
    service.complete_job(reused["job_id"], {"viewer_url":"/saved/viewer.html","reused_result":True})
    parent = service.get_job(parent_id)
    original_done = copy.deepcopy(service.get_job(done_id))
    monkeypatch.setattr(application, "full_dispatch_request",
        lambda: jsonify(success=True, task_id=reused["job_id"], reused_result=True))
    token = analysis_batch_service.batch_child_context.set((parent_id, 3))
    try:
        child_id = analysis_batch_service.dispatch_batch_item(parent,parent["payload"]["items"][3])
    finally:
        analysis_batch_service.batch_child_context.reset(token)
    assert child_id == reused["job_id"]
    child = service.get_job(child_id)
    assert child["parent_job_id"] == parent_id and child["hidden_from_default_list"] is True
    assert child["status"] == "completed" and child["progress"] == 100
    assert child["result"] == {"viewer_url":"/saved/viewer.html","reused_result":True}
    assert service.get_job(parent_id)["payload"]["items"][3]["job_id"] == child_id
    assert service.get_job(done_id) == original_done
