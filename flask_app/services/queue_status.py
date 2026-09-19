"""Read queue capacity without inferring running state from an old database row."""
from datetime import datetime, timezone
import os

def queue_snapshot(queue=None):
    from flask_app.services.persistent_queue import redis_queue
    from rq import Worker
    from rq.suspension import is_suspended
    queue = queue if queue is not None else redis_queue()
    now = datetime.now(timezone.utc)
    workers = []
    for worker in Worker.all(queue=queue):
        heartbeat = worker.last_heartbeat
        if heartbeat is None: continue
        if heartbeat.tzinfo is None: heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        if (now - heartbeat).total_seconds() > worker.worker_ttl + 60: continue
        state = worker.get_state()
        if state in {"idle", "busy", "started"}: workers.append(state)
    return {"online_workers":len(workers), "busy_workers":workers.count("busy"),
            "configured_concurrency":int(os.environ.get("WORKER_CONCURRENCY", "2")),
            "paused":is_suspended(queue.connection), "queued_count":queue.count}

def annotate_waiting_jobs(jobs):
    waiting = [job for job in jobs if job.get("status") == "queued" and (job.get("payload") or {}).get("queue_backend") == "redis"]
    if not waiting: return jobs
    try:
        snapshot = queue_snapshot()
        if snapshot["paused"]:
            stage, detail = "队列已暂停", "分析队列已暂停，请管理员恢复队列后继续。"
        elif not snapshot["online_workers"]:
            stage, detail = "等待工作进程", "任务已入队，但当前没有可用工作进程；请检查 worker 容器及其日志。"
        elif snapshot["busy_workers"] >= snapshot["online_workers"]:
            stage, detail = "等待执行名额", f"当前 {snapshot['busy_workers']} 个工作进程正在处理任务，空闲后自动执行。"
        else:
            stage, detail = "等待领取任务", "已有空闲工作进程，正在等待领取；若持续停留，请检查 worker 日志和队列连接。"
    except Exception:
        snapshot = {"available":False}
        stage, detail = "队列连接异常", "暂时无法读取队列状态，请检查 Redis 和 worker 连接。"
    for job in waiting:
        job.update(stage=stage, detail=detail, queue_status=snapshot)
    return jobs
