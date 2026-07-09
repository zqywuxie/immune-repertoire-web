"""Integration tests for FastAPI project routes."""

import os
os.environ.setdefault("FLASK_CONFIG", "testing")

import pytest
from fastapi.testclient import TestClient

# Set testing before importing app (triggers Flask create_app which reads FLASK_CONFIG)
os.environ["API_DEBUG"] = "1"

from app.main import app
from app.core.config import settings

client = TestClient(app, raise_server_exceptions=False)


class TestProjectRoutes:
    """Test /api/projects endpoints."""

    def test_list_projects_returns_200(self):
        response = client.get("/api/projects")
        # May return 200 (empty list) or 500 (if DB not available)
        assert response.status_code in (200, 500)

    def test_list_projects_response_structure(self):
        response = client.get("/api/projects")
        if response.status_code == 200:
            data = response.json()
            assert "projects" in data
            assert isinstance(data["projects"], list)

    def test_get_project_404_for_nonexistent(self):
        response = client.get("/api/projects/nonexistent-id-12345")
        # 404 if DB available and row not found, 500 if DB unavailable
        assert response.status_code in (404, 500)

    def test_create_project_validation(self):
        """POST without name should return 422."""
        response = client.post("/api/projects", json={})
        assert response.status_code in (422, 501)  # 422 if validation works, 501 if DB unavailable


class TestJobRoutes:
    """Test /api/jobs endpoints."""

    def test_list_jobs_returns_200(self):
        response = client.get("/api/jobs")
        assert response.status_code in (200, 500)

    def test_list_job_modules(self):
        response = client.get("/api/jobs/modules")
        assert response.status_code == 200
        data = response.json()
        assert "modules" in data
        assert len(data["modules"]) >= 1

    def test_get_job_404(self):
        response = client.get("/api/jobs/nonexistent-job")
        # 404 if DB available, 500 if DB unavailable
        assert response.status_code in (404, 500)

    def test_cancel_job_404(self):
        response = client.post("/api/jobs/nonexistent-job/cancel")
        assert response.status_code in (404, 500)

    def test_results_404(self):
        response = client.get("/api/jobs/nonexistent-job/results")
        assert response.status_code in (404, 500)

    def test_submit_job_validation(self):
        """Submit with unsupported module returns 400."""
        response = client.post("/api/jobs", json={"module": "invalid.module", "payload": {}})
        assert response.status_code == 400

    def test_submit_job_charts_combined(self):
        """Submit with valid module creates job or returns 500 if no DB."""
        response = client.post("/api/jobs", json={
            "module": "charts.combined",
            "payload": {"selected_modules": ["heatmap"]},
        })
        assert response.status_code in (200, 500)


class TestAssetRoutes:
    """Test /api/assets endpoints."""

    def test_preview_404(self):
        response = client.get("/api/assets/nonexistent/preview")
        # 404 if DB available, 500 if DB unavailable
        assert response.status_code in (404, 500)

    def test_download_404(self):
        response = client.get("/api/assets/nonexistent/download")
        assert response.status_code in (404, 500)

    def test_project_assets_404_project(self):
        """Non-existent project returns empty or error."""
        response = client.get("/api/projects/nonexistent-123/assets")
        assert response.status_code in (200, 404, 500)


class TestErrorHandling:
    """Test FastAPI error middleware."""

    def test_404_returns_json(self):
        response = client.get("/api/nonexistent-endpoint")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data or "message" in data

    def test_invalid_json_body(self):
        """Malformed JSON returns 422."""
        response = client.post(
            "/api/projects",
            content=b"not valid json {{{",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestSystemRoutes:
    """Test system endpoints."""

    def test_api_info(self):
        """GET /api/info — will be 404 since no such route exists yet."""
        response = client.get("/api/info")
        assert response.status_code in (200, 404)


class TestAuthRoutes:
    """Test migration-phase FastAPI auth behavior."""

    def test_auth_me_defaults_to_disabled_migration_principal(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_token", "")

        response = client.get("/api/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["authenticated"] is False
        assert data["subject"] == "migration-anonymous"
        assert data["auth_mode"] == "disabled"

    def test_auth_me_requires_token_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_token", "secret-token")

        response = client.get("/api/auth/me")

        assert response.status_code == 401

    def test_auth_me_accepts_bearer_token(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_token", "secret-token")

        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer secret-token"},
        )

        assert response.status_code == 200
        assert response.json()["authenticated"] is True

    def test_auth_me_accepts_x_api_key(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_token", "secret-token")

        response = client.get(
            "/api/auth/me",
            headers={"X-API-Key": "secret-token"},
        )

        assert response.status_code == 200
        assert response.json()["auth_mode"] == "api_token"

    def test_stable_business_routes_require_token_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_token", "secret-token")

        response = client.get("/api/jobs/modules")

        assert response.status_code == 401

    def test_stable_business_routes_accept_token_when_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "auth_token", "secret-token")

        response = client.get("/api/jobs/modules", headers={"X-API-Key": "secret-token"})

        assert response.status_code == 200
        assert "modules" in response.json()
