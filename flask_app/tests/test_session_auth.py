"""Real session boundaries using an isolated SQLite database."""
import pytest
from flask_app.app import create_app
from flask_app.models.database import db, User, Project
from flask_app.services.user_scope import scope_query, assert_owned
from flask_app.exceptions import ValidationError

@pytest.fixture
def app():
    app = create_app("testing")
    app.config.update(REQUIRE_LOGIN=True, LOGIN_DISABLED=False, AUTH_REGISTER_ENABLED=True, SECRET_KEY="session-test-only")
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()

def post(client, route, data=None):
    token = client.get("/api/auth/options").get_json()["csrf_token"]
    return client.post("/api/auth/" + route, json=data or {}, headers={"X-CSRF-Token": token})

def account(username="alice"):
    return dict(username=username, email=username + "@example.org", password="test-password", confirm_password="test-password")

def test_register_login_logout_and_cookie_identity(app):
    client = app.test_client()
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/register", json=account()).status_code == 403
    created = post(client, "register", account())
    assert created.status_code == 200
    assert created.json["user"]["role"] == "user"
    assert client.get("/api/auth/me").json["username"] == "alice"
    assert client.get("/api/auth/logout").status_code == 405
    assert post(client, "logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert post(client, "login", dict(username="alice", password="wrong")).status_code == 401
    assert post(client, "login", dict(username="alice", password="test-password")).status_code == 200
    with app.app_context():
        user = User.query.one()
        assert user.password_hash != "test-password"
        user.is_active_flag = False
        db.session.commit()
    assert client.get("/api/auth/me").status_code == 401

@pytest.mark.parametrize("change", [dict(username="../escape"), dict(username="a/b"), dict(password="short"), dict(confirm_password="mismatch"), dict(email="invalid")])
def test_reject_invalid_registration(app, change):
    client = app.test_client()
    assert post(client, "register", {**account(), **change}).status_code == 400

def test_duplicate_closed_registration_and_old_form_disabled(app):
    client = app.test_client()
    assert post(client, "register", account()).status_code == 200
    post(client, "logout")
    assert post(client, "register", account()).status_code == 409
    app.config["AUTH_REGISTER_ENABLED"] = False
    assert post(client, "register", account("bob")).status_code == 403
    assert client.post("/auth/register", data=account("bob")).status_code == 405
    assert client.get("/auth/login?next=//evil.example").location == "/login"

def test_two_users_and_admin_are_scoped(app):
    alice, bob = app.test_client(), app.test_client()
    aid = post(alice, "register", account()).json["user"]["user_id"]
    bid = post(bob, "register", account("bob")).json["user"]["user_id"]
    with app.app_context():
        db.session.add(Project(id="alice-project", name="private", user_id=aid))
        db.session.add(Project(id="unowned-project", name="legacy", user_id=None))
        db.session.get(User, bid).role = "admin"
        db.session.commit()
    with bob:
        bob.get("/api/auth/me")
        assert scope_query(Project.query, Project).count() == 0
        with pytest.raises(ValidationError): assert_owned(db.session.get(Project, "alice-project"))
    assert alice.get("/api/projects/alice-project").status_code == 200
    assert bob.get("/api/projects/alice-project").status_code in {400, 403, 404}


def test_real_profile_run_upload_results_and_cross_user_denial(app, tmp_path, monkeypatch):
    import io
    from pathlib import Path
    from flask_app.routes.api_script_hub import profile_analysis
    from flask_app.services.background_job_service import get_background_job_service
    app.config.update(PROJECT_DATA_ROOT=str(tmp_path / "data"), RESULTS_FOLDER=tmp_path / "results")
    # Keep the calculation and SQL registration real; the optional Mongo cache is isolated.
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kwargs: "isolated-cache")
    class InlineExecutor:
        def submit(self, function, task_id, **kwargs): function(task_id, **kwargs)
    monkeypatch.setattr(profile_analysis, "_script_executor", InlineExecutor())
    alice, bob = app.test_client(), app.test_client()
    post(alice, "register", account())
    post(bob, "register", account("bob"))
    created = alice.post("/api/projects", json={"name": "科研项目"})
    assert created.status_code == 201, created.json
    project_id = created.json["id"]
    content = b"sample,group,metric\nA1,A,1\nA2,A,2\nA3,A,3\nB1,B,8\nB2,B,9\nB3,B,10\n"
    uploaded = alice.post(f"/api/projects/{project_id}/assets", data={"asset_type":"profile", "asset_set":"Set1", "files":(io.BytesIO(content), "profile.csv")})
    assert uploaded.status_code == 201, uploaded.json
    asset_id = uploaded.json["assets"][0]["id"]
    assert bob.get(f"/api/assets/{asset_id}/download").status_code in {400,403,404}
    request_data = {"project_id":project_id,"asset_set":"Set1","grouptype_fields":["group"],"param_begin":"metric","param_over":"metric","force_rerun":True}
    submitted = alice.post("/api/script-hub/profile/run", json=request_data)
    assert submitted.status_code == 200, submitted.json
    task_id = submitted.json["task_id"]
    task = alice.get(f"/api/script-hub/task/{task_id}")
    assert task.json["status"] == "completed", task.json
    output = Path(task.json["result"]["output_base"])
    assert output.parent == tmp_path / "results" / "alice" / project_id
    url = task.json["result"]["viewer_url"]
    assert alice.get(url).status_code == 200
    assert bob.get(url).status_code in {400,403,404}
    assert bob.get(f"/api/script-hub/task/{task_id}").status_code == 404
    assert alice.post("/api/projects", json={"name":"cross-site"}, headers={"Origin":"https://other.example"}).status_code == 403


