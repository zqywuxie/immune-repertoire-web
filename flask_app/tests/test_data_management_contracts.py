"""Data management contracts against small isolated SQLite and synthetic files."""
import io
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager
from werkzeug.datastructures import FileStorage

from flask_app.services.input_validation_cache import schedule_uploaded_validation as actual_schedule_validation
from flask_app.exceptions import AppException, AnalysisInProgressError, ValidationError
from flask_app.models.database import AnalysisJob, Project, ProjectAsset, SampleRecord, User, db
from flask_app.routes import api_projects
REAL_MERGE_MONGO_RESULTS = api_projects._merge_mongo_results
from flask_app.services.mongo_service import get_projects_results as REAL_PROJECTS_RESULTS
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.services.project_service import ProjectService


@pytest.fixture
def context(tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SECRET_KEY='synthetic-tests',
                      SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      PROJECT_DATA_ROOT=str(tmp_path), FILE_BROWSER_ROOT=str(tmp_path))
    db.init_app(app)
    login = LoginManager(app)
    login.user_loader(lambda identifier: db.session.get(User, int(identifier)))
    service = ProjectAssetService(tmp_path / 'projects')
    monkeypatch.setattr(api_projects, '_asset_service', lambda: service)
    monkeypatch.setattr(api_projects, '_project_service', lambda: ProjectService(tmp_path / 'projects'))
    monkeypatch.setattr(api_projects, '_merge_mongo_results', lambda identifier, assets, **kwargs: assets)
    monkeypatch.setattr('flask_app.services.mongo_service.get_projects_results', lambda *args, **kwargs: [])
    monkeypatch.setattr('flask_app.services.mongo_service.get_project_results', lambda *args, **kwargs: [])
    app.register_blueprint(api_projects.project_api_bp)
    app.register_error_handler(AppException, lambda error: (error.to_dict(), error.http_status))
    with app.app_context():
        db.create_all()
        project = Project(name='合成项目')
        db.session.add(project)
        db.session.commit()
        # Keep upload tests independent of scientific validators and queue availability.
        with patch('flask_app.services.input_validation_cache.schedule_uploaded_validation'), patch(
            'flask_app.services.input_validation_cache.validate_uploaded_asset',
            return_value={'inputs': [{'kind': 'profile', 'status': 'checked', 'samples': ['001']}], 'errors': []},
        ):
            yield app, service, project
        db.session.remove()
        db.drop_all()


def upload(service, project, dataset='甲', content=b'sample,value\n001,1\n', replace=False):
    return service.upload_assets(project, asset_type='profile',
                                  file_storages=[FileStorage(stream=io.BytesIO(content), filename='指标.csv')],
                                  metadata={'asset_set': dataset}, replace_existing=replace)[0]


def test_replacement_is_dataset_scoped_and_keeps_historical_bytes(context):
    _, service, project = context
    a, b = upload(service, project), upload(service, project, '乙')
    replaced = upload(service, project, content=b'sample,value\n001,2\n', replace=True)
    assert {asset.id for asset in service.list_assets(project.id)} == {b.id, replaced.id}
    assert a.metadata_json['superseded_by'] == [replaced.id]
    assert Path(a.storage_path).read_bytes() == b'sample,value\n001,1\n'
    assert Path(b.storage_path).read_bytes() == b'sample,value\n001,1\n'
    assert db.session.get(ProjectAsset, a.id) is not None


def test_failed_replacement_preserves_old_file_and_selection(context):
    _, service, project = context
    old = upload(service, project)
    with patch('flask_app.services.input_validation_cache.validate_uploaded_asset', return_value={'errors': ['坏数据']}):
        with pytest.raises(ValidationError, match='原版本已保留'):
            upload(service, project, replace=True)
    assert service.list_assets(project.id) == [old]
    assert Path(old.storage_path).read_bytes() == b'sample,value\n001,1\n'
    assert not old.metadata_json.get('superseded')
    assert len([item for item in Path(old.storage_path).parents[2].rglob('*') if item.is_file()]) == 1


def test_empty_replacement_is_rejected_before_retiring_old(context):
    _, service, project = context
    old = upload(service, project)
    with pytest.raises(ValidationError, match='文件为空'):
        upload(service, project, content=b'', replace=True)
    assert service.list_assets(project.id) == [old]
    assert Path(old.storage_path).is_file()


@pytest.mark.parametrize('status', ['queued', 'running', 'completed'])
def test_referenced_input_cannot_be_physically_deleted(context, status):
    _, service, project = context
    asset = upload(service, project)
    db.session.add(AnalysisJob(job_type='script_hub', module='profile', project_id=project.id,
                               status=status, payload={'config': {'profile_path': asset.storage_path}}))
    db.session.commit()
    with pytest.raises(AnalysisInProgressError, match='任务引用'):
        service.delete_asset(asset)
    assert Path(asset.storage_path).is_file()


def test_metadata_patch_preserves_validation_and_rejects_system_changes(context):
    app, service, project = context
    asset = upload(service, project)
    version = asset.metadata_json['content_version']
    url = f'/api/projects/{project.id}/assets/{asset.id}'
    client = app.test_client()
    response = client.patch(url, json={'metadata_json': {'asset_set': '乙'}})
    assert response.status_code == 200
    assert response.json['asset']['metadata']['content_version'] == version
    assert response.json['asset']['metadata']['asset_set'] == '乙'
    response = client.patch(url, json={'metadata_json': {'content_version': 'fake'}})
    assert response.status_code == 400
    assert asset.metadata_json['content_version'] == version


def test_input_pages_are_complete_and_exclude_results(context):
    app, _, project = context
    for index in range(251):
        db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=f'{index}.csv',
                                     storage_path=f'/tmp/{index}.csv', size=1, metadata_json={'asset_set': '完整'}))
    for index in range(210):
        db.session.add(ProjectAsset(project_id=project.id, asset_type='processed_result', original_name=f'结果{index}',
                                     storage_path=f'/tmp/results/{index}', size=1))
    db.session.commit()
    client = app.test_client()
    first = client.get(f'/api/projects/{project.id}/assets?inputs_only=true&page_size=200').json
    second = client.get(f'/api/projects/{project.id}/assets?inputs_only=true&page_size=200&page=2').json
    assert first['pagination']['total'] == second['pagination']['total'] == 251
    assert len(first['assets']) == 200 and len(second['assets']) == 51
    assert len({asset['id'] for asset in first['assets'] + second['assets']}) == 251


