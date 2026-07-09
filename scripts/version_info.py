#!/usr/bin/env python
"""Print version and configuration info for the current deployment.

Usage:
    python scripts/version_info.py
"""

import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root))

# Use in-memory SQLite for info gathering when no live DB is available.
os.environ.setdefault("FLASK_CONFIG", "testing")


def main():
    info = {
        "Python": sys.version.split()[0],
        "Working directory": str(_project_root),
        "JOB_QUEUE backend": os.environ.get("JOB_QUEUE", "threadpool (default)"),
        "STORAGE_BACKEND": os.environ.get("STORAGE_BACKEND", "local (default)"),
        "FLASK_CONFIG": os.environ.get("FLASK_CONFIG", "development (default)"),
    }

    # Try to get route count
    try:
        from flask_app.app import create_app
        app = create_app("testing")
        with app.app_context():
            info["Flask routes"] = str(len(list(app.url_map.iter_rules())))
    except Exception:
        info["Flask routes"] = "unavailable (DB not connected)"

    # Try FastAPI
    try:
        sys.path.insert(0, str(_project_root / "backend-api"))
        from app.main import app as fastapi_app
        routes = [r for r in fastapi_app.routes if hasattr(r, "path")]
        info["FastAPI routes"] = str(len(routes))
    except Exception:
        info["FastAPI routes"] = "unavailable"

    # Worker info
    try:
        from analysis_workers.main import MODULE_WORKERS
        info["Worker modules"] = str(len(MODULE_WORKERS))
    except Exception:
        info["Worker modules"] = "unavailable"

    print("Immune Repertoire Platform")
    print("=" * 40)
    for key, value in info.items():
        print(f"  {key:24s} {value}")


if __name__ == "__main__":
    main()
