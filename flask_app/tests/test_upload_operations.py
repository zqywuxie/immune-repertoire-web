import io
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager
from werkzeug.datastructures import FileStorage

from flask_app.exceptions import ValidationError
from flask_app.models.database import Project, ProjectAsset, db
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.tests.test_data_management_contracts import context, upload


def files(*names):
    return [FileStorage(stream=io.BytesIO(b'sample,value\n001,1\n'), filename=name) for name in names]


def test_response_lost_retry_keeps_one_asset_and_one_replacement(context):
    app, service, project = context
    old = upload(service, project)
    expected = service.replacement_identities(project.id, 'profile', '甲', {'指标.csv'})
    operation = str(uuid.uuid4())
    endpoint = f'/api/projects/{project.id}/assets'
    def request():
        return app.test_client().post(endpoint, data={
            'operation_id': operation, 'asset_type': 'profile', 'asset_set': '甲',
            'replace_existing': 'true', 'expected_versions': json.dumps(expected), 'files': (io.BytesIO(b'sample,value\n001,2\n'), '指标.csv'),
        })
    # First response is deliberately ignored, as happens after a network disconnect.
    first = request()
    second = request()
    assert first.status_code == second.status_code == 201
    identifier = first.json['assets'][0]['id']
    assert second.json['assets'][0]['id'] == identifier
    assert ProjectAsset.query.count() == 2
    assert old.metadata_json['superseded_by'] == [identifier]
    assert Path(old.storage_path).read_bytes() == b'sample,value\n001,1\n'
    status = app.test_client().get(f'/api/projects/{project.id}/upload-operations/{operation}')
    assert status.json['saved'] is True
    assert [asset['id'] for asset in status.json['assets']] == [identifier]


def test_operation_manifest_and_project_scope(context):
    app, service, project = context
    operation = str(uuid.uuid4())
    a = service.upload_assets(project, asset_type='profile', file_storages=files('指标.csv'),
                              metadata={'asset_set': '甲'}, operation_id=operation)
    with pytest.raises(ValidationError, match='本次选择与原上传操作不同'):
        service.upload_assets(project, asset_type='profile', file_storages=files('指标.csv'),
                              metadata={'asset_set': '乙'}, operation_id=operation)
    other = Project(name='另一个项目')
    db.session.add(other)
    db.session.commit()
    assert service.saved_upload_operation(other.id, operation) == []
    b = service.upload_assets(other, asset_type='profile', file_storages=files('指标.csv'),
                              metadata={'asset_set': '甲'}, operation_id=operation)
    assert a[0].id != b[0].id
    assert app.test_client().get(f'/api/projects/{project.id}/upload-operations/{uuid.uuid4()}').json == {'saved': False, 'assets': []}


def test_multi_file_operation_replays_complete_original_order(context):
    _, service, project = context
    operation = str(uuid.uuid4())
    first = service.upload_assets(project, asset_type='pep', file_storages=files('a.csv', 'b.csv'), operation_id=operation)
    replay = service.upload_assets(project, asset_type='pep', file_storages=files('a.csv', 'b.csv'), operation_id=operation)
    assert [asset.id for asset in first] == [asset.id for asset in replay]
    assert ProjectAsset.query.count() == 2
    service.delete_asset(first[1])
    with pytest.raises(ValidationError, match='部分文件已移除'):
        service.saved_upload_operation(project.id, operation)


def test_failed_operation_rolls_back_and_can_retry(context):
    _, service, project = context
    operation = str(uuid.uuid4())
    broken = files('a.csv') + [FileStorage(stream=io.BytesIO(b''), filename='b.csv')]
    with pytest.raises(ValidationError, match='文件为空'):
        service.upload_assets(project, asset_type='pep', file_storages=broken, operation_id=operation)
    assert service.saved_upload_operation(project.id, operation) == []
    saved = service.upload_assets(project, asset_type='pep', file_storages=files('a.csv', 'b.csv'), operation_id=operation)
    assert len(saved) == ProjectAsset.query.count() == 2


