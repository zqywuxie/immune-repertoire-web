"""Tests for SSH remote source API endpoints used by the chord module."""

from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, current_app


def _import_api_module():
    try:
        return import_module("flask_app.routes.api_remote_sources")
    except ModuleNotFoundError:
        return import_module("routes.api_remote_sources")


@pytest.fixture
def client():
    api_remote_sources = _import_api_module()
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["SSH_REMOTE_SOURCES"] = [
        {
            "id": "linux_a",
            "name": "Linux A",
            "host": "10.0.0.8",
            "port": 22,
            "username": "analysis",
            "auth_type": "password",
            "password": "secret",
            "root_path": "/data/repertoire",
            "enabled": True,
        }
    ]

    app.config["REMOTE_CACHE_FOLDER"] = Path.cwd() / ".tmp_pytest" / "remote_sources_api_cache"
    app.config["REMOTE_SYNC_ALLOWED_EXTENSIONS"] = {".csv", ".csv.gz"}
    app.config["REMOTE_SYNC_HIDDEN_DIRECTORIES"] = [".git"]
    api_remote_sources._sync_tasks.clear()
    app.register_blueprint(api_remote_sources.remote_sources_bp)

    with app.test_client() as test_client:
        yield test_client


def test_list_remote_sources_hides_credentials(client):
    response = client.get("/api/remote-sources")
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["success"] is True
    assert payload["sources"][0]["id"] == "linux_a"
    assert "password" not in payload["sources"][0]


def test_browse_remote_source(client, monkeypatch):
    api_remote_sources = _import_api_module()

    class FakeProvider:
        def __init__(self, source):
            self.source = source

        def list_dir(self, path):
            assert path == "/data/repertoire/project1"
            return {
                "root_path": "/data/repertoire",
                "current_path": "/data/repertoire/project1",
                "parent_path": "/data/repertoire",
                "entries": [
                    {"name": "SampleA", "path": "/data/repertoire/project1/SampleA", "is_dir": True, "size": 0, "modified_time": 0}
                ],
            }

    monkeypatch.setattr(api_remote_sources, "build_ssh_file_provider", lambda source: FakeProvider(source))

    response = client.post(
        "/api/remote-sources/browse",
        json={"source_id": "linux_a", "path": "/data/repertoire/project1"},
    )
    assert response.status_code == 200

    payload = response.get_json()
    assert payload["success"] is True
    assert payload["current_path"] == "/data/repertoire/project1"
    assert payload["entries"][0]["name"] == "SampleA"


def test_sync_remote_source_task_for_chord(client, monkeypatch):
    api_remote_sources = _import_api_module()

    class FakeProvider:
        def __init__(self, source):
            self.source = source

        def resolve_remote_path(self, path):
            return path

    class FakeSyncService:
        def sync_directory(self, source, remote_path, force_refresh=False, progress_callback=None):
            if progress_callback:
                progress_callback(
                    50.0,
                    "Downloading remote files",
                    "Downloaded SampleA/SampleA__TRA.csv.gz",
                    {"phase": "download_remote", "current_file": "SampleA/SampleA__TRA.csv.gz"},
                )
            return {
                "source_id": source.source_id,
                "remote_path": remote_path,
                "local_cache_path": "E:/virtual-cache/linux_a/project1/data",
                "file_count": 3,
                "total_bytes": 2048,
                "reused_cache": False,
            }

    monkeypatch.setattr(api_remote_sources, "build_ssh_file_provider", lambda source: FakeProvider(source))
    monkeypatch.setattr(api_remote_sources, "get_remote_sync_service", lambda: FakeSyncService())
    monkeypatch.setattr(
        api_remote_sources,
        "_sync_executor",
        SimpleNamespace(submit=lambda fn, *args, **kwargs: fn(*args, **kwargs)),
    )

    response = client.post(
        "/api/remote-sources/sync",
        json={"source_id": "linux_a", "remote_path": "/data/repertoire/project1"},
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["task_id"].startswith("remote_sync_")

    status_response = client.get(f"/api/remote-sources/sync-task/{payload['task_id']}")
    assert status_response.status_code == 200
    status_payload = status_response.get_json()
    assert status_payload["success"] is True
    assert status_payload["status"] == "completed"
    assert status_payload["result"]["local_cache_path"].endswith("/data")
    assert status_payload["result"]["file_count"] == 3


def test_run_sync_task_uses_application_context(monkeypatch):
    api_remote_sources = _import_api_module()
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["REMOTE_CACHE_FOLDER"] = Path.cwd() / ".tmp_pytest" / "remote_sources_context_cache"

    source = SimpleNamespace(source_id="linux_a", name="Linux A")

    class FakeSourceService:
        def get_source(self, source_id):
            assert current_app.config["TESTING"] is True
            assert source_id == "linux_a"
            return source

    class FakeSyncService:
        def sync_directory(self, source, remote_path, force_refresh=False, progress_callback=None):
            assert current_app.config["REMOTE_CACHE_FOLDER"].name == "remote_sources_context_cache"
            if progress_callback:
                progress_callback(35.0, "Inspecting remote files", f"Scanning {remote_path}", {"phase": "scan_remote"})
            return {
                "source_id": source.source_id,
                "remote_path": remote_path,
                "local_cache_path": "E:/virtual-cache/linux_a/project1/data",
                "file_count": 2,
                "total_bytes": 128,
                "reused_cache": False,
            }

    monkeypatch.setattr(api_remote_sources, "get_remote_data_source_service", lambda: FakeSourceService())
    monkeypatch.setattr(api_remote_sources, "get_remote_sync_service", lambda: FakeSyncService())

    api_remote_sources._sync_tasks.clear()
    api_remote_sources._run_sync_task(
        app,
        "remote_sync_context",
        source_id="linux_a",
        remote_path="/data/repertoire/project1",
        force_refresh=False,
    )

    task_state = api_remote_sources._get_task_state("remote_sync_context")
    assert task_state["status"] == "completed"
    assert task_state["result"]["file_count"] == 2