def test_group_specs_use_stable_id_and_do_not_collide_for_chinese_names(context):
    app, _, project = context
    client = app.test_client()
    url = f'/api/projects/{project.id}/group-specs'
    first = client.post(url, json={'name': '方案甲', 'spec_json': {'groups': ['健康', '疾病']}})
    second = client.post(url, json={'name': '方案乙', 'spec_json': {'groups': ['前', '后']}})
    assert first.status_code == second.status_code == 201
    assert first.json['asset']['storage_path'] != second.json['asset']['storage_path']
    specs = client.get(url).json['group_specs']
    identifier = next(spec['id'] for spec in specs if spec['name'] == '方案甲')
    assert client.delete(f'{url}/{identifier}').status_code == 200
    assert [spec['name'] for spec in client.get(url).json['group_specs']] == ['方案乙']


def test_sample_coverage_preserves_ids_without_fifth_input(context):
    app, _, project = context
    for kind, samples in [('pep', ['001', '002']), ('profile', ['001']), ('transcriptome', ['001', '003']), ('cibersort', ['001'])]:
        db.session.add(ProjectAsset(project_id=project.id, asset_type=kind, original_name=kind, storage_path=f'/tmp/{kind}', size=1,
                                     metadata_json={'asset_set': '甲', 'validation': {'status': 'valid', 'summary': {'inputs': [{'samples': samples}]}}}))
    db.session.commit()
    response = app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲')
    assert response.status_code == 200
    rows = response.json['samples']
    assert [row['sample_id'] for row in rows] == ['001', '002', '003']
    assert set(rows[0]['coverage']) == {'pep', 'profile', 'transcriptome', 'deconvolution'}
    assert SampleRecord.query.count() == 0


def test_admin_samples_are_scoped_and_fields_can_be_cleared(context):
    app, _, project = context
    a = User(username='管理员', email='a@example.org', password_hash='unused', role='admin')
    b = User(username='其他', email='b@example.org', password_hash='unused')
    db.session.add_all([a, b]); db.session.flush()
    project.user_id = a.id
    other = Project(name='其他项目', user_id=b.id)
    db.session.add(other); db.session.flush()
    sample = SampleRecord(project_id=project.id, sample_id='001', sample_name='登记甲', illness='疾病')
    stranger = SampleRecord(project_id=other.id, sample_id='秘密', sample_name='其他登记')
    db.session.add_all([sample, stranger]); db.session.commit()
    app.config['REQUIRE_LOGIN'] = True
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(a.id)
        session['_fresh'] = True
    response = client.get('/api/samples?page=1&page_size=1')
    assert response.status_code == 200
    assert response.json['pagination']['total'] == 1
    assert response.json['samples'][0]['sample_id'] == '001'
    assert client.put(f'/api/samples/{stranger.id}', json={'illness': None}).status_code == 400
    assert client.put(f'/api/samples/{sample.id}', json={'illness': None}).json['illness'] is None
    assert '秘密' not in client.get('/api/samples/field-options').json['fields']['sample_id']


def test_bulk_download_contains_authorized_files_and_rejects_foreign_ids(context):
    app, service, project = context
    a = upload(service, project)
    other = Project(name='另一个项目'); db.session.add(other); db.session.commit()
    b = upload(service, other)
    client = app.test_client()
    url = f'/api/projects/{project.id}/assets/download'
    response = client.post(url, json={'asset_ids': [a.id]})
    assert response.status_code == 200
    import zipfile
    with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
        assert archive.read(archive.namelist()[0]) == b'sample,value\n001,1\n'
    assert client.post(url, json={'asset_ids': [a.id, b.id]}).status_code == 400


def summary_upload(service, project, dataset, content, replace=False):
    return service.upload_assets(project, asset_type='sample_summary',
        file_storages=[FileStorage(stream=io.BytesIO(content.encode('utf-8')), filename='登记.csv')],
        metadata={'asset_set': dataset}, replace_existing=replace)[0]


def test_summary_history_delete_keeps_current_and_other_dataset(context):
    _, service, project = context
    old = summary_upload(service, project, '甲', 'sample_id,sample_name,illness\n001,甲样本,旧\n')
    other = summary_upload(service, project, '乙', 'sample_id,sample_name,illness\n001,乙样本,乙\n')
    current = summary_upload(service, project, '甲', 'sample_id,sample_name,illness\n001,甲样本,新\n', replace=True)
    assert SampleRecord.query.count() == 2
    service.delete_asset(old)
    rows = SampleRecord.query.all()
    assert {row.extra_metadata['asset_set']: row.illness for row in rows} == {'甲': '新', '乙': '乙'}
    assert {row.extra_metadata['source_asset_id'] for row in rows} == {current.id, other.id}


def test_summary_reimport_and_delete_preserve_manual_edits(context):
    app, service, project = context
    old = summary_upload(service, project, '甲', 'sample_id,sample_name,illness\n001,甲样本,旧\n002,另一个,旧\n')
    record = SampleRecord.query.filter_by(sample_id='001').one()
    client = app.test_client()
    assert client.put(f'/api/samples/{record.id}', json={'illness': '人工补充'}).status_code == 200
    new = summary_upload(service, project, '甲', 'sample_id,sample_name,illness\n001,甲样本,文件新版\n', replace=True)
    assert SampleRecord.query.count() == 1
    assert record.illness == '人工补充'
    assert record.extra_metadata['source_asset_id'] == new.id
    service.delete_asset(old)
    service.delete_asset(new)
    assert SampleRecord.query.count() == 1
    assert record.extra_metadata['registration_kind'] == 'manual'
    assert 'source_asset_id' not in record.extra_metadata


def test_unknown_legacy_summary_does_not_authorize_clearing_registration(context):
    _, service, project = context
    asset = ProjectAsset(project_id=project.id, asset_type='sample_summary', original_name='旧表.csv',
                         storage_path='/tmp/unknown-registration.csv', size=1, metadata_json={'superseded': True})
    record = SampleRecord(project_id=project.id, sample_id='001', sample_name='来源未标记的登记')
    db.session.add_all([asset, record]); db.session.commit()
    service.delete_asset(asset)
    assert SampleRecord.query.one().id == record.id


def test_group_edit_publishes_immutable_version_and_history_delete_keeps_spec(context):
    from flask_app.models.database import ProjectGroupSpec
    _, service, project = context
    old = service.save_group_spec_asset(project, name='方案', spec_json={'groups': ['健康', '疾病']})
    content = Path(old.storage_path).read_bytes()
    new = service.save_group_spec_asset(project, name='方案', spec_json={'groups': ['疾病', '健康']})
    assert old.metadata_json['superseded_by'] == [new.id]
    assert old.storage_path != new.storage_path
    assert Path(old.storage_path).read_bytes() == content
    assert ProjectGroupSpec.query.count() == 1
    service.delete_asset(old)
    assert ProjectGroupSpec.query.one().spec_json == {'groups': ['疾病', '健康']}
    assert Path(new.storage_path).is_file()