def test_path_registration_retry_does_not_change_another_scope(context):
    app, service, project = context
    directory = service.projects_root / '合成克隆目录'
    directory.mkdir()
    operation = str(uuid.uuid4())
    endpoint = f'/api/projects/{project.id}/assets/register'
    payload = {'operation_id': operation, 'asset_type': 'pep', 'storage_path': str(directory),
               'metadata_json': {'asset_set': '甲'}}
    first = app.test_client().post(endpoint, json=payload)
    again = app.test_client().post(endpoint, json=payload)
    assert first.status_code == again.status_code == 201
    assert first.json['id'] == again.json['id']
    second = app.test_client().post(endpoint, json={**payload, 'operation_id': str(uuid.uuid4()),
                                                   'metadata_json': {'asset_set': '乙'}})
    assert second.status_code == 201
    assert second.json['id'] != first.json['id']
    assert db.session.get(ProjectAsset, first.json['id']).metadata_json['asset_set'] == '甲'
    assert service.saved_upload_operation(project.id, operation)[0].id == first.json['id']


@pytest.mark.parametrize('operation', ['bad-id', 'x' * 200])
def test_invalid_operation_is_rejected_without_saving(context, operation):
    app, _, project = context
    response = app.test_client().post(f'/api/projects/{project.id}/assets', data={
        'asset_type': 'profile', 'operation_id': operation,
        'files': (io.BytesIO(b'sample,value\n001,1\n'), '指标.csv')})
    assert response.status_code == 400
    assert ProjectAsset.query.count() == 0


@pytest.mark.parametrize("mode", ["files", "path"])
def test_concurrent_retries_publish_one_batch(tmp_path, monkeypatch, mode):
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SECRET_KEY='synthetic-upload-race',
        SQLALCHEMY_DATABASE_URI=os.environ.get('TEST_UPLOAD_DATABASE_URI', f'sqlite:///{tmp_path / "race.sqlite"}'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False, PROJECT_DATA_ROOT=str(tmp_path), FILE_BROWSER_ROOT=str(tmp_path))
    db.init_app(app)
    LoginManager(app).user_loader(lambda _: None)
    service = ProjectAssetService(tmp_path / 'projects')
    with app.app_context():
        db.create_all()
        project = Project(name='并发上传合成项目')
        db.session.add(project)
        db.session.commit()
        project_id = project.id
    barrier = Barrier(2)
    original = service.saved_upload_operation
    def simultaneous_lookup(project_id, operation_id, manifest=None):
        result = original(project_id, operation_id, manifest)
        if manifest is not None and not result:
            barrier.wait(timeout=15)
        return result
    monkeypatch.setattr(service, 'saved_upload_operation', simultaneous_lookup)
    directory = tmp_path / 'external-pep'
    directory.mkdir()
    operation = str(uuid.uuid4())
    def submit(_):
        with app.app_context():
            project = db.session.get(Project, project_id)
            if mode == 'path':
                asset = service.register_cached_asset(project, asset_type='pep', storage_path=str(directory),
                    metadata={'asset_set': '甲'}, operation_id=operation)
            else:
                asset = service.upload_assets(project, asset_type='profile', file_storages=files('指标.csv'),
                    metadata={'asset_set': '甲'}, operation_id=operation)[0]
            return asset.id, asset.storage_path
    with patch('flask_app.services.input_validation_cache.schedule_uploaded_validation'):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
    assert results[0] == results[1]
    with app.app_context():
        assets = ProjectAsset.query.filter_by(project_id=project_id).all()
        assert len(assets) == 1
        if mode == 'files':
            assert Path(assets[0].storage_path).read_bytes() == b'sample,value\n001,1\n'
            # The losing request must remove only its own upload batch.
            assert len(list(Path(assets[0].storage_path).parent.parent.parent.glob('*/profile/指标.csv'))) == 1
        else:
            assert Path(assets[0].storage_path) == directory
        db.session.delete(assets[0])
        db.session.delete(db.session.get(Project, project_id))
        db.session.commit()
        db.session.remove()
