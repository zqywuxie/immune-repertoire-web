"""Real Redis registration and Linux worker process health checks."""
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from redis import Redis
from rq import Queue, Worker
from rq.utils import utcformat
from analysis_workers.healthcheck import check_worker
from analysis_workers.worker_main import worker_name


@pytest.fixture
def queue():
    connection = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue("health-regression-" + uuid.uuid4().hex, connection=connection)
    yield queue
    connection.delete("rq:worker:" + worker_name())
    connection.srem(Worker.redis_workers_keys, "rq:worker:" + worker_name())
    queue.delete(delete_jobs=True)


def test_other_worker_cannot_mask_missing_current_worker(queue):
    other = Worker([queue], name="other-" + uuid.uuid4().hex, connection=queue.connection)
    other.register_birth()
    try:
        with pytest.raises(RuntimeError, match="尚未注册"):
            check_worker(queue)
    finally:
        other.register_death()
        queue.connection.delete(other.key)


def test_real_worker_start_heartbeat_expiry_and_stop(queue):
    code = """
import os
from redis import Redis
from rq import Queue, Worker
from analysis_workers.worker_main import worker_name
c=Redis.from_url(os.environ['REDIS_URL'])
q=Queue(os.environ['HEALTH_TEST_QUEUE'],connection=c)
Worker([q],connection=c,name=worker_name()).work(with_scheduler=False)
"""
    process = subprocess.Popen([sys.executable, "-c", code], env={**os.environ, "HEALTH_TEST_QUEUE": queue.name})
    key = "rq:worker:" + worker_name()
    try:
        deadline = time.monotonic() + 10
        while True:
            assert process.poll() is None, "工作进程意外退出"
            try:
                check_worker(queue)
                break
            except RuntimeError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        queue.connection.hset(key, "last_heartbeat", utcformat(datetime.now(timezone.utc) - timedelta(hours=1)))
        with pytest.raises(RuntimeError, match="心跳已过期"):
            check_worker(queue)
        queue.connection.hset(key, "last_heartbeat", utcformat(datetime.now(timezone.utc)))
        check_worker(queue)
        process.terminate()
        process.wait(timeout=10)
        with pytest.raises((RuntimeError, ProcessLookupError)):
            check_worker(queue)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
