"""Check this container's RQ worker, including its process and heartbeat."""
import os
from datetime import datetime, timezone

from rq import Worker
from analysis_workers.worker_main import worker_name
from flask_app.services.persistent_queue import redis_queue


def check_worker(queue=None):
    queue = queue if queue is not None else redis_queue()
    worker = Worker.find_by_key(f"rq:worker:{worker_name()}", connection=queue.connection)
    if worker is None:
        raise RuntimeError("当前工作进程尚未注册")
    if queue.name not in worker.queue_names():
        raise RuntimeError("当前工作进程未监听分析队列")
    if worker.get_state() not in {"idle", "busy", "started"}:
        raise RuntimeError("当前工作进程未处于可工作状态")
    heartbeat = worker.last_heartbeat
    if heartbeat is None:
        raise RuntimeError("当前工作进程缺少心跳")
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    # Idle workers block on Redis; allow their configured TTL plus RQ's grace period.
    if age > worker.worker_ttl + 60:
        raise RuntimeError("当前工作进程心跳已过期")
    if not worker.pid or worker.pid <= 0:
        raise RuntimeError("当前工作进程编号无效")
    os.kill(worker.pid, 0)


if __name__ == "__main__":
    check_worker()
