"""Storage contracts across shared projects, authenticated users and task cleanup."""
import io
import re
from pathlib import Path

import pytest
from flask import Flask, g
from werkzeug.datastructures import FileStorage

from flask_app.models.database import AnalysisJob, Project, ProjectAsset, User, db
from flask_app.services.background_job_service import get_background_job_service
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.services.project_service import ProjectService
from flask_app.services.project_storage_paths import (
    allocate_result_dir, project_result_parent, project_upload_parent, script_output_parent,
)


@pytest.fixture
def storage(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True, REQUIRE_LOGIN=False, INTERNAL_MODE=True,
        APP_STORAGE_USER="zhengqinyun",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        PROJECT_DATA_ROOT=tmp_path / "上传 数据", RESULTS_FOLDER=tmp_path / "分析 结果",
        ALLOWED_BASE_PATHS=[str(tmp_path)],
    )
    db.init_app(app)
    monkeypatch.setattr("flask_app.services.mongo_service.delete_project_records", lambda _: {})
    with app.app_context():
        db.create_all()
        yield app, tmp_path, ProjectAssetService(tmp_path / "old-fallback")
        db.session.remove()
        db.drop_all()


def project(name, user=None):
    item = Project(name=name, user_id=user.id if user else None)
    db.session.add(item)
    db.session.commit()
    return item


def upload(service, item, name="profile.csv"):
    return service.upload_assets(
        item, asset_type="profile", replace_existing=False,
        file_storages=[FileStorage(stream=io.BytesIO(b"sample,value\nS1,1\n"), filename=name)],
    )[0]


def output(app, item, name="profile"):
    _, directory = allocate_result_dir(project_result_parent(item, app.config["RESULTS_FOLDER"]), name)
    (directory / "result.csv").write_text("value\n1\n", encoding="utf-8")
    return directory


def test_internal_storage_username_does_not_change_project_owner(storage):
    app, _, service = storage
    user = User(username="alice", email="alice@example.test", password_hash="unused")
    db.session.add(user); db.session.commit()
    item = project("owned legacy project", user)
    asset = upload(service, item)
    parts = Path(asset.storage_path).relative_to(app.config["PROJECT_DATA_ROOT"]).parts
    assert parts[0] == "zhengqinyun"
    assert re.fullmatch(r"\d{8}_\d{6}__[a-f0-9]{8}", parts[1])
    assert parts[2:] == ("profile", "profile.csv")
    assert asset.metadata_json["storage_user"] == "zhengqinyun"
    assert asset.metadata_json["managed_layout"] == "user-time-v1"
    assert item.user_id == user.id
    app.config["APP_STORAGE_USER"] = "科研账号"
    assert project_upload_parent(item, service.projects_root).name == "科研账号"
    service.delete_asset(asset)
    assert not Path(asset.storage_path).exists()


def test_authenticated_users_have_separate_roots_and_unique_runs(storage):
    app, _, _ = storage
    app.config.update(INTERNAL_MODE=False)
    users = [User(username=name, email=name+"@example.test", password_hash="unused") for name in ("alice", "bob")]
    db.session.add_all(users); db.session.commit()
    items = [project("project " + user.username, user) for user in users]
    paths = [output(app, item) for item in items]
    second = output(app, items[0])
    assert second != paths[0]
    for user, directory in zip(users, paths):
        parts = directory.relative_to(app.config["RESULTS_FOLDER"]).parts
        assert parts[0] == user.username
        assert re.fullmatch(r"\d{8}_\d{6}", parts[1])
        assert parts[2] == "profile"
        assert re.fullmatch(r"profile_[a-f0-9]{12}", parts[3])
        assert len(parts) == 4


