"""
Add authentication and user ownership columns.

Usage:
  python migrations/add_auth_user_scope.py --dry-run
  python migrations/add_auth_user_scope.py --apply --admin-username admin --admin-email admin@example.com
  python migrations/add_auth_user_scope.py --verify
"""

from __future__ import annotations

import argparse
import os
import secrets
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
from flask_app.models.database import User, db


OWNED_TABLES = {
    "projects": "user_id",
    "files": "user_id",
    "analyses": "user_id",
    "mapping_templates": "user_id",
    "custom_parameters": "user_id",
}


def create_db_app() -> Flask:
    """Create a minimal app for DB migration without importing analysis blueprints."""
    config_name = os.environ.get("FLASK_CONFIG", "development")
    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config["development"]))
    db.init_app(app)
    return app


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _add_user_id_column(engine, table_name: str, dry_run: bool) -> None:
    inspector = inspect(engine)
    if _column_exists(inspector, table_name, "user_id"):
        print(f"[skip] {table_name}.user_id already exists")
        return
    dialect = engine.dialect.name
    ddl = f"ALTER TABLE {table_name} ADD COLUMN user_id INTEGER NULL"
    print(f"[ddl] {ddl}")
    if dry_run:
        return
    with engine.begin() as conn:
        conn.execute(text(ddl))
        if dialect == "mysql":
            try:
                conn.execute(text(f"CREATE INDEX ix_{table_name}_user_id ON {table_name} (user_id)"))
            except Exception:
                pass


def _ensure_project_indexes(engine, dry_run: bool) -> None:
    inspector = inspect(engine)
    if "projects" not in inspector.get_table_names():
        return
    if not _index_exists(inspector, "projects", "ix_projects_user_name"):
        ddl = "CREATE UNIQUE INDEX ix_projects_user_name ON projects (user_id, name)"
        print(f"[ddl] {ddl}")
        if not dry_run:
            try:
                with engine.begin() as conn:
                    conn.execute(text(ddl))
            except Exception as exc:
                print(f"[warn] failed to create ix_projects_user_name: {exc}")
    if engine.dialect.name == "mysql":
        with engine.begin() as conn:
            for index_name in ("name", "ix_projects_name"):
                try:
                    print(f"[ddl] ALTER TABLE projects DROP INDEX {index_name}")
                    if not dry_run:
                        conn.execute(text(f"ALTER TABLE projects DROP INDEX {index_name}"))
                except Exception:
                    pass


def _ensure_admin(username: str, email: str, dry_run: bool) -> tuple[int | None, str | None]:
    inspector = inspect(db.engine)
    if "users" not in inspector.get_table_names():
        password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(14)
        print(f"[create] users table and admin user {username} <{email}>")
        return None, password

    user = User.query.filter((User.username == username) | (User.email == email)).first()
    if user:
        if user.role != "admin":
            print(f"[update] promote {user.username} to admin")
            if not dry_run:
                user.role = "admin"
                db.session.commit()
        return user.id, None

    password = os.environ.get("ADMIN_PASSWORD") or secrets.token_urlsafe(14)
    print(f"[create] admin user {username} <{email}>")
    if dry_run:
        return None, password

    home_root = Path(os.environ.get("USER_DATA_ROOT", ROOT / "data" / "users"))
    home_path = home_root / username
    home_path.mkdir(parents=True, exist_ok=True)
    user = User(username=username, email=email, role="admin", home_path=str(home_path), allowed_paths=[])
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user.id, password


def _assign_legacy_rows(engine, admin_id: int, dry_run: bool) -> None:
    for table_name in OWNED_TABLES:
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names() or not _column_exists(inspector, table_name, "user_id"):
            continue
        sql = f"UPDATE {table_name} SET user_id = :admin_id WHERE user_id IS NULL"
        print(f"[data] {sql}")
        if not dry_run:
            with engine.begin() as conn:
                conn.execute(text(sql), {"admin_id": admin_id})


def migrate(args) -> None:
    app = create_db_app()
    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)
        print(f"Database dialect: {engine.dialect.name}")
        print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY' if args.apply else 'VERIFY'}")

        if args.verify:
            missing = []
            inspector = inspect(engine)
            for table_name in OWNED_TABLES:
                if table_name in inspector.get_table_names() and not _column_exists(inspector, table_name, "user_id"):
                    missing.append(f"{table_name}.user_id")
            admin_count = User.query.filter(User.role == "admin").count() if "users" in inspector.get_table_names() else 0
            print(f"Admin users: {admin_count}")
            if missing:
                raise SystemExit(f"Missing columns: {', '.join(missing)}")
            print("Verification passed.")
            return

        dry_run = args.dry_run
        if not dry_run:
            db.create_all()

        for table_name in OWNED_TABLES:
            if table_name in inspector.get_table_names():
                _add_user_id_column(engine, table_name, dry_run)

        if not dry_run:
            db.create_all()

        admin_id, password = _ensure_admin(args.admin_username, args.admin_email, dry_run)
        if admin_id:
            _assign_legacy_rows(engine, admin_id, dry_run)
        _ensure_project_indexes(engine, dry_run)

        if password:
            print("")
            print("Initial admin password:")
            print(password)
            print("Set ADMIN_PASSWORD before running --apply if you want a fixed password.")


def parse_args():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--verify", action="store_true")
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME", "admin"))
    parser.add_argument("--admin-email", default=os.environ.get("ADMIN_EMAIL", "admin@example.com"))
    return parser.parse_args()


if __name__ == "__main__":
    migrate(parse_args())
