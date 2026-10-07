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
            "paused":is_suspended(queue.connection), "queued_count":queue.count,
            "checked_at":now.isoformat(), "available":True}


def annotate_waiting_jobs(jobs):
    waiting = [job for job in jobs if job.get("status") == "queued" and (job.get("payload") or {}).get("queue_backend") == "redis"]
    if not waiting: return jobs
    try:
        from flask_app.services.persistent_queue import redis_queue
        queue = redis_queue()
        snapshot = queue_snapshot(queue)
        if snapshot["paused"]:
            state, stage, detail = "paused", "队列已暂停", "分析队列已暂停，请管理员恢复队列后继续。"
        elif not snapshot["online_workers"]:
            state, stage, detail = "no_workers", "等待工作进程", "任务已入队，但当前没有可用工作进程；请联系管理员检查工作进程。"
        elif snapshot["busy_workers"] >= snapshot["online_workers"]:
            state, stage, detail = "busy", "等待执行名额", f"当前 {snapshot['busy_workers']} 个工作进程正在处理任务，空闲后自动执行。"
        else:
            state, stage, detail = "waiting", "等待领取任务", "已有空闲工作进程，正在等待领取；若持续停留，请联系管理员核对工作进程和队列连接。"
    except Exception:
        snapshot = {"available":False, "checked_at":datetime.now(timezone.utc).isoformat()}
        state, stage, detail = "unavailable", "队列连接异常", "暂时无法读取队列状态，可重新读取任务；持续失败时请联系管理员检查队列连接。"
    for job in waiting:
        facts = {**snapshot, 'state':state, 'position':None}
        job_stage, job_detail = stage, detail
        if snapshot.get('available'):
            try:
                task_id = (job.get('payload') or {}).get('rq_job_id')
                position = queue.get_job_position(task_id) if task_id else None
                facts['position'] = position + 1 if position is not None else None
                if position is None and task_id and queue.fetch_job(task_id) is None:
                    facts['state'] = 'missing'
                    job_stage, job_detail = '队列登记待核对', '任务记录仍在，但未找到对应队列登记。请联系管理员核对队列与任务，不要重复提交。'
            except Exception:
                facts['position_available'] = False
        facts['message'] = job_detail
        job.update(stage=job_stage, detail=job_detail, queue_status=facts)
    return jobs
