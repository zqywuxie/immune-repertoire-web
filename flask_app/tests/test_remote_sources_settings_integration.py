"""Integration tests for settings-backed SSH remote source configuration."""

from flask_app.app import create_app
from flask_app.models.database import db


def test_remote_sources_follow_saved_settings():
    app = create_app('testing')

    with app.app_context():
        db.create_all()

    try:
        with app.test_client() as client:
            response = client.post(
                "/api/config",
                json={
                    "config_id": "default",
                    "config": {
                        "ssh_remote_sources": [
                            {
                                "id": "linux_settings_a",
                                "name": "Linux Settings A",
                                "host": "10.0.0.9",
                                "port": 22,
                                "username": "analysis",
                                "auth_type": "password",
                                "password": "secret",
                                "root_path": "/data/repertoire",
                                "enabled": True,
                                "description": "saved from settings",
                            }
                        ]
                    },
                },
            )
            assert response.status_code == 200
            payload = response.get_json()
            assert payload["success"] is True
            assert payload["config"]["ssh_remote_sources"][0]["id"] == "linux_settings_a"

            config_response = client.get("/api/config")
            assert config_response.status_code == 200
            config_payload = config_response.get_json()
            assert config_payload["config"]["ssh_remote_sources"][0]["host"] == "10.0.0.9"

            remote_sources_response = client.get("/api/remote-sources")
            assert remote_sources_response.status_code == 200
            remote_sources_payload = remote_sources_response.get_json()
            assert remote_sources_payload["success"] is True
            assert remote_sources_payload["sources"][0]["id"] == "linux_settings_a"
            assert "password" not in remote_sources_payload["sources"][0]
    finally:
        with app.app_context():
            db.session.remove()
            db.drop_all()
