import pytest
from unittest.mock import Mock
from flask_app.app import create_app
from flask_app.models.database import db,User
from flask_app.services.background_job_service import get_background_job_service
from flask_app.services.persistent_queue import claim,encode,decode

@pytest.fixture
def application(monkeypatch):
    monkeypatch.setenv('JOB_QUEUE','threadpool')
    app=create_app('testing')
    with app.app_context():
        yield app
        db.session.remove()
        db.drop_all()

def test_atomic_claim_rejects_duplicate_and_cancelled_job(application):
    service=get_background_job_service()
    first=service.create_job(job_type='api_request',module='statistical.analyze')
    assert claim(first['job_id']) is True
    runtime = service.get_job(first['job_id'])['payload']['runtime']
    assert runtime['python'] and runtime['packages']['scikit-learn']
    assert 'r' in runtime and 'architecture' in runtime
    assert claim(first['job_id']) is False
    second=service.create_job(job_type='api_request',module='statistical.analyze')
    service.request_cancel(second['job_id'])
    assert claim(second['job_id']) is False

def test_retry_preserves_original_and_requires_owner(application,monkeypatch):
    from flask_app.routes import api_jobs
    application.config['REQUIRE_LOGIN']=True
    owner = User(username='owner',email='one@test.invalid',password_hash='unused')
    other = User(username='other',email='two@test.invalid',password_hash='unused')
    db.session.add_all([owner, other]);db.session.commit()
    service=get_background_job_service()
    original=service.create_job(job_type='api_request',module='statistical.analyze',user_id=owner.id,payload={'file_id':'sample'})
    service.fail_job(original['job_id'],'test failure')
    queue=Mock();monkeypatch.setattr(api_jobs,'get_job_queue',lambda:queue)
    client=application.test_client()
    with client.session_transaction() as session:session['_user_id']=str(other.id);session['_fresh']=True
    assert client.post('/api/jobs/'+original['job_id']+'/retry').status_code==404
    from flask import g
    g.pop('_login_user', None)
    with client.session_transaction() as session:session['_user_id']=str(owner.id);session['_fresh']=True
    response=client.post('/api/jobs/'+original['job_id']+'/retry')
    assert response.status_code==200,response.json
    fresh=service.get_job(response.json['job_id'])
    assert fresh['job_id']!=original['job_id'] and fresh['payload']['file_id']=='sample'
    assert service.get_job(original['job_id'])['status']=='failed'
    assert client.post('/api/jobs/'+fresh['job_id']+'/retry').status_code==409
    queue.submit.assert_called_once()

def test_no_worker_does_not_fall_back_to_api_process(application,monkeypatch):
    from flask_app.services.job_queue import RedisJobQueue
    from types import SimpleNamespace
    service=get_background_job_service()
    job=service.create_job(job_type='api_request',module='statistical.analyze')
    queue=object.__new__(RedisJobQueue)
    queue._queue=Mock();queue._queue.enqueue.return_value=SimpleNamespace(id='analysis-'+job['job_id'])
    queue.fallback=None
    queue.submit(job['job_id'],lambda:None,module='statistical.analyze')
    assert queue._queue.enqueue.call_args.kwargs['job_id']=='analysis-'+job['job_id']
    assert service.get_job(job['job_id'])['payload']['queue_backend']=='redis'
    assert service.get_job(job['job_id'])['status']=='queued'

def test_enqueue_uses_module_timeout_override_and_default(application, monkeypatch):
    from types import SimpleNamespace
    from flask_app.services import persistent_queue

    service = get_background_job_service()
    module_job = service.create_job(job_type='api_request', module='analysis-batch')
    default_job = service.create_job(job_type='api_request', module='topclone')
    queue = Mock()
    queue.enqueue.side_effect = [SimpleNamespace(id='rq-batch'), SimpleNamespace(id='rq-default')]
    monkeypatch.setenv('ANALYSIS_TIMEOUT_SECONDS', '7200')
    monkeypatch.setenv('ANALYSIS_TIMEOUTS_JSON', '{"analysis-batch": 14400}')

    persistent_queue.enqueue(lambda _: None, module_job['job_id'], module_job['job_id'], queue=queue)
    persistent_queue.enqueue(lambda _: None, default_job['job_id'], default_job['job_id'], queue=queue)

    assert [call.kwargs['job_timeout'] for call in queue.enqueue.call_args_list] == [14400, 7200]

