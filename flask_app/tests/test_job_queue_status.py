import json
import os
import uuid
import pytest
from redis import Redis
from redis.exceptions import ConnectionError
from rq import Queue, Worker
from rq.suspension import suspend, resume
from flask_app.tests.test_persistent_queue import application
from flask_app.services.background_job_service import get_background_job_service


def test_actual_redis_queue_no_worker_busy_idle_and_paused(application, monkeypatch):
    from flask_app.services import persistent_queue
    connection = Redis.from_url(os.environ['REDIS_URL'])
    queue = Queue('codex-queue-status-' + uuid.uuid4().hex, connection=connection)
    monkeypatch.setattr(persistent_queue, 'redis_queue', lambda: queue)
    service = get_background_job_service()
    record = service.create_job(job_type='api_request', module='profile')
    ahead = queue.enqueue('builtins.len', [], job_id='private-' + uuid.uuid4().hex)
    task = queue.enqueue('builtins.len', [], job_id='own-' + uuid.uuid4().hex)
    service.upsert_job(record['job_id'], {'queue_backend':'redis','rq_job_id':task.id})
    worker = Worker([queue], connection=connection, name='codex-status-worker-' + uuid.uuid4().hex)
    try:
        before = service.get_job(record['job_id'])['queue_status']
        assert before['state'] == 'no_workers'
        assert before['online_workers'] == 0 and before['position'] == 2
        worker.register_birth(); worker.set_state('busy')
        busy = service.get_job(record['job_id'])['queue_status']
        assert busy['state'] == 'busy' and busy['busy_workers'] == busy['online_workers'] == 1
        assert ahead.id not in json.dumps(busy) and worker.name not in json.dumps(busy)
        worker.set_state('idle')
        assert service.get_job(record['job_id'])['queue_status']['state'] == 'waiting'
        suspend(connection)
        assert service.get_job(record['job_id'])['queue_status']['state'] == 'paused'
        resume(connection)
        assert service.get_job(record['job_id'])['status'] == 'queued'
    finally:
        resume(connection); worker.register_death()
        task.delete(); ahead.delete(); queue.delete()


def test_queue_read_failure_is_unknown_and_missing_registration_is_distinct(application, monkeypatch):
    from flask_app.services import persistent_queue
    service = get_background_job_service()
    record = service.create_job(job_type='api_request', module='profile')
    service.upsert_job(record['job_id'], {'queue_backend':'redis','rq_job_id':'absent-' + uuid.uuid4().hex})
    connection = Redis.from_url(os.environ['REDIS_URL'])
    queue = Queue('codex-missing-' + uuid.uuid4().hex, connection=connection)
    monkeypatch.setattr(persistent_queue, 'redis_queue', lambda: queue)
    assert service.get_job(record['job_id'])['queue_status']['state'] == 'missing'
    def unavailable():
        raise ConnectionError('synthetic Redis interruption')
    monkeypatch.setattr(persistent_queue, 'redis_queue', unavailable)
    response = application.test_client().get('/api/jobs/' + record['job_id'])
    assert response.status_code == 200
    assert response.json['job']['queue_status']['state'] == 'unavailable'
    assert 'online_workers' not in response.json['job']['queue_status']
    assert 'synthetic' not in response.json['job']['queue_status']['message']


def test_queue_facts_preserve_existing_job_owner_boundary(application):
    from flask_app.models.database import db, User
    from flask import g
    application.config['REQUIRE_LOGIN'] = True
    owner = User(username='queue-owner',email='owner@test.invalid',password_hash='unused')
    other = User(username='queue-other',email='other@test.invalid',password_hash='unused')
    db.session.add_all([owner,other]); db.session.commit()
    record = get_background_job_service().create_job(job_type='api_request',module='profile',user_id=owner.id)
    client = application.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(other.id); session['_fresh'] = True
    assert client.get('/api/jobs/' + record['job_id']).status_code == 404
    g.pop('_login_user', None)
    with client.session_transaction() as session:
        session['_user_id'] = str(owner.id); session['_fresh'] = True
    assert client.get('/api/jobs/' + record['job_id']).status_code == 200


def test_finished_and_cancelled_tasks_do_not_read_queue(application, monkeypatch):
    from flask_app.services import persistent_queue
    from flask_app.services.queue_status import annotate_waiting_jobs
    monkeypatch.setattr(persistent_queue,'redis_queue',lambda:pytest.fail('should not read Redis'))
    records=[{'status':status,'payload':{'queue_backend':'redis','rq_job_id':'old'}} for status in ['completed','cancelled']]
    assert annotate_waiting_jobs(records) == records
    assert all('queue_status' not in record for record in records)
