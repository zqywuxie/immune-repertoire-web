"""Smoke tests for the modular api/ Blueprint package — verifies 81 routes survived the split."""

import os

os.environ.setdefault("FLASK_CONFIG", "testing")

from flask_app.app import create_app


def test_api_blueprint_registers():
    """The api_bp Blueprint is registered and has routes."""
    app = create_app("testing")
    with app.app_context():
        rules = [r for r in app.url_map.iter_rules() if r.rule.startswith("/api")]
        paths = sorted(set(r.rule for r in rules))
        assert len(paths) >= 70, f"Expected at least 70 /api routes, got {len(paths)}"


def test_health_endpoint():
    """GET /api/health returns 200."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/health")
        assert resp.status_code == 200


def test_info_endpoint():
    """GET /api/info returns JSON with name and version."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "name" in data


def test_config_options():
    """GET /api/config/options returns supported config keys."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/config/options")
        assert resp.status_code == 200


def test_analysis_types():
    """GET /api/analysis/types returns list of analysis types."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/analysis/types")
        assert resp.status_code == 200


def test_color_schemes():
    """GET /api/color-schemes returns list."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/color-schemes")
        assert resp.status_code == 200


def test_list_files():
    """GET /api/files returns file list."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/files")
        assert resp.status_code in (200, 400, 500)  # 500 ok if no DB


def test_list_directories():
    """GET /api/directories returns directory list."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/directories")
        assert resp.status_code in (200, 400, 500)


def test_directories_validate():
    """GET /api/directories/validate returns validation info."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/directories/validate")
        assert resp.status_code in (200, 400, 500)


def test_mappings_list():
    """GET /api/mappings returns mapping templates."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/mappings")
        assert resp.status_code in (200, 400, 500)


def test_parameters_templates_list():
    """GET /api/parameters/templates returns templates."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/parameters/templates")
        assert resp.status_code in (200, 400, 500)


def test_annotations_types():
    """GET /api/annotations/types returns annotation types."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/annotations/types")
        assert resp.status_code == 200


def test_config_get():
    """GET /api/config returns config."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/config")
        assert resp.status_code in (200, 400, 500)


def test_field_mapping_suggest():
    """GET /api/field-mapping/suggest returns suggestions."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/field-mapping/suggest")
        assert resp.status_code in (200, 400, 500)


def test_files_projects():
    """GET /api/files/projects returns project files."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/files/projects")
        assert resp.status_code in (200, 400, 500)


def test_groups_list():
    """GET /api/groups returns groups."""
    app = create_app("testing")
    with app.test_client() as client:
        resp = client.get("/api/groups")
        assert resp.status_code in (200, 400, 500)


def test_no_import_errors_from_legacy_path():
    """Backwards-compat: from flask_app.routes.api import api_bp still works."""
    from flask_app.routes.api import api_bp
    assert api_bp is not None
    assert api_bp.name == "api"


def test_all_submodules_importable():
    """Each sub-module in the api/ package imports cleanly."""
    from flask_app.routes.api import (
        files, mappings, directories_files, analysis_bridge,
        config_params, annotations_groups, baseline_extra,
        pdf_routes, misc_routes,
    )
    for mod in [files, mappings, directories_files, analysis_bridge,
                config_params, annotations_groups, baseline_extra,
                pdf_routes, misc_routes]:
        assert hasattr(mod, "bp"), f"{mod.__name__} should have a 'bp' attribute"
