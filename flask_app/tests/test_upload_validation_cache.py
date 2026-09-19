import io
from unittest.mock import patch
import pytest
from werkzeug.datastructures import FileStorage
from flask_app.app import create_app
from flask_app.models.database import Project, User, db
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.services.input_quality import inspect_input_quality, validate_analysis_inputs
from flask_app.services.project_storage_paths import allocate_result_dir
from flask_app.exceptions import ValidationError

@pytest.fixture
def context(tmp_path):
    app = create_app("testing")
    app.config.update(REQUIRE_LOGIN=False, RESULTS_FOLDER=tmp_path / "results")
    with app.app_context():
        user = User(username="alice", email="alice@example.org", password_hash="unused")
        db.session.add(user); db.session.flush()
        project = Project(name="sample", user_id=user.id)
        db.session.add(project); db.session.commit()
        yield ProjectAssetService(tmp_path / "data"), project
        db.session.remove(); db.drop_all()

def upload(service, project, kind, content, filename):
    return service.upload_assets(project, asset_type=kind, file_storages=[FileStorage(stream=io.BytesIO(content), filename=filename)])[0]

def test_upload_validation_reused_without_full_scan_and_external_change_rejected(context):
    service, project = context
    asset = upload(service, project, "profile", b"sample,group\nS1,A\nS2,B\n", "profile.csv")
    assert "/alice/" in asset.storage_path
    assert asset.metadata_json["validation"]["status"] == "valid"
    with patch("flask_app.services.input_quality._inspect_input_quality", side_effect=AssertionError("full scan")) as scan:
        # Empty PEP discovery is lightweight; only full table scans are forbidden.
        from flask_app.services.input_validation_cache import cached_validation
        result = cached_validation(asset.storage_path, "profile", lambda: scan())
        assert result["inputs"][0]["sample_count"] == 2
        assert scan.call_count == 0
    from pathlib import Path
    Path(asset.storage_path).write_text("sample,group\nS1,B\nS2,A\n")
    with pytest.raises(ValidationError, match="平台外"):
        inspect_input_quality([], asset.storage_path, "", "")

def test_pep_content_and_profile_duplicates_are_saved(context):
    service, project = context
    bad = upload(service, project, "pep", b"CDR3(pep),V,J,copy\nAAA,V1,J1,no\n", "S1_TRA.csv")
    assert bad.metadata_json["validation"]["status"] == "invalid"
    with pytest.raises(ValidationError, match="检查未通过"):
        validate_analysis_inputs([{"asset_type":"pep", "path":bad.storage_path}])
    duplicate = upload(service, project, "profile", b"sample,group\nS1,A\nS1,B\n", "profile.csv")
    assert duplicate.metadata_json["validation"]["status"] == "invalid"

def test_result_runs_are_independent_and_missing_output_rejected(context):
    service, project = context
    from flask import current_app
    parent = current_app.config["RESULTS_FOLDER"] / "alice" / project.id
    first_id, first_dir = allocate_result_dir(parent, "profile")
    second_id, second_dir = allocate_result_dir(parent, "profile")
    assert first_dir != second_dir
    for path in [first_dir, second_dir]: (path / "table.csv").write_text("value\n1\n")
    a = service.register_analysis_result(project, analysis_type="profile", job_id=first_id, output_base=str(first_dir), metadata={"analysis_signature":"same"})
    b = service.register_analysis_result(project, analysis_type="profile", job_id=second_id, output_base=str(second_dir), metadata={"analysis_signature":"same"})
    assert a.id != b.id
    assert a.metadata_json["job_id"] == first_id
    assert a.size > 0 and a.metadata_json["result_files"]
    assert service.register_analysis_result(project, analysis_type="profile", job_id=first_id, output_base=str(first_dir)).id == a.id
    with pytest.raises(ValidationError, match="不存在"):
        service.register_analysis_result(project, analysis_type="profile", job_id="missing", output_base=str(parent / "missing"))


def test_queued_validation_does_not_start_a_second_scan(context):
    from flask_app.models.database import AnalysisJob
    from flask_app.services.input_validation_cache import cached_validation
    service, project = context
    asset = upload(service, project, "profile", b"sample,group\nS1,A\n", "profile.csv")
    job = AnalysisJob(id="pending-validation", job_type="input_validation", module="input-validation", status="queued", user_id=project.user_id, project_id=project.id)
    db.session.add(job)
    asset.metadata_json = {**asset.metadata_json, "validation_job_id":job.id}
    db.session.commit()
    with patch("flask_app.services.input_quality._inspect_input_quality", side_effect=AssertionError("duplicate scan")) as scan:
        result = cached_validation(asset.storage_path, "profile", scan)
        assert result["inputs"][0]["status"] == "pending"
        scan.assert_not_called()
