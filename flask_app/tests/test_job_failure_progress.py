import pytest
from flask_app.tests.test_persistent_queue import application
from flask_app.services.background_job_service import get_background_job_service

@pytest.mark.parametrize("reported_progress", [0, 35, 87.25])
def test_failure_preserves_last_progress_and_original_inputs(application, reported_progress):
    service = get_background_job_service()
    original = service.create_job(job_type="api_request", module="statistical.analyze", payload={"file_id":"synthetic"})
    if reported_progress:
        service.update_progress(original["job_id"], reported_progress, "计算分组比较", "检查合成数据")
    final = service.fail_job(original["job_id"], "缺少对照组", "synthetic traceback")
    assert final["status"] == "failed" and final["completed_at"]
    assert final["progress"] == reported_progress
    assert final["payload"]["file_id"] == "synthetic"
    assert final["error"] == "缺少对照组" and final["detail"] == "synthetic traceback"
    assert final["history"][-1]["progress"] == reported_progress
    assert all(entry["progress"] != 100 for entry in final["history"])

def test_real_threadpool_runner_failure_does_not_report_success(application):
    service = get_background_job_service()
    original = service.create_job(job_type="api_request", module="statistical.analyze")
    def computation(context):
        context.update(37.5, "计算分组比较", "检查合成数据")
        raise ValueError("synthetic worker failure")
    service._run(original["job_id"], computation, (), {})
    final = service.get_job(original["job_id"])
    assert final["status"] == "failed" and final["progress"] == 37.5
    assert final["started_at"] and final["completed_at"]
    assert "ValueError: synthetic worker failure" in final["detail"]
    assert service.update_progress(original["job_id"], 100, "迟到成功")["status"] == "failed"
    assert service.get_job(original["job_id"])["progress"] == 37.5

def test_failure_does_not_replace_a_completed_terminal_job(application):
    service = get_background_job_service()
    original = service.create_job(job_type="api_request", module="statistical.analyze")
    service.upsert_job(original["job_id"], {"status":"completed", "progress":100})
    final = service.fail_job(original["job_id"], "late failure")
    assert final["status"] == "completed" and final["progress"] == 100
    assert not final["error"]