def test_group_write_failure_rolls_back_existing_and_new_specs(context):
    from flask_app.models.database import ProjectGroupSpec
    from flask_app.exceptions import StorageError
    _, service, project = context
    old = service.save_group_spec_asset(project, name='旧方案', spec_json={'groups': ['甲', '乙']})
    content = Path(old.storage_path).read_bytes()
    for name in ['旧方案', '新方案']:
        with patch.object(Path, 'write_text', side_effect=PermissionError('合成权限错误')):
            with pytest.raises(StorageError, match='原方案已保留'):
                service.save_group_spec_asset(project, name=name, spec_json={'groups': ['乙', '甲']})
        assert ProjectGroupSpec.query.one().spec_json == {'groups': ['甲', '乙']}
        assert ProjectAsset.query.filter_by(asset_type='group_spec').count() == 1
        assert not old.metadata_json.get('superseded')
        assert Path(old.storage_path).read_bytes() == content


def test_group_database_failure_leaves_old_file_and_no_published_candidate(context):
    from flask_app.exceptions import StorageError
    from flask_app.models.database import ProjectGroupSpec
    _, service, project = context
    old = service.save_group_spec_asset(project, name='方案', spec_json={'groups': ['甲', '乙']})
    files = set(Path(old.storage_path).parent.glob('*.json'))
    with patch.object(db.session, 'commit', side_effect=RuntimeError('合成提交失败')):
        with pytest.raises(StorageError, match='原方案已保留'):
            service.save_group_spec_asset(project, name='方案', spec_json={'groups': ['乙', '甲']})
    assert set(Path(old.storage_path).parent.glob('*.json')) == files
    assert ProjectGroupSpec.query.one().spec_json == {'groups': ['甲', '乙']}
    assert not old.metadata_json.get('superseded')


def recognized_asset(project, dataset='甲', kind='profile', samples=None):
    asset = ProjectAsset(project_id=project.id, asset_type=kind, original_name=f'{dataset}_{kind}.csv',
                         storage_path=f'/tmp/{project.id}_{dataset}_{kind}.csv', size=1,
                         metadata_json={'asset_set': dataset, 'validation': {'status': 'valid',
                         'summary': {'inputs': [{'samples': samples or ['001']}]}}})
    db.session.add(asset); db.session.commit()
    return asset


def test_explicit_registration_preserves_input_and_scopes_same_identifier(context):
    app, _, project = context
    a, b = recognized_asset(project), recognized_asset(project, '乙')
    client = app.test_client()
    url = f'/api/projects/{project.id}/samples/registration'
    assert client.get(url, query_string={'asset_set': '甲', 'sample_id': '001'}).json['sample'] is None
    assert SampleRecord.query.count() == 0
    source = dict(a.metadata_json)
    first = client.post(url, json={'asset_set': '甲', 'sample_id': '001', 'fields': {'illness': '甲疾病'}})
    second = client.post(url, json={'asset_set': '乙', 'sample_id': '001', 'fields': {'illness': '乙疾病'}})
    assert first.status_code == second.status_code == 200
    assert first.json['sample']['id'] != second.json['sample']['id']
    assert first.json['sample']['sample_id'] == '001'
    assert SampleRecord.query.count() == 2
    assert client.post(url, json={'asset_set': '甲', 'sample_id': '001', 'fields': {'illness': ''}}).json['sample']['illness'] is None
    assert SampleRecord.query.count() == 2
    assert a.metadata_json == source
    assert client.get(url, query_string={'asset_set': '乙', 'sample_id': '001'}).json['sample']['illness'] == '乙疾病'


def test_registration_rejects_unknown_sample_and_invalid_save_without_partial_record(context):
    app, _, project = context
    recognized_asset(project)
    client = app.test_client(); url = f'/api/projects/{project.id}/samples/registration'
    assert client.post(url, json={'asset_set': '甲', 'sample_id': '999', 'fields': {}}).status_code == 400
    assert client.post(url, json={'asset_set': '甲', 'sample_id': '001', 'fields': {'sample_name': ''}}).status_code == 400
    assert SampleRecord.query.count() == 0
    assert client.post(url, json={'asset_set': '甲', 'sample_id': '001', 'fields': {'sample_id': 'new'}}).status_code == 400
    assert SampleRecord.query.count() == 0


def test_project_counts_distinguish_input_ids_registration_and_history(context):
    app, _, project = context
    recognized_asset(project, '甲', 'profile', ['001', '002'])
    recognized_asset(project, '甲', 'pep', ['001'])
    retired = recognized_asset(project, '甲', 'transcriptome', ['099'])
    retired.metadata_json = {**retired.metadata_json, 'superseded': True}
    recognized_asset(project, '乙', 'profile', ['001'])
    db.session.add(SampleRecord(project_id=project.id, sample_id='独立登记', sample_name='登记'))
    db.session.commit()
    payload = app.test_client().get('/api/projects').json['projects'][0]
    assert payload['input_sample_count'] == 3
    assert payload['registered_sample_count'] == payload['sample_count'] == 1
    assert payload['dataset_count'] == 2
    assert payload['historical_asset_count'] == 1
    assert payload['asset_counts'] == {'pep': 1, 'profile': 2}
    assert payload['asset_status']['has_pep'] and payload['asset_status']['has_profile']
    assert not payload['asset_status']['has_transcriptome']


def test_registration_metadata_update_cannot_remove_source_provenance(context):
    app, service, project = context
    asset = summary_upload(service, project, '甲', 'sample_id,sample_name,illness\n001,甲样本,旧\n')
    record = SampleRecord.query.one()
    response = app.test_client().put(f'/api/samples/{record.id}', json={'extra_metadata': {'source_asset_id': 'fake'}, 'illness': '编辑'})
    assert response.status_code == 200
    assert response.json['extra_metadata']['source_asset_id'] == asset.id
    assert response.json['extra_metadata']['asset_set'] == '甲'
    assert response.json['extra_metadata']['manual_fields'] == ['illness']


def test_dataset_summary_is_complete_lightweight_and_alias_scoped(context):
    app, service, project = context
    for index in range(215):
        asset = recognized_asset(project, dataset='甲', kind='profile', samples=['001'])
        asset.metadata_json = {'dataset': ' 甲 ', 'validation': {'status': 'pending' if index == 0 else 'valid',
            'summary': {'inputs': [{'samples': ['001'], 'sample_count': 1}]}}}
    retired = recognized_asset(project, dataset='甲', kind='profile')
    retired.metadata_json = {**retired.metadata_json, 'superseded': True}
    recognized_asset(project, dataset='乙', kind='datapoint', samples=['002'])
    recognized_asset(project, dataset='甲', kind='project_file')
    db.session.commit()
    response = app.test_client().get(f'/api/projects/{project.id}/datasets')
    assert response.status_code == 200
    groups = {entry['name']: entry for entry in response.json['datasets']}
    assert groups['甲']['input_count'] == 215
    assert groups['甲']['kinds']['profile']['statuses'] == {'pending': 1, 'valid': 214}
    assert groups['甲']['kinds']['profile']['sample_min'] == 1
    assert groups['乙']['kinds']['profile']['count'] == 1
    assert 'assets' not in groups['甲']
    selected = app.test_client().get(f'/api/projects/{project.id}/assets?inputs_only=true&asset_set=甲&page_size=200')
    assert selected.json['pagination']['total'] == 215


