"""One RQ worker per container; Compose controls the concurrency limit."""
import socket
import os
import uuid
from pathlib import Path
from rq import Worker
from flask_app.services.persistent_queue import redis_queue, record_killed

def identity_file():
    # /tmp is private to each container, unlike the shared analysis temp volume.
    return Path("/tmp") / ("immune-worker-" + socket.gethostname() + ".name")

def worker_name():
    try:
        return identity_file().read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return f"analysis-{socket.gethostname()}"

def main():
    queue = redis_queue()
    # A killed worker can leave its Redis name alive until TTL expiry. Never
    # reuse that name on restart or RQ refuses to start consuming the queue.
    name = f"analysis-{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
    marker = identity_file()
    marker.write_text(name, encoding="utf-8")
    try:
        Worker([queue], connection=queue.connection, name=name,
               work_horse_killed_handler=record_killed,
               maintenance_interval=int(os.environ.get("ANALYSIS_QUEUE_MAINTENANCE_SECONDS", "60"))).work()
    finally:
        marker.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