def test_module_timeout_configuration_rejects_invalid_values(application, monkeypatch):
    from flask_app.services.persistent_queue import _job_timeout_seconds

    job = get_background_job_service().create_job(job_type='api_request', module='ml-analysis')
    monkeypatch.setenv('ANALYSIS_TIMEOUTS_JSON', '{"ml-analysis": 0}')
    with pytest.raises(ValueError, match='positive integer'):
        _job_timeout_seconds(job['job_id'])

def test_script_call_retains_paths_for_independent_worker(tmp_path):
    original={'results_root':tmp_path,'selected':['TRA'],'mapping':{'cdr3':'sequence'}}
    assert decode(encode(original))==original

def test_optional_project_is_null_for_mysql_foreign_key(application):
    service=get_background_job_service()
    created=service.create_job(job_type='api_request',module='analysis.execute-unified',project_id='')
    assert created['project_id'] is None
    stored=service.upsert_job('script_optional_project',{'module':'pgen-analysis','project_id':' '})
    assert stored['project_id'] is None

def test_nested_script_executes_without_waiting_for_another_worker(application,monkeypatch):
    import rq
    from flask_app.services import persistent_queue
    monkeypatch.setenv('JOB_QUEUE','redis')
    monkeypatch.setattr(rq,'get_current_job',lambda:object())
    run=Mock(return_value={'completed':True})
    queued=Mock()
    monkeypatch.setattr(persistent_queue,'execute_script',run)
    monkeypatch.setattr(persistent_queue,'enqueue',queued)
    result=persistent_queue.ScriptExecutor().submit(test_nested_script_executes_without_waiting_for_another_worker,'child-test',value='sample')
    assert result=={'completed':True}
    run.assert_called_once_with('child-test')
    queued.assert_not_called()

def test_api_retry_does_not_execute_user_supplied_script_call(application,monkeypatch):
    from flask_app.routes import api_jobs
    application.config['REQUIRE_LOGIN']=False
    service=get_background_job_service()
    original=service.create_job(job_type='api_request',module='statistical.analyze',payload={'script_call':{'function':'untrusted'}})
    service.fail_job(original['job_id'],'invalid input')
    queue=Mock();monkeypatch.setattr(api_jobs,'get_job_queue',lambda:queue)
    response=application.test_client().post('/api/jobs/'+original['job_id']+'/retry')
    assert response.status_code==200
    queue.submit.assert_called_once()
    assert queue.submit.call_args.kwargs['module']=='statistical.analyze'

@pytest.mark.parametrize('kind',['chord','treemap'])
def test_worker_chart_progress_persists_restored_task_snapshot(application,monkeypatch,kind):
    import importlib
    route=importlib.import_module('flask_app.routes.api_'+kind)
    task_id='restored_'+kind
    tasks=getattr(route,'_'+kind+'_tasks')
    monkeypatch.setenv('JOB_QUEUE','redis')
    tasks[task_id]={'task_id':task_id,'status':'running','progress':42,'user_id':None}
    try:
        route._sync_task_state(task_id)
        assert get_background_job_service().get_job(task_id)['progress']==42
    finally:
        tasks.pop(task_id,None)

@pytest.mark.parametrize('callback_name',['record_failure','record_killed'])
def test_worker_failure_ends_only_unfinished_descendants(application,monkeypatch,callback_name):
    import importlib
    from types import SimpleNamespace
    from flask_app.services import persistent_queue
    monkeypatch.setattr(importlib.import_module('flask_app.app'),'app',application)
    service=get_background_job_service()
    parent=service.create_job(job_type='api_request',module='charts.combined')
    def child(parent_id):
        return service.create_job(job_type='chord',module='chord',extra={'parent_job_id':parent_id,'script_call':{'saved':True}})
    active=child(parent['job_id'])
    service.mark_running(active['job_id'])
    nested=child(active['job_id'])
    completed=child(parent['job_id'])
    service.complete_job(completed['job_id'],{'output':'preserve'})
    unrelated=child('another-parent')
    task=SimpleNamespace(meta={'analysis_job_id':parent['job_id']})
    if callback_name=='record_failure':
        persistent_queue.record_failure(task,None,RuntimeError,RuntimeError('worker lost'),None)
    else:
        persistent_queue.record_killed(task,123,9,None)
    for entry in (active,nested):
        stored=service.get_job(entry['job_id'])
        assert stored['status']=='interrupted' and stored['completed_at']
        assert stored['payload']['script_call']=={'saved':True}
    assert service.get_job(completed['job_id'])['status']=='completed'
    assert service.get_job(completed['job_id'])['result']=={'output':'preserve'}
    assert service.get_job(unrelated['job_id'])['status']=='queued'


