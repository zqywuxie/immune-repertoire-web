from pathlib import Path

import pytest
from flask import Flask

from flask_app.exceptions import AnalysisInProgressError, ValidationError
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, db
from flask_app.services.project_service import ProjectService


@pytest.fixture
def app_context(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        REQUIRE_LOGIN=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        PROJECT_DATA_ROOT=tmp_path / "uploads",
        RESULTS_FOLDER=tmp_path / "results",
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app, tmp_path
        db.session.remove()
        db.drop_all()


def _project(name):
    project = Project(name=name)
    db.session.add(project)
    db.session.commit()
    return project


def _job(project_id, status="completed"):
    job = AnalysisJob(
        id=f"job-{project_id[:8]}-{status}",
        job_type="script_hub",
        module="profile",
        status=status,
        project_id=project_id,
    )
    db.session.add(job)
    db.session.commit()
    return job


def test_delete_project_cleans_only_its_managed_uploads_results_and_records(app_context, monkeypatch):
    app, tmp_path = app_context
    project = _project("delete me")
    sibling = _project("keep me")
    service = ProjectService(tmp_path / "legacy-upload-root")
    project_data = service.get_project_dir(project)
    sibling_data = service.get_project_dir(sibling)
    project_data.mkdir(parents=True)
    sibling_data.mkdir(parents=True)

    from flask_app.services.project_storage_paths import project_results_dir
    project_results = project_results_dir(project, app.config["RESULTS_FOLDER"])
    sibling_results = project_results_dir(sibling, app.config["RESULTS_FOLDER"])
    project_results.mkdir(parents=True)
    sibling_results.mkdir(parents=True)
    (project_data / "input.csv").write_text("sample,value\nS1,1\n", encoding="utf-8")
    (project_results / "20260928" / "profile" / "profile_job").mkdir(parents=True)
    result_file = project_results / "20260928" / "profile" / "profile_job" / "result.csv"
    result_file.write_text("value\n1\n", encoding="utf-8")
    external = tmp_path / "external" / "source.csv"
    external.parent.mkdir()
    external.write_text("preserve", encoding="utf-8")
    db.session.add(ProjectAsset(
        project_id=project.id,
        asset_type="profile",
        original_name="external.csv",
        storage_path=str(external),
        size=external.stat().st_size,
    ))
    job = _job(project.id)
    db.session.add(AnalysisJob(
        id="sibling-job",
        job_type="script_hub",
        module="profile",
        status="completed",
        project_id=sibling.id,
    ))
    db.session.commit()

    mongo_calls = []
    monkeypatch.setattr(
        "flask_app.services.mongo_service.delete_project_records",
        lambda project_id: mongo_calls.append(project_id) or {"rawdata": 1, "results": 1, "analysis_cache": 1},
    )

    service.delete_project(project)

    assert db.session.get(Project, project.id) is None
    assert db.session.get(AnalysisJob, job.id) is None
    assert db.session.get(AnalysisJob, "sibling-job") is not None
    assert not project_data.exists()
    assert not project_results.exists()
    assert sibling_data.exists()
    assert sibling_results.exists()
    assert external.read_text(encoding="utf-8") == "preserve"
    assert mongo_calls == [project.id]


@pytest.mark.parametrize("status", ["queued", "running"])
def test_delete_project_refuses_while_analysis_is_not_terminal(app_context, monkeypatch, status):
    app, tmp_path = app_context
    project = _project("active task")
    service = ProjectService(tmp_path / "uploads")
    project_data = service.get_project_dir(project)
    project_data.mkdir(parents=True)
    (project_data / "input.csv").write_text("preserve", encoding="utf-8")
    job = _job(project.id, status)

    monkeypatch.setattr(
        "flask_app.services.mongo_service.delete_project_records",
        lambda project_id: pytest.fail("Mongo records must not be deleted for a refused project deletion"),
    )

    with pytest.raises(AnalysisInProgressError):
        service.delete_project(project)

    assert db.session.get(Project, project.id) is not None
    assert db.session.get(AnalysisJob, job.id) is not None
    assert (project_data / "input.csv").read_text(encoding="utf-8") == "preserve"


def test_mongo_cleanup_failure_rolls_back_project_records_without_removing_files(app_context, monkeypatch):
    app, tmp_path = app_context
    project = _project("mongo failure")
    service = ProjectService(tmp_path / "uploads")
    project_data = service.get_project_dir(project)
    project_data.mkdir(parents=True)
    source = project_data / "input.csv"
    source.write_text("preserve", encoding="utf-8")
    job = _job(project.id)

    def fail_mongo_cleanup(_project_id):
        raise RuntimeError("MongoDB unavailable")

    monkeypatch.setattr("flask_app.services.mongo_service.delete_project_records", fail_mongo_cleanup)
    with pytest.raises(RuntimeError, match="MongoDB unavailable"):
        service.delete_project(project)

    assert db.session.get(Project, project.id) is not None
    assert db.session.get(AnalysisJob, job.id) is not None
    assert source.read_text(encoding="utf-8") == "preserve"


def test_project_storage_path_rejects_symlink_to_sibling_project(app_context, tmp_path):
    _, root = app_context
    project = _project("symlink")
    sibling = _project("sibling")
    projects_root = root / "uploads"
    legacy_root = projects_root / "legacy"
    legacy_root.mkdir(parents=True)
    sibling_target = legacy_root / sibling.id
    sibling_target.mkdir()
    (sibling_target / "owned.csv").write_text("keep", encoding="utf-8")
    (legacy_root / project.id).symlink_to(sibling_target, target_is_directory=True)

    from flask_app.services.project_storage_paths import project_data_dir
    with pytest.raises(ValidationError, match="符号链接"):
        project_data_dir(project, projects_root)
    assert (sibling_target / "owned.csv").read_text(encoding="utf-8") == "keep"
