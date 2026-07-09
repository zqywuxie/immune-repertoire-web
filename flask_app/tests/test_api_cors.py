"""CORS bridge tests for the standalone frontend migration."""

import os

os.environ.setdefault("FLASK_CONFIG", "testing")

from flask_app.app import create_app
from flask_app.models.database import db


def test_allowed_frontend_origin_receives_api_cors_headers():
    app = create_app("testing")
    app.config["FRONTEND_ORIGINS"] = ["http://localhost:5173"]

    with app.app_context():
        response = app.test_client().get("/api/health", headers={"Origin": "http://localhost:5173"})
        db.session.remove()

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]


def test_unlisted_origin_does_not_receive_api_cors_headers():
    app = create_app("testing")
    app.config["FRONTEND_ORIGINS"] = ["http://localhost:5173"]

    with app.app_context():
        response = app.test_client().get("/api/health", headers={"Origin": "http://evil.example"})
        db.session.remove()

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers


def test_api_options_preflight_bypasses_login_requirement():
    app = create_app("testing")
    app.config["REQUIRE_LOGIN"] = True
    app.config["FRONTEND_ORIGINS"] = ["http://localhost:5173"]

    with app.app_context():
        response = app.test_client().options(
            "/api/projects",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Headers": "Content-Type",
            },
        )
        db.session.remove()

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert response.headers["Access-Control-Allow-Headers"] == "Content-Type"