def test_script_worker_rejects_input_changed_after_queueing(application, monkeypatch, tmp_path):
    import importlib
    from flask_app.exceptions import ValidationError
    from flask_app.services.persistent_queue import execute_script
    from flask_app.routes.api_script_hub import profile_analysis
    monkeypatch.setattr(importlib.import_module('flask_app.app'), 'app', application)
    computation = Mock()
    monkeypatch.setattr(profile_analysis, '_run_topclone_task', computation)
    path = tmp_path / 'profile.csv'
    path.write_text('sample,group\n001,A\n002,B\n', encoding='utf-8')
    service = get_background_job_service()
    job = service.create_job(job_type='script_hub', module='topclone', payload={
        'input_assets': [{'asset_type': 'profile', 'path': str(path)}],
        'script_call': {'function': 'flask_app.routes.api_script_hub.profile_analysis:_run_topclone_task', 'kwargs': {}, 'with_app_context': False},
    })
    path.write_text('sample,group\n001,A\n001,B\n', encoding='utf-8')
    with pytest.raises(ValidationError, match='输入数据检查未通过'):
        execute_script(job['job_id'])
    computation.assert_not_called()


def test_script_worker_revalidates_duplicate_sample_ids_with_saved_batch_field(application, monkeypatch, tmp_path):
    import importlib
    from flask_app.routes.api_script_hub import profile_analysis
    from flask_app.services.persistent_queue import execute_script

    monkeypatch.setattr(importlib.import_module('flask_app.app'), 'app', application)
    computation = Mock()
    monkeypatch.setattr(profile_analysis, '_run_topclone_task', computation)
    path = tmp_path / 'profile-batches.csv'
    path.write_text('sample,batch,group\nS1,batch-a,A\nS1,batch-b,B\n', encoding='utf-8')
    service = get_background_job_service()
    job = service.create_job(job_type='script_hub', module='topclone', payload={
        'input_assets': [{'asset_type': 'profile', 'path': str(path)}],
        'config_json': {'batch_field': 'batch'},
        'script_call': {'function': 'flask_app.routes.api_script_hub.profile_analysis:_run_topclone_task', 'kwargs': {}, 'with_app_context': False},
    })

    execute_script(job['job_id'])

    computation.assert_called_once_with(job['job_id'])


def test_optional_analysis_steps_survive_json_queue_serialization():
    import json
    original = {'optional_steps': {5, 7}, 'empty_steps': set()}
    persisted = json.loads(json.dumps(encode(original)))
    assert decode(persisted) == original


@pytest.mark.parametrize('queue_status', ['failed','stopped','canceled','finished','started','queued'])
def test_poll_recovers_only_confirmed_terminal_queue_jobs(application, monkeypatch, queue_status):
    from flask_app.services import persistent_queue
    service = get_background_job_service()
    parent = service.create_job(job_type='api_request', module='charts.combined')
    child = service.create_job(job_type='chord', module='chord', extra={'parent_job_id':parent['job_id']})
    task = Mock(meta={'analysis_job_id':parent['job_id']})
    task.get_status.return_value = queue_status
    queue = Mock()
    queue.fetch_job.return_value = task
    monkeypatch.setattr(persistent_queue, 'redis_queue', lambda:queue)
    service.upsert_job(parent['job_id'], {'queue_backend':'redis','rq_job_id':'rq-test'})
    stored = service.get_job(parent['job_id'])
    terminal = queue_status in {'failed','stopped','canceled','finished'}
    assert stored['status'] == ('interrupted' if terminal else 'queued')
    assert service.get_job(child['job_id'])['status'] == ('interrupted' if terminal else 'queued')
    if terminal:
        assert stored['completed_at']


def test_poll_does_not_infer_failure_from_unavailable_redis(application, monkeypatch):
    from redis.exceptions import ConnectionError
    from flask_app.services import persistent_queue
    service = get_background_job_service()
    parent = service.create_job(job_type='api_request', module='statistical.analyze')
    monkeypatch.setattr(persistent_queue, 'redis_queue', Mock(side_effect=ConnectionError('offline')))
    service.upsert_job(parent['job_id'], {'queue_backend':'redis','rq_job_id':'rq-test'})
    assert service.get_job(parent['job_id'])['status'] == 'queued'