def test_summary_project_has_same_counts_without_loading_relationships(context):
    from sqlalchemy import inspect
    app, _, project = context
    recognized_asset(project, dataset='甲', samples=['001', '002'])
    recognized_asset(project, dataset='乙', samples=['001'])
    db.session.add(SampleRecord(project_id=project.id, sample_id='001', sample_name='登记', extra_metadata={'asset_set': '甲'}))
    db.session.commit()
    expected = project.to_dict()
    db.session.expire_all()
    with patch('flask_app.services.mongo_service.get_project_results', return_value=[]):
        response = app.test_client().get(f'/api/projects/{project.id}?summary_only=true')
    assert response.status_code == 200
    assert 'assets' not in response.json and 'samples_preview' not in response.json
    for key in ['input_sample_count', 'registered_sample_count', 'asset_counts', 'dataset_count', 'historical_asset_count']:
        assert response.json[key] == expected[key]
    assert 'assets' in inspect(project).unloaded and 'samples' in inspect(project).unloaded


def test_summary_result_count_preserves_sql_mongo_deduplication(context):
    app, _, project = context
    db.session.add(ProjectAsset(project_id=project.id, asset_type='processed_result', original_name='结果',
        storage_path='/synthetic/results/a', metadata_json={'analysis_signature': 's', 'job_id': 'j'}))
    db.session.commit()
    documents = [{'analysis_signature': 's', 'job_id': 'j', 'output_base': '/synthetic/results/a'},
                 {'analysis_signature': 't', 'job_id': 'k', 'output_base': '/synthetic/results/b'}]
    with patch('flask_app.services.mongo_service.get_project_results', return_value=documents) as query:
        response = app.test_client().get(f'/api/projects/{project.id}?summary_only=true')
    assert response.json['result_count'] == 2
    assert response.json['asset_status']['has_results']
    assert query.call_args.kwargs['projection']['output_base'] == 1


def test_registry_list_options_export_are_dataset_scoped(context):
    app, _, project = context
    for dataset, institution in [('甲', '甲机构'), ('乙', '乙机构')]:
        db.session.add(SampleRecord(project_id=project.id, sample_id='001', sample_name='原编号', institution=institution,
                                   extra_metadata={'asset_set': dataset}))
    db.session.commit()
    query = {'project_id': project.id, 'asset_set': '甲'}
    client = app.test_client()
    records = client.get('/api/samples', query_string={**query, 'page': 1}).json
    assert records['pagination']['total'] == 1
    assert records['samples'][0]['institution'] == '甲机构'
    assert client.get('/api/samples/field-options', query_string=query).json['fields']['institution'] == ['甲机构']
    exported = client.get('/api/samples/export', query_string=query).data.decode('utf-8-sig')
    assert '甲机构' in exported and '乙机构' not in exported


def test_input_sample_attention_filter_uses_actual_validation_status(context):
    app, _, project = context
    good = recognized_asset(project, samples=['001'])
    pending = recognized_asset(project, samples=['002'])
    pending.metadata_json = {**pending.metadata_json, 'validation': {'status': 'pending', 'summary': {'inputs': [{'samples': ['002']}]}}}
    db.session.commit()
    response = app.test_client().get(f'/api/projects/{project.id}/input-samples?state=needs_attention')
    assert [row['sample_id'] for row in response.json['samples']] == ['002']


def test_directory_preview_pages_files_preserves_ids_and_denies_traversal(context, tmp_path):
    app, _, project = context
    directory = tmp_path / 'pep-folder'; directory.mkdir()
    for number in range(25):
        (directory / f'{number:03d}_TRA.csv').write_text('sample,CDR3\n001,CASS\n002,CATS\n003,CALS\n004,CAPS\n005,CARS\n006,CAVS\n', encoding='utf-8')
    outside = tmp_path / 'outside.csv'; outside.write_text('private\nsecret\n', encoding='utf-8')
    (directory / 'link.csv').symlink_to(outside)
    asset = ProjectAsset(project_id=project.id, asset_type='pep', original_name='pep-folder', storage_path=str(directory))
    db.session.add(asset); db.session.commit()
    url = f'/api/projects/{project.id}/assets/{asset.id}/table-preview'
    client = app.test_client()
    listing = client.get(url, query_string={'page_size': 20}).json
    assert listing['directory'] and listing['pagination']['total'] == 25
    assert len(listing['files']) == 20 and listing['rows'] == []
    assert len(client.get(url, query_string={'page': 2, 'page_size': 20}).json['files']) == 5
    preview = client.get(url, query_string={'file': '000_TRA.csv'}).json
    assert len(preview['rows']) == 5 and preview['rows'][0][0] == '001'
    assert client.get(url, query_string={'file': '../outside.csv'}).status_code == 400
    assert client.get(url, query_string={'file': 'link.csv'}).status_code == 400
    other = Project(name='无权关联项目'); db.session.add(other); db.session.commit()
    assert client.get(f'/api/projects/{other.id}/assets/{asset.id}/table-preview').status_code == 400


def test_failed_validation_job_updates_waiting_asset_using_actual_terminal_state(context):
    app, _, project = context
    asset = recognized_asset(project)
    live = recognized_asset(project, dataset='乙')
    db.session.add_all([AnalysisJob(id='failed-validation', job_type='input_validation', module='input-validation',
        project_id=project.id, status='failed', error='工作进程已终止'),
        AnalysisJob(id='live-validation', job_type='input_validation', module='input-validation', project_id=project.id, status='running')])
    asset.metadata_json = {**asset.metadata_json, 'validation': {'status': 'pending'}, 'validation_job_id': 'failed-validation'}
    live.metadata_json = {**live.metadata_json, 'validation': {'status': 'pending'}, 'validation_job_id': 'live-validation'}
    db.session.commit()
    response = app.test_client().get(f'/api/projects/{project.id}/datasets')
    assert response.status_code == 200
    assert asset.metadata_json['validation']['status'] == 'failed'
    assert asset.metadata_json['validation']['message'] == '工作进程已终止'
    assert live.metadata_json['validation']['status'] == 'pending'