def test_project_deletion_uses_registered_files_not_shared_user_directory(storage):
    app, root, service = storage
    first, other = project("delete"), project("preserve")
    first_asset, other_asset = upload(service, first), upload(service, other)
    first_path, other_path = Path(first_asset.storage_path), Path(other_asset.storage_path)
    note = first_path.parent / "operator-note.txt"; note.write_text("preserve")
    first_run, other_run = output(app, first), output(app, other)
    for item, run in ((first, first_run), (other, other_run)):
        service.register_analysis_result(item, analysis_type="profile", job_id=item.id, output_base=str(run))
    failed_run = output(app, first, "volcano")
    db.session.add(AnalysisJob(id="failed-task", project_id=first.id, job_type="script_hub", module="volcano",
        status="failed", payload={"allocated_output_dirs": [str(failed_run)]}))
    db.session.commit()
    # Changing a logical bucket does not make recorded historical paths disappear.
    app.config["APP_STORAGE_USER"] = "new_bucket"
    ProjectService(root / "old-fallback").delete_project(first)
    assert not first_path.exists()
    assert not first_run.exists()
    assert not failed_run.exists()
    assert note.read_text() == "preserve"
    assert other_path.exists() and (other_run / "result.csv").exists()
    assert db.session.get(Project, other.id) is not None


def test_project_deletion_preserves_other_project_imported_result(storage):
    app, root, service = storage
    first, other = project("source"), project("consumer")
    run = output(app, first)
    service.register_analysis_result(first, analysis_type="profile", output_base=str(run))
    service.register_cached_asset(other, asset_type="profile", storage_path=str(run / "result.csv"))
    ProjectService(root / "old-fallback").delete_project(first)
    assert (run / "result.csv").exists()


def test_failed_task_records_all_allocations_after_stale_payload_state_updates(storage):
    app, _, _ = storage
    item = project("failed")
    jobs = get_background_job_service()
    task = jobs.create_job(job_type="script_hub", module="profile", project_id=item.id,
        payload={"config_json": {"chain": "TRB"}})
    task_id = task["job_id"]
    from flask_app.routes.api_script_hub import _common
    _common._script_tasks[task_id] = dict(task)
    try:
        parent = script_output_parent(task_id, app.config["RESULTS_FOLDER"])
        first = allocate_result_dir(parent, "profile")[1]
        second = allocate_result_dir(parent, "profile")[1]
        (first / "partial.csv").write_text("partial")
        _common._set_task_state(task_id, status="running", detail="running")
        _common._set_task_state(task_id, status="failed", error="real failure")
        saved = jobs.get_job(task_id)
        assert saved["payload"]["allocated_output_dirs"] == [str(first), str(second)]
        assert saved["payload"]["config_json"] == {"chain": "TRB"}
        from flask_app.routes.api_jobs import _delete_job_assets_and_paths
        result = _delete_job_assets_and_paths(saved)
        assert not result["errors"]
        assert not first.exists() and not second.exists()
        assert parent.exists()
    finally:
        _common._script_tasks.pop(task_id, None)
        g.pop("analysis_task_id", None)
        g.pop("analysis_allocated_dirs", None)


def test_task_cleanup_preserves_result_imported_by_other_project(storage):
    app, _, service = storage
    first, other = project("source"), project("consumer")
    run = output(app, first)
    jobs = get_background_job_service()
    task = jobs.create_job(job_type="script_hub", module="profile", project_id=first.id)
    jobs.upsert_job(task["job_id"], {"status": "failed", "allocated_output_dirs": [str(run)]})
    service.register_cached_asset(other, asset_type="profile", storage_path=str(run / "result.csv"))
    from flask_app.routes.api_jobs import _delete_job_assets_and_paths
    result = _delete_job_assets_and_paths(jobs.get_job(task["job_id"]))
    assert result["errors"]
    assert (run / "result.csv").exists()


def test_imported_input_in_result_root_is_not_owned_output(storage):
    app, root, service = storage
    item = project("external input")
    run = output(app, item)
    service.register_cached_asset(item, asset_type="profile", storage_path=str(run / "result.csv"))
    ProjectService(root / "old-fallback").delete_project(item)
    assert (run / "result.csv").exists()


