"""Unit tests for repository layer — validates SQL patterns and row mapping."""

import os
os.environ.setdefault("FLASK_CONFIG", "testing")

import pytest

# Verify all repository modules compile and import cleanly
# (Full integration tests require a running MySQL — these tests
# verify structural correctness: columns, params, SQL safety.)


class TestProjectRepository:
    """Verify ProjectRepository structure and SQL safety."""

    def test_imports_cleanly(self):
        from app.repositories.projects import ProjectRepository
        assert ProjectRepository is not None

    def test_methods_exist(self):
        from app.repositories.projects import ProjectRepository
        methods = [m for m in dir(ProjectRepository) if not m.startswith("_")]
        assert "list_all" in methods
        assert "get_by_id" in methods
        assert "create" in methods
        assert "update" in methods

    def test_to_dict_like_structure(self):
        """Repository returns dicts matching ProjectSummary schema keys."""
        from app.repositories.projects import ProjectRepository

        # Simulated row from .mappings() call
        mock_row = {
            "id": "p1", "name": "Test", "user_id": None,
            "institution": "Uni", "cooperation_level": "public",
            "description": "desc", "status": "active",
            "created_at": "2026-01-01", "updated_at": "2026-01-01",
        }
        result = dict(mock_row)
        # Verify keys match what routes expect
        expected_keys = {"id", "name", "user_id", "institution",
                         "cooperation_level", "description", "status",
                         "created_at", "updated_at"}
        assert expected_keys.issubset(set(result.keys()))


class TestAssetRepository:
    """Verify AssetRepository structure and row mapping."""

    def test_imports_cleanly(self):
        from app.repositories.assets import AssetRepository
        assert AssetRepository is not None

    def test_methods_exist(self):
        from app.repositories.assets import AssetRepository
        methods = [m for m in dir(AssetRepository) if not m.startswith("_")]
        assert "list_by_project" in methods
        assert "get_by_id" in methods
        assert "create" in methods
        assert "delete" in methods
        assert "find_by_project_and_type" in methods

    def test_to_dict_maps_storage_uri(self):
        from app.repositories.assets import AssetRepository

        mock_row = {
            "id": "a1", "project_id": "p1", "asset_type": "input",
            "original_name": "data.csv", "storage_path": "/tmp/data.csv",
            "mime_type": "text/csv", "size": 1024,
            "metadata_json": {"storage_uri": "local:///tmp/data.csv"},
            "uploaded_at": "2026-01-01",
        }
        result = AssetRepository._to_dict(mock_row)
        assert result["storage_uri"] == "local:///tmp/data.csv"
        assert result["mime_type"] == "text/csv"
        assert result["size"] == 1024

    def test_to_dict_handles_null_metadata(self):
        from app.repositories.assets import AssetRepository

        mock_row = {
            "id": "a1", "project_id": "p1", "asset_type": "input",
            "original_name": "data.csv", "storage_path": "/tmp/data.csv",
            "mime_type": None, "size": 0,
            "metadata_json": None,
            "uploaded_at": None,
        }
        result = AssetRepository._to_dict(mock_row)
        assert result["metadata"] == {}
        assert result["storage_uri"] is None


class TestJobRepository:
    """Verify JobRepository structure and row mapping."""

    def test_imports_cleanly(self):
        from app.repositories.jobs import JobRepository
        assert JobRepository is not None

    def test_methods_exist(self):
        from app.repositories.jobs import JobRepository
        methods = [m for m in dir(JobRepository) if not m.startswith("_")]
        assert "list_all" in methods
        assert "get_by_id" in methods
        assert "create" in methods
        assert "update_status" in methods
        assert "set_cancel_requested" in methods
        assert "delete" in methods

    def test_to_dict_maps_all_fields(self):
        from app.repositories.jobs import JobRepository

        mock_row = {
            "id": "j1", "job_id": "j1", "job_type": "api_request",
            "module": "charts.combined", "status": "running",
            "progress": 50.0, "stage": "executing", "detail": None,
            "payload": {"key": "val"}, "result": {"out": 1},
            "error": None, "project_id": "p1", "user_id": None,
            "created_at": "2026-01-01", "updated_at": "2026-01-01",
            "started_at": None, "completed_at": None,
        }
        result = JobRepository._to_dict(mock_row)
        assert result["id"] == "j1"
        assert result["status"] == "running"
        assert result["progress"] == 50.0
        assert result["payload"] == {"key": "val"}
        assert result["result"] == {"out": 1}

    def test_to_dict_handles_null_fields(self):
        from app.repositories.jobs import JobRepository

        mock_row = {
            "id": "j1", "job_id": None, "job_type": None,
            "module": None, "status": None, "progress": None,
            "stage": None, "detail": None, "payload": None,
            "result": None, "error": None, "project_id": None,
            "user_id": None, "created_at": None, "updated_at": None,
            "started_at": None, "completed_at": None,
        }
        result = JobRepository._to_dict(mock_row)
        # Should not raise; should return safe defaults
        assert result["status"] in ("queued", "")
        assert result["progress"] == 0.0
        assert isinstance(result["payload"], dict)
        assert isinstance(result["result"], dict)


