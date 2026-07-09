"""Tests for additive schema compatibility repairs."""

from datetime import datetime, timedelta

from flask import Flask
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query
from sqlalchemy import inspect, text

from flask_app.models.database import Project, ProjectAsset, User, db
from flask_app.services.project_asset_service import get_project_asset_service
from flask_app.services.schema_compatibility import ensure_schema_compatibility


def test_schema_compatibility_repairs_legacy_project_asset_schema():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username VARCHAR(80) NOT NULL,
                    email VARCHAR(120),
                    password_hash VARCHAR(255),
                    is_active BOOLEAN,
                    created_at DATETIME NOT NULL,
                    last_login DATETIME
                )
            """))
            conn.execute(text("""
                CREATE TABLE projects (
                    id VARCHAR(36) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    institution VARCHAR(255),
                    cooperation_level VARCHAR(120),
                    description TEXT,
                    status VARCHAR(50) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE project_assets (
                    id VARCHAR(36) PRIMARY KEY,
                    project_id VARCHAR(36) NOT NULL,
                    asset_type VARCHAR(50) NOT NULL,
                    original_name VARCHAR(255) NOT NULL,
                    storage_path VARCHAR(500) NOT NULL,
                    mime_type VARCHAR(120),
                    size INTEGER NOT NULL,
                    metadata_json JSON,
                    uploaded_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE analysis_jobs (
                    id VARCHAR(64) PRIMARY KEY,
                    job_type VARCHAR(80) NOT NULL,
                    module VARCHAR(120) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    progress FLOAT NOT NULL,
                    payload JSON,
                    result JSON,
                    project_id VARCHAR(36),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
            """))
            conn.execute(text("""
                INSERT INTO users (username, email, password_hash, is_active, created_at, last_login)
                VALUES ('legacy', 'legacy@example.com', 'hash', 0, '2026-01-01 00:00:00', '2026-01-02 00:00:00')
            """))
            conn.execute(text("""
                INSERT INTO projects (id, name, status, created_at, updated_at)
                VALUES ('project-1', 'Legacy Project', 'active', '2026-01-01 00:00:00', '2026-01-01 00:00:00')
            """))
            conn.execute(text("""
                INSERT INTO project_assets (
                    id, project_id, asset_type, original_name, storage_path, mime_type, size, metadata_json, uploaded_at
                )
                VALUES (
                    'asset-1', 'project-1', 'pep', 'sample.html', 'sample.html', 'text/html', 10,
                    '{"relative_path": "sample.html"}', '2026-01-01 00:00:00'
                )
            """))

        ensure_schema_compatibility()

        inspector = inspect(db.engine)
        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        job_columns = {column["name"] for column in inspector.get_columns("analysis_jobs")}
        asset_indexes = {
            index["name"]: tuple(index["column_names"])
            for index in inspector.get_indexes("project_assets")
        }
        assert "user_id" in project_columns
        assert "user_id" in job_columns
        assert {"role", "is_active_flag", "home_path", "allowed_paths", "last_login_at"}.issubset(user_columns)
        assert asset_indexes["ix_project_assets_project_uploaded"] == ("project_id", "uploaded_at")
        assert asset_indexes["ix_project_assets_project_type_uploaded"] == ("project_id", "asset_type", "uploaded_at")

        project = Project.query.filter_by(id="project-1").first()
        assert project is not None
        assert project.user_id is None

        asset = ProjectAsset.query.filter_by(id="asset-1").first()
        assert asset is not None
        assert asset.to_dict()["metadata"] == {"relative_path": "sample.html"}

        user = User.query.filter_by(username="legacy").first()
        assert user is not None
        assert user.role == "user"
        assert user.is_active is False
        assert user.last_login_at is not None

        db.session.remove()


def test_project_asset_list_falls_back_when_mysql_sort_buffer_is_exhausted(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    with app.app_context():
        db.create_all()
        project = Project(id="project-sort-fallback", name="Sort Fallback", status="active")
        first = ProjectAsset(
            id="asset-old",
            project_id=project.id,
            asset_type="pep",
            original_name="old.csv",
            storage_path="old.csv",
            size=1,
            uploaded_at=datetime.utcnow() - timedelta(days=1),
        )
        second = ProjectAsset(
            id="asset-new",
            project_id=project.id,
            asset_type="pep",
            original_name="new.csv",
            storage_path="new.csv",
            size=1,
            uploaded_at=datetime.utcnow(),
        )
        db.session.add_all([project, first, second])
        db.session.commit()

        original_all = Query.all

        class SortBufferError(Exception):
            def __init__(self):
                super().__init__(1038, "Out of sort memory, consider increasing server sort buffer size")

        def flaky_all(self):
            if getattr(self, "_order_by_clauses", ()):
                raise OperationalError("SELECT project_assets", {}, SortBufferError())
            return original_all(self)

        monkeypatch.setattr(Query, "all", flaky_all)

        service = get_project_asset_service(tmp_path)
        assets = service.list_assets(project.id)

        assert [asset.id for asset in assets] == ["asset-new", "asset-old"]
        db.session.remove()
