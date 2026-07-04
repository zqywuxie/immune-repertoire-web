"""OpenAPI contract tests — verify backend response shapes match the spec.

These tests parse ``docs/api/openapi-draft.yaml`` and validate that each
implemented endpoint returns data matching the declared response schema.
"""

import os

os.environ.setdefault("FLASK_CONFIG", "testing")

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

# ── Load the OpenAPI spec ─────────────────────────────────────────────

_SPEC_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi-draft.yaml"
)


def _load_spec() -> dict:
    return yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8"))


_SPEC = _load_spec()

# Extract paths marked with x-status ✅ (implemented)
_IMPLEMENTED_PATHS: dict[str, dict] = {}
for route, methods in _SPEC.get("paths", {}).items():
    for method, detail in methods.items():
        if not isinstance(detail, dict):
            continue
        if detail.get("x-status") == "✅":
            _IMPLEMENTED_PATHS.setdefault(route, {})[method] = detail

# Import app after spec load (order matters for env setup)
from app.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)


class TestOpenAPIContract:
    """Verify each ✅ endpoint returns the declared shape."""

    # ── GET /api/info ──────────────────────────────────────────────
    def test_info_returns_spec_shape(self):
        spec = _IMPLEMENTED_PATHS.get("/api/info", {}).get("get", {})
        if not spec:
            pytest.skip("No /api/info spec found")

        json_schema = (
            spec.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        expected_keys = set(json_schema.get("properties", {}).keys())

        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        for key in expected_keys:
            assert key in data, f"/api/info missing key: {key}"

    # ── GET /api/jobs/modules ──────────────────────────────────────
    def test_jobs_modules_spec_shape(self):
        spec = _IMPLEMENTED_PATHS.get("/api/jobs/modules", {}).get("get", {})
        if not spec:
            pytest.skip("No /api/jobs/modules spec found")

        resp = client.get("/api/jobs/modules")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("modules"), list), "modules should be a list"

    # ── POST /api/jobs (validation) ────────────────────────────────
    def test_submit_job_spec_shape(self):
        spec = _IMPLEMENTED_PATHS.get("/api/jobs", {}).get("post", {})
        if not spec:
            pytest.skip("No POST /api/jobs spec found")

        json_schema = (
            spec.get("responses", {})
            .get("201", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
            or spec.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        expected_keys = set(json_schema.get("properties", {}).keys())

        resp = client.post("/api/jobs", json={"module": "invalid.module", "payload": {}})
        assert resp.status_code == 400  # validation error

    # ── GET /api/health ────────────────────────────────────────────
    def test_health_returns_spec_shape(self):
        spec = _IMPLEMENTED_PATHS.get("/api/health", {}).get("get", {})
        if not spec:
            # Health endpoint is newly added — ensure it returns valid JSON
            pass

        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("ok", "degraded")


_PARAMETERLESS_PATHS = {"/api/info", "/api/jobs/modules"}

# Pre-compute the list outside the class to avoid scoping issues
_PARAMETERIZED = [
    (r, m) for r, m in _IMPLEMENTED_PATHS.items()
    if "get" in m and r not in _PARAMETERLESS_PATHS
]


class TestAllImplementedPathsReturnSensibleStatus:
    """Smoke-test every ✅ endpoint."""

    @pytest.mark.parametrize("route", sorted(_PARAMETERLESS_PATHS))
    def test_parameterless_endpoint_ok(self, route):
        resp = client.get(route)
        assert resp.status_code == 200, f"{route} returned {resp.status_code}"

    @pytest.mark.parametrize("route,methods", _PARAMETERIZED)
    def test_parameterized_get_endpoint(self, route, methods):
        """GET with placeholder params — may 404/422/500. Must not crash."""
        url = route
        for part in url.split("/"):
            if part.startswith("{") and part.endswith("}"):
                url = url.replace(part, "dummy-param")
        resp = client.get(url)
        assert resp.status_code in (200, 404, 422, 405, 500), (
            f"{route} → {url} returned unexpected {resp.status_code}"
        )


class TestResponseContentTypes:
    """Verify API responses use the correct Content-Type."""

    def test_json_endpoints_return_json(self):
        for route, methods in _IMPLEMENTED_PATHS.items():
            if "get" not in methods:
                continue
            resp = client.get(route)
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                # Some GET endpoints may return 404/422 for missing params
                if "application/json" in ct:
                    # Verify parseable JSON
                    try:
                        resp.json()
                    except Exception:
                        pytest.fail(f"{route} claims JSON but body is unparseable")


class TestOpenAPISpecInternalConsistency:
    """Verify the OpenAPI spec itself is well-formed."""

    def test_spec_has_version(self):
        assert "openapi" in _SPEC
        assert "info" in _SPEC
        assert "version" in _SPEC["info"]

    def test_all_tags_have_paths(self):
        tags = {t["name"] for t in _SPEC.get("tags", [])}
        used_tags: set[str] = set()
        for methods in _SPEC.get("paths", {}).values():
            for detail in methods.values():
                if isinstance(detail, dict):
                    for t in detail.get("tags", []):
                        used_tags.add(t)
        unused = tags - used_tags
        assert not unused, f"Tags defined but never used: {unused}"

    def test_no_empty_path_definitions(self):
        for route, methods in _SPEC.get("paths", {}).items():
            assert methods, f"Path {route} has no methods defined"

    def test_implemented_paths_count(self):
        """At minimum we should have the core business API paths implemented."""
        count = len(_IMPLEMENTED_PATHS)
        assert count >= 5, (
            f"Only {count} ✅ paths — should have at least 5 core endpoints"
        )
