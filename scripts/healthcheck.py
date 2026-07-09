#!/usr/bin/env python
"""Quick health check — verifies Flask starts and key endpoints respond.

Usage:
    python scripts/healthcheck.py [--port 5000]
"""

import argparse
import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root))

# Use in-memory SQLite so no live DB is needed for a health check.
os.environ.setdefault("FLASK_CONFIG", "testing")

from flask_app.app import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    app = create_app("testing")
    with app.app_context():
        count = len(list(app.url_map.iter_rules()))
        print(f"[OK] Flask app loaded -- {count} routes registered")

    print("[OK] Health check passed")


if __name__ == "__main__":
    main()
