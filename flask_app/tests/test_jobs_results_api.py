"""Unified background job result API tests."""

import os
from datetime import datetime

os.environ.setdefault("FLASK_CONFIG", "testing")

from flask_app.app import create_app
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, db


def test_job_results_include_outputs_and_registered_assets():
    app = create_app("testing")

    with app.app_context():
        project = Project(id="project-job-results", name="Job Results Project", status="active")
        db.session.add(project)
        db.session.add(AnalysisJob(
            id="job_results_1",
            job_type="api_request",
            module="charts.combined",
            status="completed",
            progress=100,
            result={
                "viewer_url": "/reports/job_results_1/index.html",
                "zip_url": "/reports/job_results_1/bundle.zip",
                "chart_results": [
                    {"module": "treemap", "viewer_url": "/reports/job_results_1/treemap.html"},
                ],
            },
            project_id=project.id,
        ))
        db.session.add(ProjectAsset(
            id="asset-job-result",
            project_id=project.id,
            asset_type="processed_result",
            original_name="combined_result",
            storage_path="/tmp/combined_result",
            mime_type="application/octet-stream",
            size=0,
            metadata_json={"job_id": "job_results_1", "analysis_type": "charts.combined"},
            uploaded_at=datetime.utcnow(),
        ))
        db.session.commit()

        response = app.test_client().get("/api/jobs/job_results_1/results")
        payload = response.get_json()
        db.session.remove()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["status"] == "completed"
    assert [output["url"] for output in payload["outputs"]] == [
        "/reports/job_results_1/index.html",
        "/reports/job_results_1/bundle.zip",
        "/reports/job_results_1/treemap.html",
    ]
    assert payload["assets"][0]["id"] == "asset-job-result"
    assert payload["assets"][0]["preview_url"] == "/api/assets/asset-job-result/preview"
    assert payload["assets"][0]["download_url"] == "/api/assets/asset-job-result/download"


def test_job_results_missing_job_returns_404():
    app = create_app("testing")

    response = app.test_client().get("/api/jobs/missing/results")
    payload = response.get_json()

    assert response.status_code == 404
    assert payload["success"] is False
    assert payload["error"] == "JOB_NOT_FOUND"


def test_job_events_stream_completed_job_once():
    app = create_app("testing")

    with app.app_context():
        db.session.add(AnalysisJob(
            id="job_events_done",
            job_type="api_request",
            module="charts.combined",
            status="completed",
            progress=100,
            stage="Completed",
            detail="Task completed",
            result={"viewer_url": "/reports/job_events_done/index.html"},
        ))
        db.session.commit()

        response = app.test_client().get("/api/jobs/job_events_done/events?max_events=2")
        body = response.get_data(as_text=True)
        db.session.remove()

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert "event: completed" in body
    assert '"job_id": "job_events_done"' in body
    assert '"status": "completed"' in body


def test_job_events_missing_job_returns_404():
    app = create_app("testing")

    response = app.test_client().get("/api/jobs/missing/events")
    payload = response.get_json()

    assert response.status_code == 404
    assert payload["success"] is False
    assert payload["error"] == "JOB_NOT_FOUND"
