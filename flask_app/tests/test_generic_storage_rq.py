"""Real forked RQ worker acceptance for partial generic output ownership."""
import os
import uuid
from pathlib import Path

import pytest


@pytest.mark.skipif(os.environ.get("RUN_GENERIC_STORAGE_RQ") != "1", reason="需显式启用隔离 Redis 任务目录验收")
def test_failed_generic_rq_job_keeps_partial_paths_for_lifecycle_cleanup(tmp_path, monkeypatch):
    from flask import Flask
    from redis import Redis
    from rq import Queue, Worker
    from flask_app.models.database import Project, db
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.project_storage_paths import allocate_report_dir, allocate_result_dir, project_result_parent
    from flask_app.services.api_job_runner import ALLOWED_API_JOBS
    from flask_app.services import persistent_queue
    from flask_app.routes.api_jobs import _delete_job_assets_and_paths
    import flask_app.app as app_module

    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, INTERNAL_MODE=True, APP_STORAGE_USER="科研用户",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{tmp_path / 'rq-jobs.db'}", SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RESULTS_FOLDER=str(tmp_path / "独立 分析结果"), ALLOWED_BASE_PATHS=[str(tmp_path)])
    db.init_app(app)
    service = get_background_job_service()
    monkeypatch.setattr(service, "app", app)
    monkeypatch.setattr(app_module, "app", app)
    monkeypatch.setattr(app_module, "create_app", lambda: app)
    def partial_failure():
        for _ in range(2):
            _, directory = allocate_report_dir(app.config["RESULTS_FOLDER"], "partial_analysis")
            (directory / "partial.csv").write_text("sample,value\n001,1\n", encoding="utf-8")
        raise RuntimeError("synthetic calculation failed after allocating two directories")
    app.view_functions[ALLOWED_API_JOBS["analysis.execute"]["endpoint"]] = partial_failure
    connection = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue("generic-storage-" + uuid.uuid4().hex, connection=connection)
    with app.app_context():
        db.create_all()
        first, other = Project(name="失败任务项目"), Project(name="保留项目")
        db.session.add_all([first, other]); db.session.commit()
        _, sibling = allocate_result_dir(project_result_parent(other, app.config["RESULTS_FOLDER"]), "preserved_analysis")
        (sibling / "result.csv").write_text("preserved")
        task = service.create_job(job_type="api_request", module="analysis.execute", project_id=first.id, payload={"custom_parameter": "retained"})
        rq_task = persistent_queue.enqueue(persistent_queue.execute_api, task["job_id"], "analysis.execute", task["job_id"], queue=queue)
        db.session.remove(); db.engine.dispose()
        try:
            Worker([queue], connection=connection, work_horse_killed_handler=persistent_queue.record_killed).work(burst=True, logging_level="WARNING")
            db.session.remove()
            saved = service.get_job(task["job_id"])
            assert saved["status"] == "failed", saved
            paths = saved["payload"]["allocated_output_dirs"]
            assert len(paths) == 2
            assert saved["payload"]["custom_parameter"] == "retained"
            assert all((Path(path) / "partial.csv").is_file() for path in paths)
            assert all(Path(path).relative_to(app.config["RESULTS_FOLDER"]).parts[0] == "科研用户" for path in paths)
            assert not _delete_job_assets_and_paths(saved)["errors"]
            assert all(not Path(path).exists() for path in paths)
            assert (sibling / "result.csv").read_text() == "preserved"
        finally:
            rq_task.delete()
            queue.delete()
            db.session.remove(); db.drop_all()