@pytest.mark.parametrize("worker_module,function,module", [
    ("analysis", "run_analysis_execute_job", "analysis.execute"),
    ("chord", "run_chord_job", "chord.generate"),
    ("generic", "run_generic_job", "analysis.execute"),
    ("heatmap", "run_heatmap_generate_job", "auto-heatmap.generate-heatmap"),
    ("ppt", "run_ppt_scan_images_job", "ppt.scan-images"),
    ("statistical", "run_statistical_analyze_job", "statistical.analyze"),
    ("treemap", "run_treemap_job", "treemap.generate"),
    ("charts", "run_charts_job", "charts.combined"),
])
def test_generic_workers_journal_partial_outputs_before_failure(storage, monkeypatch, worker_module, function, module):
    from importlib import import_module
    from flask_app.services.api_job_runner import ALLOWED_API_JOBS, call_json_endpoint
    from flask_app.services.project_storage_paths import allocate_report_dir
    from flask_app.routes.api_jobs import _delete_job_assets_and_paths
    app, _, _ = storage
    item, other = project("failed worker"), project("unrelated project")
    sibling = output(app, other)
    jobs = get_background_job_service()
    task = jobs.create_job(job_type="api_request", module=module, project_id=item.id, payload={"input": "preserved"})
    paths = []
    def endpoint():
        for _ in range(2):
            _, directory = allocate_report_dir(app.config["RESULTS_FOLDER"], "partial_analysis")
            paths.append(directory)
            (directory / "partial.csv").write_text("unfinished")
        raise RuntimeError("calculation failed after writing partial output")
    endpoint_module = "analysis.execute" if module == "charts.combined" else module
    app.view_functions[ALLOWED_API_JOBS[endpoint_module]["endpoint"]] = endpoint
    monkeypatch.setattr("flask_app.app.create_app", lambda: app)
    if module == "charts.combined":
        monkeypatch.setattr("flask_app.services.api_job_runner.run_combined_charts_job",
                            lambda context: call_json_endpoint(endpoint_module, {}, None))
    result = getattr(import_module("analysis_workers.tasks." + worker_module), function)(task["job_id"])
    assert result["success"] is False
    saved = jobs.get_job(task["job_id"])
    assert saved["status"] == "failed"
    assert saved["payload"]["allocated_output_dirs"] == list(map(str, paths))
    assert saved["payload"]["input"] == "preserved"
    assert len(paths) == 2 and all(path.relative_to(app.config["RESULTS_FOLDER"]).parts[0] == "zhengqinyun" for path in paths)
    assert not getattr(g, "analysis_task_id", None)
    assert not _delete_job_assets_and_paths(saved)["errors"]
    assert all(not path.exists() for path in paths)
    assert sibling.exists()


def test_threadpool_records_compute_and_result_registration_failures(storage):
    from flask_app.services.project_storage_paths import allocate_report_dir
    from flask_app.routes.api_jobs import _delete_job_assets_and_paths
    app, _, _ = storage
    item = project("threadpool failure")
    jobs = get_background_job_service()
    task = jobs.create_job(job_type="api_request", module="charts.combined", project_id=item.id)
    def calculate(context):
        with app.test_request_context("/worker", json={}):
            _, directory = allocate_report_dir(app.config["RESULTS_FOLDER"], "partial_analysis")
            (directory / "partial.csv").write_text("partial")
        # Real generic result writer allocates a second directory and rejects this image.
        return {"results": {"charts": [{"image": "invalid-base64!"}]}}
    jobs._run(task["job_id"], calculate, (), {})
    saved = jobs.get_job(task["job_id"])
    assert saved["status"] == "failed"
    paths = saved["payload"]["allocated_output_dirs"]
    assert len(paths) == 2
    assert (Path(paths[0]) / "partial.csv").exists()
    assert (Path(paths[1]) / "results.json").exists()
    assert not getattr(g, "analysis_task_id", None)
    assert not _delete_job_assets_and_paths(saved)["errors"]
    assert all(not Path(path).exists() for path in paths)


def test_nested_task_storage_context_restores_parent_and_project(storage):
    from flask_app.services.project_storage_paths import job_storage_context
    app, _, _ = storage
    first, second = project("parent"), project("child")
    jobs = get_background_job_service()
    parent = jobs.create_job(job_type="api_request", module="analysis.execute", project_id=first.id)["job_id"]
    child = jobs.create_job(job_type="api_request", module="analysis.execute", project_id=second.id)["job_id"]
    with job_storage_context(parent):
        assert g.analysis_project_id == first.id
        before = output(app, first)
        with job_storage_context(parent):
            with job_storage_context(child):
                inside = output(app, second)
                assert g.analysis_project_id == second.id
            assert g.analysis_task_id == parent
        after = output(app, first)
    assert jobs.get_job(parent)["payload"]["allocated_output_dirs"] == [str(before), str(after)]
    assert jobs.get_job(child)["payload"]["allocated_output_dirs"] == [str(inside)]
    assert not getattr(g, "analysis_task_id", None)
