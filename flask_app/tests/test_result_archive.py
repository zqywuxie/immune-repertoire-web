import io
import zipfile
import pytest
from flask import Flask, send_file
from flask_app.models.database import db
from flask_app.routes.api_jobs import jobs_bp
from flask_app.services.background_job_service import get_background_job_service


@pytest.fixture
def app(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app); app.register_blueprint(jobs_bp)
    @app.get("/api/script-hub/results/<report>/<name>")
    def file(report, name):
        path = tmp_path / report / name
        if not path.is_file(): return "missing", 404
        return send_file(path)
    @app.get("/api/assets/asset/download")
    def asset_download():
        return send_file(tmp_path / "first" / "表.csv", as_attachment=True, download_name="样本结果.csv")
    with app.app_context():
        db.create_all()
        service = get_background_job_service()
        for report in ("first", "second"):
            folder = tmp_path / report; folder.mkdir()
            (folder / "表.csv").write_text("样本,值\n001,1.000000001\n", encoding="utf-8")
            job = service.create_job(job_type="script_hub", module="profile", user_id=7)
            service.complete_job(job["job_id"], {"csv_urls": [f"/api/script-hub/results/{report}/表.csv", f"/api/script-hub/results/{report}/missing.csv"]})
            app.config[report] = job["job_id"]
        yield app
        db.session.remove(); db.drop_all()


def item(app, report="first", name="表.csv"):
    return {"job_id": app.config[report], "url": f"/api/script-hub/results/{report}/{name}"}


def test_archive_contains_both_tasks_without_duplicate_selection(app):
    first, second = item(app), item(app, "second")
    response = app.test_client().post("/api/jobs/results/archive", json={"items": [first, second, first]})
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert len(archive.namelist()) == 2
        assert len({name.split('/')[0] for name in archive.namelist()}) == 2
        assert all(archive.read(name).decode('utf-8') == "样本,值\n001,1.000000001\n" for name in archive.namelist())
    response.close()


def test_rejects_file_from_another_task_and_missing_files(app):
    wrong = {**item(app), "url": item(app, "second")["url"]}
    client = app.test_client()
    assert client.post("/api/jobs/results/archive", json={"items": [wrong]}).status_code == 400
    response = client.post("/api/jobs/results/archive", json={"items": [item(app), item(app, name="missing.csv")]})
    assert response.status_code == 409 and response.is_json


def test_ownership_checked_before_reading_file(app, monkeypatch):
    import flask_app.routes.api_jobs as api
    app.config["REQUIRE_LOGIN"] = True
    monkeypatch.setattr(api, "current_user_id", lambda: 8)
    monkeypatch.setattr(api, "is_admin", lambda: False)
    assert app.test_client().post("/api/jobs/results/archive", json={"items": [item(app)]}).status_code == 404


def test_empty_selection_and_size_limit(app):
    client = app.test_client()
    assert client.post("/api/jobs/results/archive", json={"items": []}).status_code == 400
    app.config["RESULT_ARCHIVE_MAX_BYTES"] = 3
    response = client.post("/api/jobs/results/archive", json={"items": [item(app)]})
    assert response.status_code == 413 and response.is_json


def test_asset_download_preserves_original_filename(app):
    job_id = app.config["first"]
    url = "/api/assets/asset/download"
    get_background_job_service().upsert_job(job_id, {"result": {"csv_urls": [url]}})
    response = app.test_client().post("/api/jobs/results/archive", json={"items": [{"job_id": job_id, "url": url}]})
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.data)) as bundle:
        assert bundle.namelist()[0].endswith("样本结果.csv")
    response.close()
