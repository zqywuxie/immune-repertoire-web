"""Coordinate Linux deployment admission with in-flight HTTP writes."""
import argparse
import fcntl
from pathlib import Path

DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "data"

def open_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return (directory / ".deployment.lock").open("a+")

def set_maintenance(directory, token, enabled):
    marker = Path(directory) / ".deployment-maintenance"
    with open_lock(directory) as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        current = marker.read_text() if marker.exists() else None
        if current is not None and current != token:
            raise RuntimeError("已有其他维护操作，不能覆盖或解除其维护状态。")
        if enabled:
            marker.write_text(token)
        elif current is not None:
            marker.unlink()

def register_maintenance(app):
    from flask import g, jsonify, request
    @app.before_request
    def guard_writes():
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return None
        # Already-admitted batches dispatch child requests inside the worker.
        # This server-only ContextVar cannot be supplied in an HTTP request.
        from flask_app.services.analysis_batch_service import batch_child_context
        if batch_child_context.get() is not None:
            return None
        if app.testing and not app.config.get("MAINTENANCE_DIRECTORY"):
            return None
        directory = Path(app.config.get("MAINTENANCE_DIRECTORY") or DEFAULT_DIRECTORY)
        lock = open_lock(directory)
        fcntl.flock(lock, fcntl.LOCK_SH)
        g.deployment_lock = lock
        if (directory / ".deployment-maintenance").exists():
            return jsonify(success=False, error="DEPLOYMENT_MAINTENANCE", message="平台正在更新，暂时不能提交或修改数据；已有任务继续执行，请稍后重试。"), 503, {"Retry-After":"30"}

    @app.teardown_request
    def release_write_lock(error=None):
        lock = g.pop("deployment_lock", None)
        if lock is not None:
            lock.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="开启或解除部署维护状态")
    parser.add_argument("action", choices=["enable", "disable"])
    parser.add_argument("--token", required=True)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    set_maintenance(args.directory, args.token, args.action == "enable")
    print("维护状态已开启；维护令牌：" + args.token if args.action == "enable" else "维护状态已解除")