def test_worker_restores_result_registration_context(application, monkeypatch):
    monkeypatch.setenv('JOB_QUEUE','redis')
    from importlib import import_module
    from flask_app.models.database import Project
    from flask_app.routes.api_script_hub import _common, profile_analysis
    from flask_app.services.persistent_queue import execute_script
    monkeypatch.setattr(import_module('flask_app.app'), 'app', application)
    db.session.add(Project(id='worker-project',name='结果登记回归'));db.session.commit()
    saved = Mock(return_value='registered-result')
    monkeypatch.setattr(_common, '_persist_script_result', saved)
    def compute(task_id, **kwargs):
        _common._complete_script_task(task_id,module_name='topclone',detail='完成',result={'job_id':'report-id'},history=[])
    monkeypatch.setattr(profile_analysis, '_run_topclone_task', compute)
    service=get_background_job_service()
    context={'analysis_signature':'saved-signature','input_assets':[{'path':'/input.csv'}], 'config_json':{'group_field':'group'}}
    job=service.create_job(job_type='script_hub',module='topclone',project_id='worker-project',payload={**context,
        'status':'completed','user_id':999,
        'script_call':{'function':'flask_app.routes.api_script_hub.profile_analysis:_run_topclone_task','kwargs':{},'with_app_context':False}})
    execute_script(job['job_id'])
    saved.assert_called_once()
    for key,value in context.items(): assert saved.call_args.kwargs[key]==value
    result=service.get_job(job['job_id'])
    assert result['result']['result_id']=='registered-result'
    assert result['user_id'] is None


@pytest.mark.parametrize("reviewed", [False, True])
def test_script_worker_requires_saved_sample_alignment_review(application, monkeypatch, tmp_path, reviewed):
    import importlib
    from flask_app.exceptions import ValidationError
    from flask_app.routes.api_script_hub import profile_analysis
    from flask_app.services.persistent_queue import execute_script

    monkeypatch.setattr(importlib.import_module('flask_app.app'), 'app', application)
    computation = Mock()
    monkeypatch.setattr(profile_analysis, '_run_topclone_task', computation)
    profile = tmp_path / 'profile.csv'
    profile.write_text('sample,group\n001,A\n002,B\n', encoding='utf-8')
    expression = tmp_path / 'expression.csv'
    expression.write_text('Gene,001,003\nG1,1,2\n', encoding='utf-8')
    service = get_background_job_service()
    job = service.create_job(job_type='script_hub', module='topclone', payload={
        'input_assets': [
            {'asset_type': 'profile', 'path': str(profile)},
            {'asset_type': 'transcriptome', 'path': str(expression)},
        ],
        'config_json': {'input_alignment': {'reviewed': reviewed}},
        'script_call': {'function': 'flask_app.routes.api_script_hub.profile_analysis:_run_topclone_task', 'kwargs': {}, 'with_app_context': False},
    })

    if reviewed:
        execute_script(job['job_id'])
        computation.assert_called_once_with(job['job_id'])
    else:
        with pytest.raises(ValidationError, match='样本编号不完全一致'):
            execute_script(job['job_id'])
        computation.assert_not_called()


def test_default_job_lifecycle_uses_chinese_text_and_keeps_status_contract(application):
    service = get_background_job_service()
    waiting = service.create_job(job_type="api_request", module="statistical.analyze")
    assert waiting["status"] == "queued" and waiting["stage"] == "等待执行"
    assert waiting["detail"] == "任务已创建，等待开始。"
    completed = service.complete_job(waiting["job_id"])
    assert completed["status"] == "completed" and completed["stage"] == "已完成"
    assert completed["detail"] == "任务已完成。"
    second = service.create_job(job_type="api_request", module="statistical.analyze")
    cancelled = service.request_cancel(second["job_id"])
    assert cancelled["status"] == "cancelled" and cancelled["stage"] == "已取消"
    assert cancelled["detail"] == "任务已在开始前取消。"


@pytest.mark.parametrize("module", ["umapin", "analysis-batch"])
def test_running_cancel_is_pending_and_poll_cannot_confirm(application, module):
    service = get_background_job_service()
    job = service.create_job(job_type="script_hub", module=module)
    job_id = job["job_id"]
    assert claim(job_id)
    service.update_progress(job_id, 25, "计算中")
    client = application.test_client()
    for path in (f"/api/jobs/{job_id}/cancel", f"/api/script-hub/jobs/{job_id}/cancel"):
        response = client.post(path)
        assert response.status_code == 200, response.json
        assert response.json["job"]["status"] == "running"
        assert response.json["job"]["stage"] == "正在取消"
    service.upsert_job(job_id, {"status": "running", "progress": 50, "stage": "旧快照", "allocated_output_dirs": ["/tmp/synthetic"]})
    for path in (f"/api/jobs/{job_id}", f"/api/script-hub/task/{job_id}"):
        response = client.get(path)
        stored = response.json.get("job", response.json)
        assert stored["status"] == "running" and stored["cancel_requested"] is True
        assert stored["stage"] == "正在取消" and stored["completed_at"] is None
        assert stored["progress"] == 25
    assert client.post(f"/api/jobs/{job_id}/retry").status_code == 409
    assert client.delete(f"/api/jobs/{job_id}?delete_results=1").status_code == 409
    assert service.get_job(job_id)["payload"]["allocated_output_dirs"] == ["/tmp/synthetic"]
    service.cancel_job(job_id)
    assert client.get(f"/api/script-hub/task/{job_id}").json["status"] == "cancelled"


