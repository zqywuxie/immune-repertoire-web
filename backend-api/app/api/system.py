"""System routes — health, info, and configuration."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["System"])


@router.get("/info")
async def app_info():
    """Get application metadata."""
    return {
        "name": "Immune Repertoire Platform API",
        "version": "0.2.0",
        "backend": "FastAPI",
        "python_version": os.sys.version.split()[0] if hasattr(os, "sys") else "3.x",
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
async def health_check():
    """Full health check — API, DB, Redis, and storage backend status."""
    import time
    from sqlalchemy import text

    result: dict = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {},
    }

    # ── Database ──────────────────────────────────────────────────────
    try:
        from ..core.database import SessionLocal

        t0 = time.monotonic()
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        db_ms = round((time.monotonic() - t0) * 1000)
        result["checks"]["database"] = {"status": "ok", "latency_ms": db_ms}
    except Exception as exc:
        result["checks"]["database"] = {"status": "error", "detail": str(exc)}
        result["status"] = "degraded"

    # ── Redis ─────────────────────────────────────────────────────────
    try:
        import redis

        redis_host = os.environ.get("REDIS_HOST", "127.0.0.1")
        redis_port = int(os.environ.get("REDIS_PORT", "6379"))
        t0 = time.monotonic()
        r = redis.Redis(host=redis_host, port=redis_port, socket_connect_timeout=2)
        r.ping()
        r.close()
        redis_ms = round((time.monotonic() - t0) * 1000)
        result["checks"]["redis"] = {"status": "ok", "latency_ms": redis_ms}
    except Exception as exc:
        result["checks"]["redis"] = {"status": "error", "detail": str(exc)}
        # Redis is optional during development
        if result["status"] == "ok":
            result["status"] = "degraded"

    # ── Storage backend ───────────────────────────────────────────────
    storage_status = _check_storage()
    result["checks"]["storage"] = storage_status
    if storage_status["status"] == "error" and result["status"] == "ok":
        # Local storage is always available; MinIO failure is advisory
        pass

    return result


def _check_storage() -> dict:
    """Probe the configured storage backend.

    Returns a dict with ``status``, ``backend``, and optional ``detail``.
    """
    import time

    storage_type = os.environ.get("STORAGE_BACKEND", "local").lower()

    if storage_type == "s3":
        try:
            t0 = time.monotonic()
            import boto3

            s3 = boto3.client(
                "s3",
                endpoint_url=os.environ.get("S3_ENDPOINT_URL", "http://minio:9000"),
                aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
                aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
                region_name=os.environ.get("S3_REGION", "us-east-1"),
            )
            bucket = os.environ.get("S3_BUCKET", "immune-repertoire")
            s3.head_bucket(Bucket=bucket)
            s3_ms = round((time.monotonic() - t0) * 1000)
            return {
                "status": "ok",
                "backend": "s3",
                "bucket": bucket,
                "latency_ms": s3_ms,
            }
        except Exception as exc:
            return {
                "status": "error",
                "backend": "s3",
                "detail": str(exc),
            }

    # Local filesystem — always "ok" as long as we can stat the root
    try:
        t0 = time.monotonic()
        storage_root = os.environ.get("STORAGE_ROOT", "flask_app/data/projects")
        import os as _os

        if not _os.path.exists(storage_root):
            _os.makedirs(storage_root, exist_ok=True)
        fs_ms = round((time.monotonic() - t0) * 1000)
        return {
            "status": "ok",
            "backend": "local",
            "root": storage_root,
            "latency_ms": fs_ms,
        }
    except Exception as exc:
        return {
            "status": "error",
            "backend": "local",
            "detail": str(exc),
        }
