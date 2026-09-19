"""Persistent execution of API and Script Hub tasks through Redis/RQ."""
import importlib
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

def redis_queue():
    from redis import Redis
    from rq import Queue
    connection=Redis.from_url(os.environ.get('REDIS_URL','redis://redis:6379/0'),socket_connect_timeout=5,socket_timeout=10)
    connection.ping()
    return Queue('default',connection=connection,default_timeout=int(os.environ.get('ANALYSIS_TIMEOUT_SECONDS','7200')))

def enqueue(entrypoint,job_id,*args,queue=None):
    from flask_app.services.background_job_service import get_background_job_service
    service=get_background_job_service()
    try:
        task=(queue if queue is not None else redis_queue()).enqueue(entrypoint,*args,job_id='analysis-'+job_id,
             meta={'analysis_job_id':job_id},on_failure=record_failure,job_timeout=int(os.environ.get('ANALYSIS_TIMEOUT_SECONDS','7200')),
             result_ttl=86400,failure_ttl=604800)
        service.upsert_job(job_id,{'queue_backend':'redis','rq_job_id':task.id})
        return task
    except Exception as error:
        service.fail_job(job_id,'任务入队失败：'+str(error))
        raise

def claim(job_id):
    """An atomic database transition prevents duplicate deliveries executing twice."""
    from flask_app.models.database import db,AnalysisJob
    count=AnalysisJob.query.filter(AnalysisJob.id==job_id,AnalysisJob.status=='queued',AnalysisJob.cancel_requested.is_(False)).update(
        {'status':'running','started_at':datetime.now(timezone.utc).replace(tzinfo=None)},synchronize_session=False)
    db.session.commit()
    db.session.expire_all()
    if count == 1:
        from flask_app.services.runtime_provenance import runtime_provenance
        job = db.session.get(AnalysisJob, job_id)
        job.payload = {**(job.payload or {}), 'runtime': runtime_provenance()}
        db.session.commit()
    return count==1

def interrupt_child_jobs(parent_job_id):
    """End unfinished inline children when their owning RQ process fails."""
    from flask_app.models.database import AnalysisJob
    from flask_app.services.background_job_service import get_background_job_service
    service = get_background_job_service()
    pending = [parent_job_id]
    visited = {parent_job_id}
    while pending:
        parent_id = pending.pop()
        children = AnalysisJob.query.filter(
            AnalysisJob.payload["parent_job_id"].as_string() == parent_id
        ).all()
        for child in children:
            if child.id in visited:
                continue
            visited.add(child.id)
            pending.append(child.id)
            if child.status in {"queued", "running"}:
                service.upsert_job(child.id, {
                    "status": "interrupted",
                    "detail": "所属工作进程已中断，请从组合分析任务重试。",
                })


def record_failure(rq_job,connection,exc_type,exc_value,traceback):
    from flask_app.app import app
    from flask_app.services.background_job_service import get_background_job_service
    with app.app_context():
        job_id=rq_job.meta.get('analysis_job_id')
        if job_id:
            get_background_job_service().fail_job(job_id,'工作进程失败：'+str(exc_value))
            interrupt_child_jobs(job_id)

def record_killed(rq_job,retpid,ret_val,rusage):
    from flask_app.app import app
    from flask_app.services.background_job_service import get_background_job_service
    with app.app_context():
        job_id=rq_job.meta.get('analysis_job_id')
        if job_id:
            get_background_job_service().upsert_job(job_id,{'status':'interrupted','detail':'工作进程已中断，请检查资源和参数后重试。'})
            interrupt_child_jobs(job_id)

def encode(value):
    if isinstance(value,set):return {'__worker_set__':[encode(item) for item in sorted(value,key=repr)]}
    if isinstance(value,Path):return {'__worker_path__':str(value)}
    if isinstance(value,dict):return {key:encode(item) for key,item in value.items()}
    if isinstance(value,(list,tuple)):return [encode(item) for item in value]
    return value

def decode(value):
    if isinstance(value,dict):
        if set(value)=={'__worker_path__'}:return Path(value['__worker_path__'])
        if set(value)=={'__worker_set__'}:return {decode(item) for item in value['__worker_set__']}
        return {key:decode(item) for key,item in value.items()}
    if isinstance(value,list):return [decode(item) for item in value]
    return value

