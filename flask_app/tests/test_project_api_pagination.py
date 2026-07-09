"""Pagination contract tests for project asset/result APIs."""

import os
from datetime import datetime, timedelta

os.environ.setdefault("FLASK_CONFIG", "testing")

from flask_app.app import create_app
from flask_app.models.database import Project, ProjectAsset, db


def _create_project_with_assets(storage_path: str = "", metadata_json=None):
    project = Project(id="project-pagination", name="Pagination Project", status="active")
    db.session.add(project)
    now = datetime.utcnow()
    for index in range(5):
        db.session.add(ProjectAsset(
            id=f"asset-{index}",
            project_id=project.id,
            asset_type="profile" if index % 2 else "processed_result",
            original_name=f"asset-{index}.csv",
            storage_path=storage_path if index == 0 and storage_path else f"/tmp/asset-{index}.csv",
            size=index + 1,
            uploaded_at=now - timedelta(minutes=index),
            metadata_json=metadata_json if index == 0 and metadata_json is not None else ({"analysis_type": "unit-test"} if index % 2 == 0 else {}),
        ))
    db.session.commit()
    return project


def test_project_assets_are_paginated():
    app = create_app("testing")

    with app.app_context():
        project = _create_project_with_assets()
        response = app.test_client().get(f"/api/projects/{project.id}/assets?page=2&page_size=2")
        payload = response.get_json()
        db.session.remove()

    assert response.status_code == 200
    assert len(payload["assets"]) == 2
    assert payload["pagination"] == {
        "page": 2,
        "page_size": 2,
        "total": 5,
        "total_pages": 3,
    }


def test_project_processed_result_assets_are_paginated():
    app = create_app("testing")

    with app.app_context():
        project = _create_project_with_assets()
        response = app.test_client().get(f"/api/projects/{project.id}/assets?asset_type=processed_result&page=1&page_size=2")
        payload = response.get_json()
        db.session.remove()

    assert response.status_code == 200
    assert len(payload["assets"]) == 2
    assert payload["pagination"]["total"] == 3
    assert all(asset["asset_type"] == "processed_result" for asset in payload["assets"])


def test_project_asset_preview_and_download(tmp_path):
    app = create_app("testing")
    asset_file = tmp_path / "asset.csv"
    asset_file.write_text("sample,value\ns1,1\n", encoding="utf-8")

    with app.app_context():
        project = _create_project_with_assets(str(asset_file))
        client = app.test_client()
        preview = client.get(f"/api/projects/{project.id}/assets/asset-0/preview")
        download = client.get(f"/api/projects/{project.id}/assets/asset-0/download")
        global_preview = client.get("/api/assets/asset-0/preview")
        global_download = client.get("/api/assets/asset-0/download")
        db.session.remove()

    assert preview.status_code == 200
    assert preview.data.replace(b"\r\n", b"\n") == b"sample,value\ns1,1\n"
    assert "attachment" not in preview.headers.get("Content-Disposition", "")
    assert download.status_code == 200
    assert b"sample,value" in download.data
    assert "attachment" in download.headers.get("Content-Disposition", "")
    assert global_preview.status_code == 200
    assert global_preview.data.replace(b"\r\n", b"\n") == b"sample,value\ns1,1\n"
    assert "attachment" not in global_preview.headers.get("Content-Disposition", "")
    assert global_download.status_code == 200
    assert b"sample,value" in global_download.data
    assert "attachment" in global_download.headers.get("Content-Disposition", "")


def test_global_asset_preview_prefers_storage_uri(tmp_path):
    app = create_app("testing")
    asset_file = tmp_path / "asset-via-uri.csv"
    asset_file.write_text("sample,value\ns2,2\n", encoding="utf-8")

    with app.app_context():
        from flask_app.services.storage_adapter import get_storage_adapter

        _create_project_with_assets(
            storage_path="/legacy/missing.csv",
            metadata_json={"storage_uri": get_storage_adapter().uri_for_path(asset_file)},
        )
        response = app.test_client().get("/api/assets/asset-0/preview")
        db.session.remove()

    assert response.status_code == 200
    assert response.data.replace(b"\r\n", b"\n") == b"sample,value\ns2,2\n"
