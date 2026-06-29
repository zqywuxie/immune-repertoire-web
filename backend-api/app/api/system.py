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
    """Quick health check — returns 200 if the API is reachable."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
