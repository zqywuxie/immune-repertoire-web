"""Docker RQ worker; no application server is started here."""
import socket
import os

from rq import Worker
from flask_app.services.persistent_queue import redis_queue, record_killed


def worker_name():
    return f"analysis-{socket.gethostname()}"


if __name__ == "__main__":
    queue = redis_queue()
    Worker(
        [queue], connection=queue.connection, name=worker_name(),
        work_horse_killed_handler=record_killed,
        maintenance_interval=int(os.environ.get("ANALYSIS_QUEUE_MAINTENANCE_SECONDS", "60")),
    ).work()