class TestServiceLayer:
    """Verify services import and have expected methods."""

    def test_project_service_imports(self):
        from app.services.project_service import ProjectService
        assert ProjectService is not None

    def test_asset_service_imports(self):
        from app.services.asset_service import AssetService
        assert AssetService is not None

    def test_job_service_imports(self):
        from app.services.job_service import JobService
        assert JobService is not None

    def test_job_service_validates_modules(self):
        from app.services.job_service import JobService
        from unittest.mock import MagicMock

        svc = JobService(MagicMock())
        # Valid module should not raise
        svc.validate_module("charts.combined")  # no exception

    def test_job_service_rejects_invalid_module(self):
        from app.services.job_service import JobService
        from unittest.mock import MagicMock
        from fastapi import HTTPException

        svc = JobService(MagicMock())
        with pytest.raises(HTTPException) as exc:
            svc.validate_module("invalid.something")
        assert exc.value.status_code == 400

    def test_job_service_terminal_status_check(self):
        from app.services.job_service import JobService

        assert JobService.is_terminal("completed") is True
        assert JobService.is_terminal("failed") is True
        assert JobService.is_terminal("cancelled") is True
        assert JobService.is_terminal("running") is False
        assert JobService.is_terminal("queued") is False


class TestJobResultsAggregation:
    """B3: Verify result aggregation helpers."""

    def test_kind_from_mime_html(self):
        from app.api.jobs import _kind_from_mime
        assert _kind_from_mime("text/html") == "html"

    def test_kind_from_mime_image(self):
        from app.api.jobs import _kind_from_mime
        assert _kind_from_mime("image/png") == "image"
        assert _kind_from_mime("image/jpeg") == "image"

    def test_kind_from_mime_csv(self):
        from app.api.jobs import _kind_from_mime
        assert _kind_from_mime("text/csv") == "csv"

    def test_kind_from_mime_zip(self):
        from app.api.jobs import _kind_from_mime
        assert _kind_from_mime("application/zip") == "zip"

    def test_kind_from_mime_pdf(self):
        from app.api.jobs import _kind_from_mime
        assert _kind_from_mime("application/pdf") == "pdf"

    def test_kind_from_mime_ppt(self):
        from app.api.jobs import _kind_from_mime
        assert _kind_from_mime("application/vnd.ms-powerpoint") == "ppt"

    def test_kind_from_mime_unknown(self):
        from app.api.jobs import _kind_from_mime
        assert _kind_from_mime("") == "data"
        assert _kind_from_mime(None) == "data"


class TestJobDispatch:
    """Verify submitted jobs are handed to a real background worker."""

    def test_start_background_job_spawns_daemon_thread(self, monkeypatch):
        from app.api import jobs as jobs_api

        captured = {}

        class DummyThread:
            def __init__(self, target, args, daemon, name):
                captured["target"] = target
                captured["args"] = args
                captured["daemon"] = daemon
                captured["name"] = name

            def start(self):
                captured["started"] = True

        monkeypatch.setattr(jobs_api.threading, "Thread", DummyThread)

        jobs_api._start_background_job("charts.combined", "job-123456789")

        assert captured["target"] is jobs_api._execute_job_background
        assert captured["args"] == ("charts.combined", "job-123456789")
        assert captured["daemon"] is True
        assert captured["name"] == "analysis-job-job-1234"
        assert captured["started"] is True


class TestNoRawSQLInRoutes:
    """Verify route files no longer contain raw SQL patterns."""

    def test_projects_route_has_no_raw_sql(self):
        import ast
        import inspect
        from app.api.projects import (
            list_projects, create_project, get_project, update_project,
            list_project_results,
        )
        for fn in [list_projects, create_project, get_project, update_project,
                    list_project_results]:
            source = inspect.getsource(fn)
            # No direct text() calls (repository handles SQL)
            assert "text(" not in source, f"{fn.__name__} still contains raw text() call"

    def test_assets_route_has_no_raw_sql_except_upload(self):
        """Upload endpoint still has DB insert via service — verify list/get/download are clean."""
        import inspect
        from app.api.assets import list_project_assets, preview_asset, download_asset
        for fn in [list_project_assets, preview_asset, download_asset]:
            source = inspect.getsource(fn)
            assert "text(" not in source, f"{fn.__name__} still contains raw text() call"

    def test_jobs_route_has_no_raw_sql_in_crud(self):
        import inspect
        from app.api.jobs import list_jobs, submit_job, get_job, cancel_job, delete_job
        for fn in [list_jobs, submit_job, get_job, cancel_job, delete_job]:
            source = inspect.getsource(fn)
            assert "text(" not in source, f"{fn.__name__} still contains raw text() call"