def test_validation_queue_creation_failure_keeps_file_and_marks_retryable_failure(context, monkeypatch):
    app, _, project = context
    asset = recognized_asset(project)
    asset.metadata_json = {**asset.metadata_json, 'validation': {'status': 'pending'}}; db.session.commit()
    monkeypatch.setenv('JOB_QUEUE', 'redis')
    with patch('flask_app.services.background_job_service.get_background_job_service', side_effect=RuntimeError('队列连接失败')):
        actual_schedule_validation([asset])
    assert db.session.get(ProjectAsset, asset.id) is not None
    assert asset.metadata_json['validation']['status'] == 'failed'
    assert '队列连接失败' in asset.metadata_json['validation']['message']


def test_old_pep_report_has_explicit_refresh_status_in_sample_coverage(context):
    app, _, project = context
    asset = recognized_asset(project, kind='pep')
    asset.metadata_json = {'asset_set': '甲', 'validation': {'status': 'valid', 'key': {'validator': 5},
        'summary': {'inputs': [{'sample_count': 2}]}}}
    db.session.commit()
    response = app.test_client().get(f'/api/projects/{project.id}/input-samples')
    assert response.json['samples'] == []
    assert response.json['unresolved'][0]['status'] == 'needs_refresh'


def test_shared_asset_delete_preserves_other_registration_bytes(context):
    app, service, project = context
    original = upload(service, project)
    content = Path(original.storage_path).read_bytes()
    other = Project(name='合成复用项目')
    db.session.add(other); db.session.commit()
    shared = service.register_cached_asset(other, asset_type='profile', storage_path=original.storage_path)
    original_id, shared_id = original.id, shared.id
    response = app.test_client().delete(f'/api/projects/{project.id}/assets/{original_id}')
    assert response.status_code == 200 and response.json['storage_retained']
    assert db.session.get(ProjectAsset, original_id) is None
    assert db.session.get(ProjectAsset, shared_id) is not None
    assert Path(shared.storage_path).read_bytes() == content


def test_shared_parent_directory_preserves_child_asset(context):
    _, service, project = context
    original = upload(service, project)
    directory = service.get_asset_dir(project, 'pep') / '共享目录'
    directory.mkdir(parents=True, exist_ok=True)
    child = directory / '001.csv'; child.write_text('sample,value\n001,1\n', encoding='utf-8')
    parent = service.register_cached_asset(project, asset_type='pep', storage_path=str(directory))
    shared = service.register_cached_asset(project, asset_type='profile', storage_path=str(child))
    service.delete_asset(parent)
    assert child.read_text(encoding='utf-8').endswith('001,1\n')
    assert db.session.get(ProjectAsset, shared.id) is not None


def test_file_description_can_change_without_mutating_referenced_input(context):
    app, service, project = context
    asset = upload(service, project)
    before = Path(asset.storage_path).read_bytes()
    db.session.add(AnalysisJob(id='synthetic-reference-v4', project_id=project.id,
        job_type='analysis', module='profile', status='completed', payload={'asset_id': asset.id}))
    db.session.commit()
    response = app.test_client().patch(f'/api/projects/{project.id}/assets/{asset.id}',
        json={'metadata_json': {'description': '合成输入用途'}})
    assert response.status_code == 200
    assert response.json['asset']['metadata']['description'] == '合成输入用途'
    assert response.json['asset']['metadata']['asset_set'] == '甲'
    assert Path(asset.storage_path).read_bytes() == before
    blocked = app.test_client().patch(f'/api/projects/{project.id}/assets/{asset.id}',
        json={'metadata_json': {'asset_set': '乙'}})
    assert blocked.status_code != 200


def test_scheme_stable_id_rename_preserves_attributes_and_immutable_file(context):
    app, service, project = context
    old = service.save_group_spec_asset(project, name='原方案', spec_json={'group_field':'group',
        'groups':[{'name':'健康','color':'blue'}, {'name':'患者','color':'red'}], 'description':'保留原说明'})
    old_content = Path(old.storage_path).read_bytes()
    spec_id = old.metadata_json['spec_id']
    response = app.test_client().post(f'/api/projects/{project.id}/group-specs', json={
        'id':spec_id, 'expected_revision':old.id, 'name':'重命名方案', 'spec_json': {'groups':[{'name':'患者','color':'red'}, {'name':'健康','color':'blue'}]}})
    assert response.status_code == 201
    spec = response.json['group_specs'][0]
    assert spec['id'] == spec_id and spec['name'] == '重命名方案'
    assert spec['spec_json']['group_field'] == 'group'
    assert spec['spec_json']['description'] == '保留原说明'
    assert Path(old.storage_path).read_bytes() == old_content
    import json
    assert json.loads(Path(response.json['asset']['storage_path']).read_text(encoding='utf-8')) == spec['spec_json']


def test_group_values_use_owned_asset_real_field_and_text_identity(context):
    app, service, project = context
    asset = upload(service, project, content='sample,group,value\n001,健康,1\n002,患者,2\n003,健康,3\n'.encode())
    response = app.test_client().get(f'/api/projects/{project.id}/assets/{asset.id}/group-values?field=group')
    assert response.status_code == 200
    assert response.json['samples_by_value']['健康'] == ['001','003']
    assert response.json['row_counts']['健康'] == 2
    assert response.json['content_version'] == asset.metadata_json['content_version']
    other = Project(name='其他项目'); db.session.add(other); db.session.commit()
    assert app.test_client().get(f'/api/projects/{other.id}/assets/{asset.id}/group-values?field=group').status_code != 200
    assert app.test_client().get(f'/api/projects/{project.id}/assets/{asset.id}/group-values?field=missing').status_code != 200


def test_source_bound_scheme_rejects_unknown_group_and_foreign_version(context):
    app, service, project = context
    asset = upload(service, project, content=b'sample,group,value\n001,control,1\n002,patient,2\n')
    endpoint = f'/api/projects/{project.id}/group-specs'
    definition = {'source_asset_id':asset.id, 'group_field':'group', 'groups':['patient','control']}
    bad = app.test_client().post(endpoint, json={'name':'不匹配', 'spec_json':{**definition,'groups':['absent']}})
    assert bad.status_code != 201
    good = app.test_client().post(endpoint, json={'name':'真实来源', 'spec_json':definition})
    assert good.status_code == 201
    spec = good.json['group_specs'][0]
    from flask_app.services.group_spec_service import get_group_spec_service
    resolved = get_group_spec_service().apply_to_payload('profile', {
        'group_spec_id':spec['id'],'datapoint_path':asset.storage_path}, project.id)
    assert resolved['group_order'] == 'patient,control'
    other = upload(service, project, dataset='乙')
    with pytest.raises(ValidationError, match='来源版本'):
        get_group_spec_service().apply_to_payload('profile', {'group_spec_id':spec['id'], 'datapoint_path':other.storage_path}, project.id)


