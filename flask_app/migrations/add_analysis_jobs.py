"""Add persistent global analysis_jobs table.

Usage:
  python migrations/add_analysis_jobs.py --dry-run
  python migrations/add_analysis_jobs.py --apply
  python migrations/add_analysis_jobs.py --verify
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from flask import Flask
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except Exception:
    pass

from flask_app.config import config
from flask_app.models.database import AnalysisJob, db  # noqa: F401


UPDATED_AT_INDEX = "idx_analysis_jobs_updated_at"


def create_db_app() -> Flask:
    config_name = os.environ.get("FLASK_CONFIG", "development")
    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config["development"]))
    db.init_app(app)
    return app


def migrate(args) -> None:
    app = create_db_app()
    with app.app_context():
        inspector = inspect(db.engine)
        exists = "analysis_jobs" in inspector.get_table_names()
        print(f"Database dialect: {db.engine.dialect.name}")
        print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY' if args.apply else 'VERIFY'}")

        if args.verify:
            if not exists:
                raise SystemExit("Missing table: analysis_jobs")
            columns = {column["name"] for column in inspector.get_columns("analysis_jobs")}
            required = {"id", "job_type", "module", "status", "progress", "payload", "result", "user_id", "project_id"}
            missing = sorted(required - columns)
            if missing:
                raise SystemExit(f"Missing columns: {', '.join(missing)}")
            index_columns = {
                tuple(index.get("column_names") or [])
                for index in inspector.get_indexes("analysis_jobs")
            }
            if ("updated_at",) not in index_columns:
                raise SystemExit(f"Missing index on analysis_jobs.updated_at; run {Path(__file__).name} --apply")
            print("Verification passed.")
            return

        if exists:
            index_columns = {
                tuple(index.get("column_names") or [])
                for index in inspector.get_indexes("analysis_jobs")
            }
            if ("updated_at",) in index_columns:
                print("[skip] analysis_jobs table already exists")
                return
            print(f"[create-index] {UPDATED_AT_INDEX} on analysis_jobs(updated_at)")
            if not args.dry_run:
                with db.engine.begin() as conn:
                    conn.execute(text(f"CREATE INDEX {UPDATED_AT_INDEX} ON analysis_jobs (updated_at)"))
                print("Created updated_at index.")
            return

        print("[create] analysis_jobs table")
        if not args.dry_run:
            db.create_all()
            print("Created analysis_jobs table.")


def parse_args():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    migrate(parse_args())
