"""Small idempotent schema repairs for databases created before migrations.

These checks intentionally cover only additive changes that old local
databases need before the current ORM models can query them.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from flask_app.models.database import db

LOGGER = logging.getLogger(__name__)


OWNED_TABLES = (
    "projects",
    "files",
    "analyses",
    "analysis_jobs",
    "mapping_templates",
    "custom_parameters",
)


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(inspector, table_name: str) -> set[str]:
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _quote_identifier(name: str) -> str:
    return "`" + name.replace("`", "``") + "`"


def _add_column(conn, dialect: str, table_name: str, column_name: str, column_type: str) -> None:
    table = _quote_identifier(table_name) if dialect == "mysql" else table_name
    column = _quote_identifier(column_name) if dialect == "mysql" else column_name
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))


def _create_index(conn, dialect: str, table_name: str, index_name: str, column_names: tuple[str, ...], *, unique: bool = False) -> None:
    table = _quote_identifier(table_name) if dialect == "mysql" else table_name
    index = _quote_identifier(index_name) if dialect == "mysql" else index_name
    columns = ", ".join(_quote_identifier(column) if dialect == "mysql" else column for column in column_names)
    unique_sql = "UNIQUE " if unique else ""
    conn.execute(text(f"CREATE {unique_sql}INDEX {index} ON {table} ({columns})"))


def _ensure_index(conn, inspector, dialect: str, table_name: str, index_name: str, column_names: tuple[str, ...], *, unique: bool = False) -> None:
    indexes = _index_names(inspector, table_name)
    if index_name in indexes:
        return
    try:
        _create_index(conn, dialect, table_name, index_name, column_names, unique=unique)
    except Exception:
        LOGGER.warning("Failed to create index %s on %s", index_name, table_name, exc_info=True)


def _ensure_project_asset_indexes(conn, inspector, dialect: str, table_names: set[str]) -> None:
    if "project_assets" not in table_names:
        return
    _ensure_index(
        conn,
        inspector,
        dialect,
        "project_assets",
        "ix_project_assets_project_uploaded",
        ("project_id", "uploaded_at"),
    )
    inspector = inspect(db.engine)
    _ensure_index(
        conn,
        inspector,
        dialect,
        "project_assets",
        "ix_project_assets_project_type_uploaded",
        ("project_id", "asset_type", "uploaded_at"),
    )


def _copy_legacy_user_values(conn, inspector, dialect: str) -> None:
    if "users" not in inspector.get_table_names():
        return

    columns = _column_names(inspector, "users")
    table = _quote_identifier("users") if dialect == "mysql" else "users"
    if {"is_active", "is_active_flag"}.issubset(columns):
        conn.execute(text(f"UPDATE {table} SET is_active_flag = CASE WHEN is_active THEN 1 ELSE 0 END"))
    if {"last_login", "last_login_at"}.issubset(columns):
        conn.execute(text(f"UPDATE {table} SET last_login_at = last_login WHERE last_login_at IS NULL AND last_login IS NOT NULL"))


def ensure_schema_compatibility() -> None:
    """Add missing columns required by the current models.

    Flask-SQLAlchemy's ``create_all`` creates absent tables, but it does not
    migrate existing tables. Older development databases therefore need a
    narrow compatibility pass before normal requests query the models.
    """
    engine = db.engine
    dialect = engine.dialect.name
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    with engine.begin() as conn:
        if "users" in table_names:
            columns = _column_names(inspector, "users")
            user_columns = {
                "role": "VARCHAR(30) NULL DEFAULT 'user'",
                "is_active_flag": "BOOLEAN NULL DEFAULT 1",
                "home_path": "VARCHAR(500) NULL",
                "allowed_paths": "JSON NULL" if dialect == "mysql" else "JSON",
                "last_login_at": "DATETIME NULL",
            }
            for column_name, column_type in user_columns.items():
                if column_name not in columns:
                    _add_column(conn, dialect, "users", column_name, column_type)

        for table_name in OWNED_TABLES:
            if table_name not in table_names:
                continue
            columns = _column_names(inspector, table_name)
            if "user_id" not in columns:
                _add_column(conn, dialect, table_name, "user_id", "INTEGER NULL")

        inspector = inspect(engine)
        if "projects" in table_names and "user_id" in _column_names(inspector, "projects"):
            _ensure_index(conn, inspector, dialect, "projects", "ix_projects_user_id", ("user_id",))
            inspector = inspect(engine)
            _ensure_index(conn, inspector, dialect, "projects", "ix_projects_user_name", ("user_id", "name"), unique=True)

        inspector = inspect(engine)
        _ensure_project_asset_indexes(conn, inspector, dialect, table_names)

        inspector = inspect(engine)
        _copy_legacy_user_values(conn, inspector, dialect)
