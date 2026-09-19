import pytest
from flask import Flask
from flask_app.models.database import db, Project
from flask_app.services.background_job_service import get_background_job_service
from flask_app.services import analysis_batch_service as batch


@pytest.fixture
def app():
    from flask_app.routes.api_script_hub import script_hub_bp
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    app.register_blueprint(script_hub_bp)
    from flask_app.routes.api_jobs import jobs_bp
    app.register_blueprint(jobs_bp)
    with app.app_context():
        db.create_all()
        db.session.add(Project(id="project",name="批次测试")); db.session.commit()
        yield app
        db.session.remove(); db.drop_all()


def make_parent():
    service = get_background_job_service()
    return service.create_job(job_type="analysis_batch",module="analysis-batch",project_id="project",payload={"asset_set":"Set2", "items":batch.validate_batch({"items":[{"module":"profile","payload":{}},{"module":"umapin","payload":{}},{"module":"volcano","payload":{}}]})})


def test_api_persists_whole_plan_before_enqueue(app, monkeypatch):
    monkeypatch.setenv("JOB_QUEUE","redis")
    queued=[]
    monkeypatch.setattr("flask_app.services.persistent_queue.enqueue",lambda *args:queued.append(args))
    response=app.test_client().post("/api/script-hub/batches",json={"project_id":"project","asset_set":"Set2","items":[{"module":"profile","payload":{"metric":"x"}},{"module":"umapin","payload":{}}]})
    assert response.status_code==202,response.json
    parent=get_background_job_service().get_job(response.json["job_id"])
    assert len(parent["payload"]["items"])==2
    assert parent["payload"]["items"][0]["payload"]=={"metric":"x"}
    assert queued[0][1:]==(parent["job_id"],parent["job_id"])


def test_worker_continues_independent_items_and_preserves_success(app, monkeypatch):
    service=get_background_job_service()
    parent=make_parent()
    def dispatch(parent,item):
        if item["module"]=="umapin":raise ValueError("分组列缺失")
        child=service.create_job(job_type="script_hub",module=item["module"],project_id="project")
        batch.attach_batch_child(child["job_id"])
        service.complete_job(child["job_id"],{"files":["result.csv"]})
        return child["job_id"]
    monkeypatch.setattr(batch,"dispatch_batch_item",dispatch)
    batch.run_batch_plan(parent["job_id"])
    final=service.get_job(parent["job_id"])
    assert final["status"]=="failed"
    assert final["result"]["completed_count"]==2
    assert final["result"]["partial_success"] is True
    assert final["payload"]["items"][1]["error"]=="分组列缺失"
    for index in (0,2):
        child=service.get_job(final["payload"]["items"][index]["job_id"])
        assert child["parent_job_id"]==parent["job_id"]
        assert child["result"]["files"]==["result.csv"]
    assert batch.batch_child_context.get() is None


def test_cancelled_batch_does_not_submit_remaining_items(app, monkeypatch):
    service=get_background_job_service(); parent=make_parent()
    called=[]
    def dispatch(parent,item):
        called.append(item["module"])
        child=service.create_job(job_type="script_hub",module=item["module"],project_id="project")
        service.complete_job(child["job_id"],{})
        service.cancel_job(parent["job_id"])
        return child["job_id"]
    monkeypatch.setattr(batch,"dispatch_batch_item",dispatch)
    batch.run_batch_plan(parent["job_id"])
    final=service.get_job(parent["job_id"])
    assert called==["profile"]
    assert [item["status"] for item in final["payload"]["items"]]==["completed","cancelled","cancelled"]


def test_invalid_plan_does_not_enqueue(app,monkeypatch):
    monkeypatch.setenv("JOB_QUEUE","redis")
    def unexpected(*args):raise AssertionError("must not enqueue")
    monkeypatch.setattr("flask_app.services.persistent_queue.enqueue",unexpected)
    response=app.test_client().post("/api/script-hub/batches",json={"project_id":"project","asset_set":"Set2","items":[{"module":"shell","payload":{}}]})
    assert response.status_code==400