def test_finished_job_ignores_cancel_request(application):
    service = get_background_job_service()
    job = service.create_job(job_type="script_hub", module="umapin")
    service.complete_job(job["job_id"], {"preserve": True})
    cancelled = service.request_cancel(job["job_id"])
    assert cancelled["status"] == "completed" and cancelled["cancel_requested"] is False
    assert cancelled["result"] == {"preserve": True}


def test_cancel_at_completion_discards_result_without_persisting(application, monkeypatch):
    from flask_app.services import generic_result_storage
    persist = Mock()
    monkeypatch.setattr(generic_result_storage, "persist_generic_result", persist)
    service = get_background_job_service()
    job = service.create_job(job_type="api_request", module="statistical.analyze")
    assert claim(job["job_id"])
    service.request_cancel(job["job_id"])
    finished = service.complete_job(job["job_id"], {"output": "unconfirmed"})
    assert finished["status"] == "cancelled" and finished["result"] == {}
    persist.assert_not_called()


def test_script_cancellation_confirms_only_after_nested_work_unwinds(application, monkeypatch):
    import importlib
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from flask_app.routes.api_script_hub import _common, profile_analysis
    from flask_app.services.persistent_queue import execute_script
    monkeypatch.setattr(importlib.import_module("flask_app.app"), "app", application)
    service = get_background_job_service()
    observations = []
    def computation(job_id):
        release = Event()
        with ThreadPoolExecutor(max_workers=1) as nested:
            future = nested.submit(release.wait)
            try:
                service.request_cancel(job_id)
                _common._record_stage(job_id, 70, "不应覆盖", "检查点")
            except _common.ScriptTaskCancelled:
                current = service.get_job(job_id)
                observations.append((current["status"], current["completed_at"], future.done()))
                release.set()
                raise
    monkeypatch.setattr(profile_analysis, "_run_topclone_task", computation)
    job = service.create_job(job_type="script_hub", module="topclone", payload={
        "script_call": {"function": "flask_app.routes.api_script_hub.profile_analysis:_run_topclone_task", "kwargs": {}, "with_app_context": False},
    })
    finished = execute_script(job["job_id"])
    assert observations == [("running", None, False)]
    assert finished["status"] == "cancelled" and finished["completed_at"]
    assert finished["progress"] != 100


def test_local_script_executor_confirms_cancellation(application):
    from flask_app.routes.api_script_hub import _common
    from flask_app.services.persistent_queue import _execute_local_script
    service = get_background_job_service()
    job = service.create_job(job_type="script_hub", module="topclone")
    assert claim(job["job_id"])
    def computation(job_id, app_context_app=None):
        service.request_cancel(job_id)
        _common._record_stage(job_id, 80, "不应覆盖", "检查点")
    _execute_local_script(computation, job["job_id"], {"app_context_app": application})
    assert service.get_job(job["job_id"])["status"] == "cancelled"


def test_generic_cancel_checkpoint_with_chinese_error_is_not_failure(application):
    service = get_background_job_service()
    job = service.create_job(job_type="api_request", module="statistical.analyze")
    def computation(context):
        service.request_cancel(context.job_id)
        context.raise_if_cancelled()
    service._run(job["job_id"], computation, (), {})
    finished = service.get_job(job["job_id"])
    assert finished["status"] == "cancelled" and not finished["error"]


def test_generic_worker_failure_after_cancel_confirms_cancellation(application):
    service = get_background_job_service()
    job = service.create_job(job_type="api_request", module="statistical.analyze")
    assert claim(job["job_id"])
    service.request_cancel(job["job_id"])
    finished = service.fail_job(job["job_id"], "用户已取消任务")
    assert finished["status"] == "cancelled" and finished["completed_at"]
    assert not finished["error"]
