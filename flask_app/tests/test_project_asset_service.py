"""Tests for project asset deletion behavior."""

from pathlib import Path
import sys

from flask import Flask
import pytest
from werkzeug.datastructures import FileStorage

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parents[1]
for import_dir in (APP_DIR, ROOT_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))

try:
    from flask_app.models.database import Project, ProjectAsset, db
    from flask_app.services.project_asset_service import ProjectAssetService
except ModuleNotFoundError:
    from models.database import Project, ProjectAsset, db
    from services.project_asset_service import ProjectAssetService


@pytest.fixture
def app_context(tmp_path):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    with app.app_context():
        db.create_all()
        yield tmp_path
        db.session.remove()
        db.drop_all()


def _create_project(name="Deletion Test"):
    project = Project(name=name)
    db.session.add(project)
    db.session.commit()
    return project


def test_delete_asset_removes_external_path_record_without_deleting_source(app_context):
    project = _create_project()
    service = ProjectAssetService(app_context / "projects")
    external_dir = app_context / "external-source"
    external_dir.mkdir()

    asset = ProjectAsset(
        project_id=project.id,
        asset_type="pep",
        original_name="external-source",
        storage_path=str(external_dir),
        size=0,
    )
    db.session.add(asset)
    db.session.commit()
    asset_id = asset.id

    service.delete_asset(asset)

    assert external_dir.exists()
    assert db.session.get(ProjectAsset, asset_id) is None


def test_delete_asset_removes_managed_directory(app_context):
    project = _create_project()
    service = ProjectAssetService(app_context / "projects")
    managed_dir = service.get_asset_dir(project, "pep") / "sample-a"
    managed_dir.mkdir(parents=True)
    (managed_dir / "TRA.csv").write_text("cdr3\nAAA\n", encoding="utf-8")

    asset = ProjectAsset(
        project_id=project.id,
        asset_type="pep",
        original_name="sample-a",
        storage_path=str(managed_dir),
        size=0,
    )
    db.session.add(asset)
    db.session.commit()

    service.delete_asset(asset)

    assert not managed_dir.exists()


def test_register_profile_does_not_reuse_datapoint_path(app_context):
    project = _create_project("Profile Only")
    service = ProjectAssetService(app_context / "projects")
    profile_path = app_context / "Profile_All.csv"
    profile_path.write_text("sample,disease\nS1,A\n", encoding="utf-8")

    first = service.register_cached_asset(
        project,
        asset_type="datapoint",
        storage_path=str(profile_path),
        original_name="Profile_All.csv",
        metadata={"source": "legacy"},
    )
    second = service.register_cached_asset(
        project,
        asset_type="profile",
        storage_path=str(profile_path),
        original_name="Profile_All.csv",
        metadata={"source": "script-hub"},
    )

    assets = ProjectAsset.query.filter(
        ProjectAsset.project_id == project.id,
        ProjectAsset.storage_path == str(profile_path),
    ).order_by(ProjectAsset.asset_type).all()
    assert first.id != second.id
    assert len(assets) == 2
    assert [asset.asset_type for asset in assets] == ["datapoint", "profile"]
    assert assets[0].metadata_json["source"] == "legacy"
    assert assets[1].metadata_json["source"] == "script-hub"


def test_upload_asset_records_storage_uri(app_context):
    project = _create_project("Storage URI Upload")
    service = ProjectAssetService(app_context / "projects")
    source = app_context / "upload.csv"
    source.write_text("sample,value\nS1,1\n", encoding="utf-8")

    with source.open("rb") as stream:
        assets = service.upload_assets(
            project,
            asset_type="profile",
            file_storages=[FileStorage(stream=stream, filename="upload.csv")],
            relative_paths=["upload.csv"],
        )

    storage_uri = assets[0].metadata_json.get("storage_uri")
    assert storage_uri.startswith("local:///")
    assert "upload.csv" in storage_uri


def test_register_cached_asset_records_storage_uri(app_context):
    project = _create_project("Storage URI Register")
    service = ProjectAssetService(app_context / "projects")
    profile_path = app_context / "Profile_All.csv"
    profile_path.write_text("sample,disease\nS1,A\n", encoding="utf-8")

    asset = service.register_cached_asset(
        project,
        asset_type="profile",
        storage_path=str(profile_path),
        original_name="Profile_All.csv",
        metadata={"source": "script-hub"},
    )

    assert asset.metadata_json["source"] == "script-hub"
    assert asset.metadata_json["storage_uri"].startswith("local:///")