class ScriptExecutor:
    def __init__(self):self.local=ThreadPoolExecutor(max_workers=2)
    def submit(self,function,job_id,**kwargs):
        if os.environ.get('JOB_QUEUE','').lower()!='redis':
            return self.local.submit(function,job_id,**kwargs)
        from flask_app.services.background_job_service import get_background_job_service
        context=kwargs.pop('app_context_app',None)
        call={'function':function.__module__+':'+function.__name__,'kwargs':encode(kwargs),'with_app_context':context is not None}
        get_background_job_service().upsert_job(job_id,{'script_call':call})
        from flask_app.services.analysis_batch_service import attach_batch_child, batch_child_context
        attach_batch_child(job_id)
        from rq import get_current_job
        if get_current_job() is not None or batch_child_context.get() is not None:
            # A combined job executes its child in the same worker to avoid
            # waiting for a second worker that may not exist.
            return execute_script(job_id)
        return enqueue(execute_script,job_id,job_id)

def execute_script(job_id):
    from flask_app.app import app
    from flask_app.models.database import db,User
    from flask_app.services.background_job_service import get_background_job_service
    from flask_login import login_user
    from flask_app.routes.api_script_hub import _common
    with app.app_context():
        service=get_background_job_service()
        if not claim(job_id):return {'skipped':True}
        job=service.get_job(job_id)
        call=(job.get('payload') or {}).get('script_call') or {}
        module,name=call.get('function','').split(':',1)
        if not (module.startswith('flask_app.routes.api_script_hub.') or (module, name) in {('flask_app.routes.api_chord', '_run_chord_task'), ('flask_app.routes.api_treemap', '_run_treemap_task')}) or not name.startswith('_run_'):
            raise ValueError('Unsupported Script Hub worker')
        route_module=importlib.import_module(module)
        function=getattr(route_module,name)
        state_module = _common if module.startswith('flask_app.routes.api_script_hub.') else route_module
        prefix = 'script' if state_module is _common else ('chord' if module.endswith('api_chord') else 'treemap')
        task_lock = getattr(state_module, '_' + prefix + '_task_lock')
        tasks = getattr(state_module, '_' + prefix + '_tasks')
        kwargs=decode(call['kwargs'])
        if call.get('with_app_context'):kwargs['app_context_app']=app
        with task_lock:tasks[job_id]=job
        try:
            with app.test_request_context('/api/script-hub/worker'):
                if job.get('user_id'):
                    owner=db.session.get(User,job['user_id'])
                    if owner is None or not owner.is_active:raise ValueError('任务所属用户不存在或已停用')
                    login_user(owner)
                from flask import g
                g.analysis_project_id = job.get('project_id')
                from flask_app.services.analysis_artifacts import revalidate_job_upstream
                revalidate_job_upstream(job)
                from flask_app.services.input_preparation import revalidate_prepared_sources
                revalidate_prepared_sources(job)
                from flask_app.services.input_quality import validate_analysis_inputs
                validate_analysis_inputs((job.get('payload') or {}).get('input_assets', []))
                function(job_id,**kwargs)
        finally:
            with task_lock:tasks.pop(job_id,None)
        return service.get_job(job_id)

def execute_api(module,job_id):
    from flask_app.app import app
    from analysis_workers.main import get_worker
    with app.app_context():
        if not claim(job_id):return {'skipped':True}
        return get_worker(module)(job_id)


def reconcile_terminal_queue_job(job):
    """Recover a missed worker callback only from an explicit terminal RQ state."""
    from redis.exceptions import RedisError
    from rq.exceptions import NoSuchJobError
    from flask_app.models.database import AnalysisJob, db

    payload = job.payload or {}
    if job.status not in {'queued', 'running'} or payload.get('queue_backend') != 'redis' or not payload.get('rq_job_id'):
        return
    try:
        task = redis_queue().fetch_job(payload['rq_job_id'])
        if task is None or task.meta.get('analysis_job_id') != job.id:
            return
        state = task.get_status(refresh=True)
        state = getattr(state, 'value', state)
    except (RedisError, NoSuchJobError):
        # Unavailable Redis and expired records are not proof of a stopped task.
        return
    if state not in {'failed', 'stopped', 'canceled', 'finished'}:
        return
    detail = ('工作进程已结束，但未保存完整分析结果，请重新提交分析。' if state == 'finished'
              else '队列确认任务已终止，可能因工作进程退出或执行失败，请检查后重试。')
    changed = AnalysisJob.query.filter(AnalysisJob.id == job.id,
        AnalysisJob.status.in_(['queued', 'running'])).update({
            'status':'interrupted', 'stage':'分析中断', 'detail':detail,
            'completed_at':datetime.now(timezone.utc).replace(tzinfo=None),
        }, synchronize_session=False)
    db.session.commit()
    db.session.refresh(job)
    if changed:
        interrupt_child_jobs(job.id)