def test_unified_result_pages_include_sql_mongo_once_and_stable_order(context, monkeypatch):
    app, _, project = context
    from datetime import datetime
    now = datetime(2026,10,3,0,0,0)
    for index in range(5):
        db.session.add(ProjectAsset(id=f'sql-v4-{index}', project_id=project.id, asset_type='processed_result',
            original_name=f'result-{index}',storage_path=f'/synthetic/output/{index}',uploaded_at=now,
            metadata_json={'analysis_type':'profile','job_id':f'run-{index}'}))
    db.session.commit()
    docs = [{'_id':'mongo-v4-duplicate','project_id':project.id,'analysis_type':'profile','job_id':'run-0',
             'output_base':'/synthetic/output/0','created_at':now},
            {'_id':'mongo-v4-only','project_id':project.id,'analysis_type':'profile','job_id':'run-mongo',
             'output_base':'/synthetic/output/mongo','created_at':now}]
    monkeypatch.setattr(api_projects,'_merge_mongo_results',REAL_MERGE_MONGO_RESULTS)
    with patch('flask_app.services.mongo_service.get_project_results',return_value=docs):
        client=app.test_client()
        pages=[client.get(f'/api/projects/{project.id}/results?page={page}&page_size=2').json for page in [1,2,3]]
        repeated=client.get(f'/api/projects/{project.id}/results?page=1&page_size=2').json
        count=client.get(f'/api/projects/{project.id}?summary_only=true').json['result_count']
    assert [page['pagination']['total'] for page in pages] == [6,6,6]
    identities=[asset['id'] for page in pages for asset in page['results']]
    assert len(identities) == len(set(identities)) == count == 6
    assert set(identities) == {f'sql-v4-{index}' for index in range(5)} | {'mongo-v4-only'}
    assert repeated['results'] == pages[0]['results']


def test_attention_file_filter_includes_failed_mapping_and_unknown(context):
    app, _, project = context
    for index, state in enumerate(['valid','failed','invalid','needs_mapping','unknown','pending']):
        asset = recognized_asset(project,samples=[f'{index:03d}'])
        asset.metadata_json = {**asset.metadata_json,'validation':{'status':state}}
    db.session.commit()
    response = app.test_client().get(f'/api/projects/{project.id}/assets?inputs_only=true&validation_status=needs_attention')
    assert response.status_code == 200 and response.json['pagination']['total'] == 4
    assert {asset['metadata']['validation']['status'] for asset in response.json['assets']} == {'failed','invalid','needs_mapping','unknown'}


def test_unchanged_fields_do_not_become_manual_or_block_source_updates(context):
    _, _, project = context
    import pandas as pd
    from flask_app.services.sample_registry_service import get_sample_registry_service
    registry = get_sample_registry_service()
    frame = pd.DataFrame({'sample_id':['001'], 'sample_name':['来源名称'], 'institution':['甲机构'], 'species':['人']})
    record = registry.import_sample_summary_dataframe(project, frame, source_asset_id='synthetic-register', asset_set='甲')[0]
    registry.update_sample(record, {'sample_name':'人工名称','institution':'甲机构','spices':'人'})
    assert set(record.extra_metadata['manual_fields']) == {'sample_name'}
    frame.loc[0,'institution'] = '乙机构'
    updated = registry.import_sample_summary_dataframe(project, frame, source_asset_id='synthetic-register', asset_set='甲')[0]
    assert updated.id == record.id and updated.sample_name == '人工名称' and updated.institution == '乙机构'
    registry.update_sample(updated, {'institution':''})
    frame.loc[0,'institution'] = '丙机构'
    again = registry.import_sample_summary_dataframe(project, frame, source_asset_id='synthetic-register', asset_set='甲')[0]
    assert again.institution is None and again.sample_id == '001'


def test_group_source_blocks_delete_and_assignment_until_scheme_changed(context):
    app, service, project = context
    asset = upload(service, project, content=b'sample,group,value\n001,A,1\n002,B,2\n')
    response = app.test_client().post(f'/api/projects/{project.id}/group-specs', json={
        'name':'来源依赖', 'spec_json':{'source_asset_id':asset.id,'group_field':'group','groups':['A','B']}})
    assert response.status_code == 201
    endpoint = f'/api/projects/{project.id}/assets/{asset.id}'
    blocked = app.test_client().delete(endpoint)
    assert blocked.status_code != 200 and '来源依赖' in blocked.json['message']
    assert Path(asset.storage_path).exists() and db.session.get(ProjectAsset,asset.id) is not None
    assert app.test_client().patch(endpoint,json={'metadata_json':{'asset_set':'乙'}}).status_code != 200
    assert app.test_client().patch(endpoint,json={'metadata_json':{'description':'可更新说明'}}).status_code == 200
    spec = response.json['group_specs'][0]
    assert app.test_client().delete(f'/api/projects/{project.id}/group-specs/{spec["id"]}').status_code == 200
    assert app.test_client().delete(endpoint).status_code == 200


def test_scheme_compatibility_uses_owned_original_and_prepared_source_paths(context):
    app, service, project = context
    asset = upload(service, project,content=b'sample,group,value\n001,A,1\n002,B,2\n')
    other = upload(service, project,dataset='乙')
    service.save_group_spec_asset(project,name='来源方案',spec_json={'source_asset_id':asset.id,'group_field':'group','groups':['A','B']})
    prepared_path = Path(asset.storage_path).parent / 'prepared.csv'
    prepared_path.write_text('sample,group,value\n001,A,1\n002,B,2\n', encoding='utf-8')
    prepared = ProjectAsset(project_id=project.id,asset_type='profile',original_name='规范化.csv',storage_path=str(prepared_path),
        metadata_json={'asset_set':'甲','source_asset_id':asset.id})
    db.session.add(prepared);db.session.commit()
    endpoint=f'/api/projects/{project.id}/group-specs'
    client=app.test_client()
    assert client.get(endpoint,query_string={'profile_path':asset.storage_path,'asset_set':'甲'}).json['group_specs'][0]['source']['available']
    assert client.get(endpoint,query_string={'profile_path':prepared.storage_path,'asset_set':'甲'}).json['group_specs'][0]['source']['available']
    source=client.get(endpoint,query_string={'profile_path':other.storage_path,'asset_set':'甲'}).json['group_specs'][0]['source']
    assert not source['available'] and '版本' in source['reason']
    source=client.get(endpoint,query_string={'profile_path':asset.storage_path,'asset_set':'乙'}).json['group_specs'][0]['source']
    assert not source['available'] and '数据集' in source['reason']


