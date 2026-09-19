"""Real Redis: two concurrent consumers, pending third job, restart with stale registration."""
import os
import subprocess
import sys
import time
import uuid
import pytest
from redis import Redis
from rq import Queue, Worker
from flask_app.services.queue_status import queue_snapshot, annotate_waiting_jobs

def wait_for(check, seconds=15):
    deadline = time.monotonic() + seconds
    while not check():
        if time.monotonic() > deadline: raise AssertionError("worker 状态未在期限内变化")
        time.sleep(0.05)

@pytest.fixture
def queue():
    queue = Queue("capacity-" + uuid.uuid4().hex, connection=Redis.from_url(os.environ["REDIS_URL"]))
    yield queue
    for worker in Worker.all(queue=queue):
        worker.register_death(); queue.connection.delete(worker.key)
    queue.delete(delete_jobs=True)

def launch(queue, marker):
    code = """
import os
from pathlib import Path
from redis import Redis
from rq import Queue
from analysis_workers import worker_main
worker_main.redis_queue = lambda: Queue(os.environ['TEST_QUEUE'], connection=Redis.from_url(os.environ['REDIS_URL']))
worker_main.identity_file = lambda: Path(os.environ['TEST_MARKER'])
worker_main.main()
"""
    return subprocess.Popen([sys.executable, "-c", code], env={**os.environ,"TEST_QUEUE":queue.name,"TEST_MARKER":str(marker)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def stop(process):
    if process.poll() is None:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)

def test_two_jobs_run_while_third_waits(queue, tmp_path):
    processes = [launch(queue, tmp_path / str(slot)) for slot in range(2)]
    try:
        wait_for(lambda: queue_snapshot(queue)["online_workers"] == 2)
        jobs = [queue.enqueue("time.sleep", 4, job_timeout=20) for _ in range(3)]
        wait_for(lambda: sum(job.get_status(refresh=True) == "started" for job in jobs) == 2)
        assert sum(job.get_status(refresh=True) == "queued" for job in jobs) == 1
        assert queue_snapshot(queue)["busy_workers"] == 2
        wait_for(lambda: all(job.get_status(refresh=True) == "finished" for job in jobs), 20)
    finally:
        for process in processes: stop(process)

def test_restart_does_not_reuse_live_redis_registration(queue, tmp_path):
    marker = tmp_path / "worker-name"
    process = launch(queue, marker)
    replacement = None
    try:
        wait_for(lambda: marker.exists() and queue_snapshot(queue)["online_workers"] == 1)
        old_name = marker.read_text()
        process.kill(); process.wait(timeout=5)
        assert queue.connection.exists("rq:worker:" + old_name)
        replacement = launch(queue, marker)
        wait_for(lambda: marker.exists() and marker.read_text() != old_name)
        task = queue.enqueue("time.sleep", 0.1)
        wait_for(lambda: task.get_status(refresh=True) == "finished")
        assert replacement.poll() is None
    finally:
        stop(process)
        if replacement: stop(replacement)

def test_no_worker_is_reported_without_faking_running(queue, monkeypatch):
    from flask_app.services import queue_status
    monkeypatch.setattr(queue_status, "queue_snapshot", lambda: queue_snapshot(queue))
    job = {"status":"queued", "payload":{"queue_backend":"redis"}}
    annotate_waiting_jobs([job])
    assert job["status"] == "queued" and job["stage"] == "等待工作进程"
    from rq.suspension import suspend, resume
    suspend(queue.connection)
    try:
        annotate_waiting_jobs([job])
        assert job["stage"] == "队列已暂停"
    finally: resume(queue.connection)