def test_running_batch_cancel_reaches_child_before_terminal_confirmation(app):
    from flask_app.services.background_job_service import JobContext
    service=get_background_job_service(); parent=make_parent()
    service.mark_running(parent["job_id"])
    child=service.create_job(job_type="script_hub",module="profile",project_id="project",payload={"parent_job_id":parent["job_id"]})
    context=JobContext(service,child["job_id"])
    assert not context.is_cancel_requested()
    requested=service.request_cancel(parent["job_id"])
    assert requested["status"]=="running" and requested["stage"]=="正在取消"
    assert context.is_cancel_requested()
    from flask_app.routes.api_script_hub._common import _script_task_cancel_requested
    assert _script_task_cancel_requested(child["job_id"])
    batch.run_batch_plan(parent["job_id"])
    assert service.get_job(parent["job_id"])["status"]=="cancelled"


def test_queued_batch_cancel_marks_all_plan_items(app):
    service=get_background_job_service(); parent=make_parent()
    cancelled=service.request_cancel(parent["job_id"])
    assert cancelled["status"]=="cancelled"
    assert all(item["status"]=="cancelled" for item in cancelled["payload"]["items"])


def test_dependency_failure_blocks_only_dependent_item(app,monkeypatch):
    service=get_background_job_service(); parent=make_parent()
    items=parent["payload"]["items"]
    items[1]["depends_on"]=[0]
    service.upsert_job(parent["job_id"],{"items":items})
    called=[]
    def dispatch(parent,item):
        called.append(item["module"])
        if item["module"]=="profile":raise ValueError("输入检查失败")
        child=service.create_job(job_type="script_hub",module=item["module"],project_id="project")
        service.complete_job(child["job_id"],{})
        return child["job_id"]
    monkeypatch.setattr(batch,"dispatch_batch_item",dispatch)
    batch.run_batch_plan(parent["job_id"])
    final=service.get_job(parent["job_id"])
    assert called==["profile","volcano"]
    assert final["payload"]["items"][1]["blocked_by"]==[0]
    assert final["result"]["completed_count"]==1


def test_retry_creates_clean_plan_and_preserves_original(app,monkeypatch):
    service=get_background_job_service(); parent=make_parent()
    items=parent["payload"]["items"]
    items[0].update(status="failed",job_id="old-child",error="旧错误")
    items[1]["depends_on"]=[0]
    service.upsert_job(parent["job_id"],{"items":items,"status":"failed"})
    queued=[]
    monkeypatch.setattr("flask_app.services.persistent_queue.enqueue",lambda *args:queued.append(args))
    response=app.test_client().post(f"/api/jobs/{parent['job_id']}/retry")
    assert response.status_code==200,response.json
    fresh=service.get_job(response.json["job_id"])
    assert fresh["job_id"]!=parent["job_id"] and fresh["payload"]["retry_of"]==parent["job_id"]
    assert all(item["status"]=="queued" and not item["job_id"] and not item["error"] for item in fresh["payload"]["items"])
    assert fresh["payload"]["items"][1]["depends_on"]==[0]
    assert service.get_job(parent["job_id"])["payload"]["items"][0]["job_id"]=="old-child"
    assert queued[0][1:]==(fresh["job_id"],fresh["job_id"])


@pytest.mark.parametrize("dependency",[0,1,-1,True,"0"])
def test_rejects_invalid_or_forward_dependencies(dependency):
    from flask_app.exceptions import ValidationError
    with pytest.raises(ValidationError):
        batch.validate_batch({"items":[{"module":"profile","payload":{},"depends_on":[dependency]}]})


def test_batch_upstream_binding_uses_only_current_child(monkeypatch):
    from flask_app.services.analysis_batch_service import validate_batch, bind_batch_upstream
    from flask_app.services import analysis_artifacts
    plan = validate_batch({'items': [
        {'module': 'pep-analysis', 'payload': {}},
        {'module': 'volcano', 'payload': {'input_mode': 'usage'}, 'upstream_from': 0},
    ]})
    assert plan[1]['depends_on'] == [0]
    plan[0].update(status='completed', job_id='current')
    parent = {'project_id': 'p', 'payload': {'asset_set': 'Set2', 'items': plan}}
    monkeypatch.setattr(analysis_artifacts, 'scoped_pep_candidates', lambda *args: [
        {'id': 'old-output', 'job_id': 'old', 'status': 'available'},
        {'id': 'current-output', 'job_id': 'current', 'status': 'available'},
    ])
    payload = {'input_mode': 'usage', 'data_dir': '/stale', 'upstream_artifact_id': 'old-output'}
    bind_batch_upstream(parent, plan[1], payload)
    assert payload['upstream_artifact_id'] == 'current-output'
    assert payload['source_job_id'] == 'current'
    assert 'data_dir' not in payload