@pytest.mark.parametrize('filter_value, expected', [('human',{'001','002'}),('人',{'001','002'}),('mouse',{'003','004'}),('小鼠',{'003','004'}),('斑马鱼',{'005'})])
def test_species_filters_match_explicit_chinese_english_aliases_without_rewriting(context, filter_value, expected):
    app,_,project=context
    originals=['人','human','小鼠','mouse','斑马鱼']
    for index,value in enumerate(originals,1):
        db.session.add(SampleRecord(project_id=project.id,sample_id=f'{index:03d}',sample_name=f'登记{index}',spices=value,extra_metadata={'asset_set':'甲'}))
    db.session.commit()
    response=app.test_client().get('/api/samples',query_string={'project_id':project.id,'asset_set':'甲','spices':filter_value,'page':1})
    assert response.status_code==200
    assert {record['sample_id'] for record in response.json['samples']}==expected
    assert [record.spices for record in SampleRecord.query.order_by(SampleRecord.sample_id).all()]==originals


def test_group_summary_counts_preserve_unique_ids_and_read_only_needed_columns(context):
    app, service, project = context
    asset = upload(service, project, content=b'sample,group,unused\n001,A,large\n001,A,large\n002,A,large\n,B,large\n003,B,large\n004,,large\n')
    from flask_app.routes.api_script_hub import _common
    original = _common._robust_read_csv
    reads = []
    def read(path, **options):
        if 'usecols' in options:
            reads.append(options['usecols'])
        return original(path, **options)
    with patch.object(_common, '_robust_read_csv', side_effect=read):
        response = app.test_client().get(f'/api/projects/{project.id}/assets/{asset.id}/group-values?field=group&include_samples=false')
    assert response.status_code == 200
    assert reads == [['group', 'sample']]
    assert response.json['sample_counts'] == {'A': 2, 'B': 1}
    assert response.json['row_counts'] == {'A': 3, 'B': 2}
    assert response.json['samples_by_value'] == {}
    full = app.test_client().get(f'/api/projects/{project.id}/assets/{asset.id}/group-values?field=group')
    assert full.json['samples_by_value'] == {'': ['004'], 'A': ['001', '002'], 'B': ['003']}
    assert full.json['sample_counts'] == response.json['sample_counts']


@pytest.mark.parametrize('extension', ['csv', 'tsv', 'xlsx'])
def test_group_summary_required_columns_work_with_text_and_excel(context, extension):
    app, service, project = context
    import pandas as pd
    path = service.projects_root / f'groups.{extension}'
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({'sample': ['001', '001', '002'], 'group': ['A', 'A', 'B'], 'unused': ['extra'] * 3})
    if extension == 'xlsx':
        frame.to_excel(path, index=False)
    else:
        frame.to_csv(path, index=False, sep='\t' if extension == 'tsv' else ',')
    asset = service.register_cached_asset(project, asset_type='profile', storage_path=str(path), original_name=path.name, metadata={'asset_set': '甲'})
    result = app.test_client().get(f'/api/projects/{project.id}/assets/{asset.id}/group-values?field=group&include_samples=false')
    assert result.status_code == 200, result.json
    assert result.json['sample_counts'] == {'A': 1, 'B': 1}
    assert result.json['row_counts'] == {'A': 2, 'B': 1}
    assert result.json['samples_by_value'] == {}


def test_asset_detail_reads_exact_owned_history_without_list_page(context):
    app, service, project = context
    old = upload(service, project)
    upload(service, project, replace=True)
    response = app.test_client().get(f'/api/projects/{project.id}/assets/{old.id}')
    assert response.status_code == 200
    assert response.json['asset']['id'] == old.id
    assert response.json['asset']['metadata']['superseded'] is True
    other = Project(name='其他范围')
    db.session.add(other)
    db.session.commit()
    foreign = app.test_client().get(f'/api/projects/{other.id}/assets/{old.id}')
    assert foreign.status_code != 200
    missing = app.test_client().get(f'/api/projects/{project.id}/assets/missing')
    assert missing.status_code != 200


def test_coverage_scope_distinguishes_absence_from_missing_identifier(context):
    app, service, project = context
    recognized_asset(project)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='cibersort', original_name='浸润.csv',
        storage_path='/tmp/infiltration.csv', metadata_json={'asset_set': '甲', 'validation': {
            'status': 'valid', 'summary': {'inputs': [{'samples': ['002']}]}}}))
    db.session.commit()
    data = app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲').json
    assert [row['sample_id'] for row in data['samples']] == ['001', '002']
    assert data['input_scopes'] == {'甲': {'profile': {'asset_count': 1, 'unresolved_count': 0},
                                        'deconvolution': {'asset_count': 1, 'unresolved_count': 0}}}
    assert 'deconvolution' not in data['samples'][0]['coverage']
    assert 'pep' not in data['input_scopes']['甲']
    # Neither an absent optional input nor a different identified sample is a validation error.
    data = app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲&state=needs_attention').json
    assert data['samples'] == []


@pytest.mark.parametrize('status', ['pending', 'needs_mapping', 'invalid', 'failed', 'unknown', 'valid'])
def test_unidentified_file_never_proves_missing_sample(context, status):
    app, service, project = context
    recognized_asset(project)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='transcriptome', original_name='待识别.csv',
        storage_path='/tmp/unidentified.csv', metadata_json={'asset_set': '甲', 'validation': {
            'status': status, 'summary': {'inputs': [{'samples': []}]}}}))
    db.session.commit()
    data = app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲&state=needs_attention').json
    assert [row['sample_id'] for row in data['samples']] == ['001']
    assert data['input_scopes']['甲']['transcriptome'] == {'asset_count': 1, 'unresolved_count': 1}
    assert len(data['unresolved']) == 1


def test_coverage_scope_pending_partial_and_dataset_version_isolation(context):
    app, service, project = context
    recognized_asset(project)
    for dataset, historical in [('甲', False), ('甲', True), ('乙', False)]:
        db.session.add(ProjectAsset(project_id=project.id, asset_type='pep', original_name='克隆.csv',
            storage_path=f'/tmp/{dataset}-{historical}.csv', metadata_json={
                'asset_set': dataset, 'superseded': historical,
                'validation': {'status': 'pending', 'summary': {'inputs': [{'samples': ['002']}]}}}))
    db.session.commit()
    data = app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲&q=001&state=needs_attention').json
    assert [row['sample_id'] for row in data['samples']] == ['001']
    assert set(data['input_scopes']) == {'甲'}
    assert data['input_scopes']['甲']['pep'] == {'asset_count': 1, 'unresolved_count': 1}