def test_project_profile_reused_by_unified_analysis_and_persisted(app, tmp_path):
    import io
    from pathlib import Path
    from flask_app.services.api_job_runner import call_json_endpoint
    from flask_app.services.background_job_service import get_background_job_service
    app.config.update(PROJECT_DATA_ROOT=str(tmp_path / "data"), RESULTS_FOLDER=tmp_path / "results")
    alice, bob = app.test_client(), app.test_client()
    uid = post(alice, "register", account()).json["user"]["user_id"]
    post(bob, "register", account("bob"))
    pid = alice.post("/api/projects", json={"name":"测序量项目"}).json["id"]
    upload = alice.post(f"/api/projects/{pid}/assets", data={"asset_type":"profile", "files":(io.BytesIO(b"sample,TRA_reads\nS1,12\nS2,24\n"),"profile.csv")})
    assert upload.status_code == 201, upload.json
    asset_id = upload.json["assets"][0]["id"]
    files = alice.get(f"/api/files?project={pid}")
    assert files.status_code == 200, files.json
    assert files.json["files"][0]["columns"] == ["sample", "TRA_reads"]
    assert bob.get(f"/api/files?project={pid}").status_code in {400,403,404}
    with app.app_context():
        service = get_background_job_service()
        payload = {"project_id":pid, "file_id":asset_id, "mode":"scheme", "scheme_id":"sequencing_reads_chart", "field_mapping":{"Sample":"sample"}, "parameters":{"chains":["TRA"],"chart_config":{"figsize":[5,4],"dpi":60}}}
        outputs = []
        for _ in range(2):
            job = service.create_job(job_type="analysis", module="analysis.execute-unified", user_id=uid, project_id=pid, payload=payload)
            result = call_json_endpoint("analysis.execute-unified", payload, uid)
            assert result["success"], result
            completed = service.complete_job(job["id"], result)
            result = completed["result"]
            output = Path(result["output_base"])
            assert output.parent == tmp_path / "results" / "alice" / pid
            assert (output / "chart_1.png").is_file()
            assert (output / "results.zip").is_file()
            outputs.append(output)
        assert outputs[0] != outputs[1]
    # Each HTTP request gets its own application context and session identity.
    assert alice.get(result["viewer_url"]).status_code == 200
    assert alice.get(result["zip_url"]).status_code == 200
    assert bob.get(result["zip_url"]).status_code in {400,403,404}


def test_heatmap_report_and_reuse_keep_project_paths_and_references(app, tmp_path):
    from flask_login import login_user
    from flask_app.models.database import AnalysisJob
    from flask_app.services.similarity_heatmap_report_service import SimilarityHeatmapReportService
    from flask_app.services.project_storage_paths import register_report, register_reused_result
    from flask_app.routes.api_jobs import _delete_job_assets_and_paths
    app.config.update(PROJECT_DATA_ROOT=str(tmp_path / "data"), RESULTS_FOLDER=tmp_path / "results")
    alice, bob = app.test_client(), app.test_client()
    uid = post(alice, "register", account()).json["user"]["user_id"]
    post(bob, "register", account("bob"))
    pid = alice.post("/api/projects", json={"name":"热图项目"}).json["id"]
    with app.test_request_context("/api/reports", method="POST", json={"project_id":pid}):
        login_user(db.session.get(User, uid))
        project = db.session.get(Project, pid)
        service = SimilarityHeatmapReportService(tmp_path / "results")
        report = service.generate_report({"mode":"traditional", "metrics":{"sorensen":{"matrix_data":{"samples":["S1","S2"], "values":[[1,0.5],[0.5,1]]}}}})
        assert report.output_base.parent.parent == tmp_path / "results" / "alice" / pid
        assert service.create_archive(report.job_id).is_file()
        asset = register_report(project, "heatmap", report, "", "")
        asset_id = asset.id
        source = {"job_id":report.job_id,"output_base":str(report.output_base)}
        reused = register_reused_result(pid, "heatmap", "reused-task", source)
        assert reused["output_base"] != source["output_base"]
        db.session.add(AnalysisJob(id="reused-task", job_type="script_hub", module="heatmap", status="completed", project_id=pid, user_id=uid, result=reused))
        db.session.commit()
        cleanup = _delete_job_assets_and_paths({"job_id":report.job_id,"project_id":pid,"user_id":uid,"result":source})
        assert not cleanup["deleted_paths"]
        assert cleanup["errors"] and report.report_path.is_file()
    assert alice.get(f"/api/assets/{asset_id}/download").status_code == 200
    assert bob.get(f"/api/assets/{asset_id}/download").status_code in {400,403,404}


def test_six_character_password_is_accepted(app):
    client = app.test_client()
    assert post(client, "register", {**account(), "password":"abc123", "confirm_password":"abc123"}).status_code == 200
    post(client, "logout")
    assert post(client, "login", {"username":"alice", "password":"abc123"}).status_code == 200
