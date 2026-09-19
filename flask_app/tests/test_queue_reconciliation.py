import os
import uuid
from redis import Redis
from rq import Queue
from rq.job import Job, JobStatus
from flask_app.tests.test_persistent_queue import application


def test_real_redis_terminal_record_recovers_missing_callback(application, monkeypatch):
    from flask_app.services import persistent_queue
    from flask_app.services.background_job_service import get_background_job_service
    connection = Redis.from_url(os.environ['REDIS_URL'])
    queue = Queue('recovery-' + uuid.uuid4().hex, connection=connection)
    monkeypatch.setattr(persistent_queue, 'redis_queue', lambda:queue)
    service = get_background_job_service()
    parent = service.create_job(job_type='api_request', module='statistical.analyze')
    task = Job.create('builtins.len', args=([],), connection=connection, origin=queue.name,
        id='recovery-' + uuid.uuid4().hex, meta={'analysis_job_id':parent['job_id']})
    try:
        task.save()
        task.set_status(JobStatus.STARTED)
        service.upsert_job(parent['job_id'], {'status':'running', 'queue_backend':'redis', 'rq_job_id':task.id})
        assert service.get_job(parent['job_id'])['status'] == 'running'
        task.set_status(JobStatus.FAILED)
        recovered = service.get_job(parent['job_id'])
        assert recovered['status'] == 'interrupted'
        assert recovered['completed_at']
        assert service.get_job(parent['job_id'])['completed_at'] == recovered['completed_at']
    finally:
        task.delete()


def test_killed_worker_is_recovered_after_real_heartbeat_expiry(application, monkeypatch):
    import multiprocessing
    import signal
    import time
    from rq import Worker
    from flask_app.services import persistent_queue
    from flask_app.services.background_job_service import get_background_job_service
    connection = Redis.from_url(os.environ['REDIS_URL'])
    queue = Queue('worker-death-' + uuid.uuid4().hex, connection=connection)
    monkeypatch.setattr(persistent_queue, 'redis_queue', lambda:queue)
    service = get_background_job_service()
    parent = service.create_job(job_type='api_request', module='statistical.analyze')
    child = service.create_job(job_type='chord', module='chord', extra={'parent_job_id':parent['job_id']})
    task = queue.enqueue('time.sleep', 180, job_timeout=240, meta={'analysis_job_id':parent['job_id']})
    service.upsert_job(parent['job_id'], {'status':'running','queue_backend':'redis','rq_job_id':task.id})
    worker_name = 'kill-test-' + uuid.uuid4().hex
    def run_worker():
        os.setsid()
        Worker([queue], connection=connection, name=worker_name, job_monitoring_interval=1).work(burst=True, logging_level='WARNING')
    process = multiprocessing.get_context('fork').Process(target=run_worker)
    process.start()
    try:
        deadline = time.monotonic() + 20
        while task.get_status(refresh=True) != JobStatus.STARTED:
            assert time.monotonic() < deadline, 'worker did not start'
            time.sleep(0.1)
        # Kill the worker and its computation together, so neither can run a callback.
        os.killpg(process.pid, signal.SIGKILL)
        process.join(5)
        assert not process.is_alive()
        assert service.get_job(parent['job_id'])['status'] == 'running'
        registry = queue.started_job_registry
        deadline = time.monotonic() + 95
        while not registry.get_expired_job_ids():
            assert time.monotonic() < deadline, 'heartbeat did not expire'
            time.sleep(0.5)
        replacement = Worker([queue], connection=connection, name='replacement-' + uuid.uuid4().hex)
        replacement.clean_registries()
        assert task.get_status(refresh=True) == JobStatus.FAILED
        assert service.get_job(parent['job_id'])['status'] == 'interrupted'
        assert service.get_job(child['job_id'])['status'] == 'interrupted'
    finally:
        if process.is_alive():
            os.killpg(process.pid, signal.SIGKILL)
            process.join(5)
        registry = queue.started_job_registry
        registry.remove(task.id)
        queue.failed_job_registry.remove(task.id)
        task.delete()
        connection.delete('rq:worker:' + worker_name)
        connection.srem('rq:workers', 'rq:worker:' + worker_name)
        connection.srem('rq:workers:' + queue.name, 'rq:worker:' + worker_name)
        queue.delete()
