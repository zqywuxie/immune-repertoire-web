"""Pagination contract tests for project asset/result APIs."""

import os
from datetime import datetime, timedelta

os.environ.setdefault("FLASK_CONFIG", "testing")

from flask_app.app import create_app
from flask_app.models.database import Project, ProjectAsset, db


def _create_project_with_assets():
    project = Project(id="project-pagination", name="Pagination Project", status="active")
    db.session.add(project)
    now = datetime.utcnow()
    for index in range(5):
        db.session.add(ProjectAsset(
            id=f"asset-{index}",
            project_id=project.id,
            asset_type="profile" if index % 2 else "processed_result",
            original_name=f"asset-{index}.csv",
            storage_path=f"/tmp/asset-{index}.csv",
            size=index + 1,
            uploaded_at=now - timedelta(minutes=index),
            metadata_json={"analysis_type": "unit-test"} if index % 2 == 0 else {},
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