def test_summary_dataset_patch_preserves_linked_and_manual_records(context):
    app, service, project = context
    asset = summary_upload(service, project, '甲', 'sample_id,sample_name,illness\n001,登记样本,来源疾病\n')
    record = SampleRecord.query.filter_by(project_id=project.id, sample_id='001').one()
    from flask_app.services.sample_registry_service import get_sample_registry_service
    get_sample_registry_service().update_sample(record, {'illness': '人工补充'})
    manual = SampleRecord(project_id=project.id, sample_id='001', sample_name='独立补录',
                          extra_metadata={'asset_set': '乙', 'registration_kind': 'manual'})
    db.session.add(manual); db.session.commit()
    client = app.test_client()
    url = f'/api/projects/{project.id}/assets/{asset.id}'
    rejected = client.patch(url, json={'metadata_json': {'asset_set': '乙', 'description': '不能部分保存'}})
    assert rejected.status_code == 400
    assert '已有来源登记' in rejected.json['message']
    db.session.refresh(asset); db.session.refresh(record); db.session.refresh(manual)
    assert asset.metadata_json['asset_set'] == record.extra_metadata['asset_set'] == '甲'
    assert not asset.metadata_json.get('description')
    assert record.extra_metadata['source_asset_id'] == asset.id
    assert record.extra_metadata['manual_fields'] == ['illness']
    assert record.illness == '人工补充'
    assert manual.extra_metadata['asset_set'] == '乙'
    assert client.patch(url, json={'metadata_json': {'description': '正常说明'}}).status_code == 200
    assert client.patch(url, json={'metadata_json': {'asset_set': ' 甲 '}}).status_code == 200


def test_legacy_summary_group_label_cannot_bypass_source_policy(context):
    app, service, project = context
    asset = summary_upload(service, project, '甲', 'sample_id,sample_name\n001,登记\n')
    asset.metadata_json = {'group_label': '甲'}; db.session.commit()
    result = app.test_client().patch(f'/api/projects/{project.id}/assets/{asset.id}',
                                   json={'metadata_json': {'group_label': '乙'}})
    assert result.status_code == 400
    assert service.dataset_name(asset) == '甲'


def test_summary_without_source_records_can_change_scope(context):
    app, _, project = context
    asset = ProjectAsset(project_id=project.id, asset_type='sample_summary', original_name='空登记表.csv',
        storage_path='/tmp/empty-registration.csv', metadata_json={'asset_set': '甲'})
    # An unrelated/manual registration does not make this asset a source.
    db.session.add_all([asset, SampleRecord(project_id=project.id, sample_id='001', sample_name='人工',
        extra_metadata={'asset_set': '甲', 'registration_kind': 'manual'})]); db.session.commit()
    result = app.test_client().patch(f'/api/projects/{project.id}/assets/{asset.id}',
                                   json={'metadata_json': {'asset_set': '乙'}})
    assert result.status_code == 200
    assert SampleRecord.query.one().extra_metadata['asset_set'] == '甲'


def test_project_cards_details_results_share_unique_product_counts(context, monkeypatch):
    app, _, project = context
    other = Project(name='只有文档结果'); db.session.add(other); db.session.flush()
    for identifier, path, retired in [('a', '/output/a', False), ('duplicate-a', '/output/a', False),
                                      ('b', '/output/b', False), ('history', '/output/old', True)]:
        db.session.add(ProjectAsset(id=identifier, project_id=project.id, asset_type='processed_result',
            original_name=identifier, storage_path=path, metadata_json={
                'analysis_signature': 's', 'job_id': 'j', 'superseded': retired}))
    db.session.commit()
    docs = [{'_id': 'nested-duplicate', 'project_id': project.id, 'metadata_json': {
                'analysis_signature': 's', 'job_id': 'j', 'output_base': '/output/a'}},
            {'_id': 'same-job-other-product', 'project_id': project.id,
                'analysis_signature': 's', 'job_id': 'j', 'output_base': '/output/c'},
            {'_id': 'mongo-only', 'project_id': project.id,
                'analysis_signature': 't', 'job_id': 'k', 'output_base': '/output/d'},
            {'_id': 'other-project-result', 'project_id': other.id, 'output_base': '/other/output'}]
    monkeypatch.setattr(api_projects, '_merge_mongo_results', REAL_MERGE_MONGO_RESULTS)
    with patch('flask_app.services.mongo_service.get_project_results',
               side_effect=lambda identifier, *args, **kwargs: [doc for doc in docs if doc['project_id'] == identifier]), patch(
        'flask_app.services.mongo_service.get_projects_results', return_value=docs) as bulk:
        client = app.test_client()
        cards = {item['id']: item for item in client.get('/api/projects').json['projects']}
        assert bulk.call_count == 1
        assert set(bulk.call_args.args[0]) == {project.id, other.id}
        assert bulk.call_args.kwargs['projection']['output_base'] == 1
        detail = client.get(f'/api/projects/{project.id}').json
        summary = client.get(f'/api/projects/{project.id}?summary_only=true').json
        pages = [client.get(f'/api/projects/{project.id}/results?page={page}&page_size=2').json for page in [1, 2]]
        other_detail = client.get(f'/api/projects/{other.id}').json
    assert [cards[project.id]['result_count'], detail['result_count'], summary['result_count']] == [4, 4, 4]
    assert all(page['pagination']['total'] == 4 for page in pages)
    products = [item['storage_path'] for page in pages for item in page['results']]
    assert set(products) == {'/output/a', '/output/b', '/output/c', '/output/d'}
    assert len(products) == 4
    assert cards[other.id]['result_count'] == other_detail['result_count'] == 1
    assert cards[other.id]['asset_status']['has_results'] and other_detail['asset_status']['has_results']


def test_result_records_without_product_path_are_not_guessed_equal(context, monkeypatch):
    app, _, project = context
    for identifier in ['sql-no-path-a', 'sql-no-path-b']:
        db.session.add(ProjectAsset(id=identifier, project_id=project.id, asset_type='processed_result',
            original_name=identifier, storage_path=''))
    db.session.commit()
    docs = [{'_id': identifier, 'project_id': project.id} for identifier in ['mongo-no-path-a', 'mongo-no-path-b']]
    monkeypatch.setattr(api_projects, '_merge_mongo_results', REAL_MERGE_MONGO_RESULTS)
    with patch('flask_app.services.mongo_service.get_project_results', return_value=docs):
        client = app.test_client()
        results = client.get(f'/api/projects/{project.id}/results').json
        count = client.get(f'/api/projects/{project.id}?summary_only=true').json['result_count']
    assert results['pagination']['total'] == count == 4
    assert len({item['id'] for item in results['results']}) == 4


def test_bulk_result_query_only_uses_authorized_project_ids(context, monkeypatch):
    _, _, project = context
    from flask_app.services import mongo_service
    seen = {}
    class Collection:
        def find(self, query, projection):
            seen.update(query=query, projection=projection)
            return [{'_id': 'result', 'project_id': project.id}]
    monkeypatch.setattr(mongo_service, 'ensure_result_indexes', lambda: None)
    monkeypatch.setattr(mongo_service, 'results_col', lambda: Collection())
    documents = REAL_PROJECTS_RESULTS([project.id], projection={'output_base': 1})
    assert seen == {'query': {'project_id': {'$in': [project.id]}}, 'projection': {'output_base': 1}}
    assert documents[0]['project_id'] == project.id
    assert REAL_PROJECTS_RESULTS([]) == []
