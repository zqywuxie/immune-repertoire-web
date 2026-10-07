"""Registration conflict and scope regression using isolated synthetic records."""
import csv
import io

import pytest
from sqlalchemy import event

from flask_app.tests.test_data_management_contracts import context
from flask_app.models.database import ProjectAsset, SampleRecord, db


def create_sample(project, identifier='001', **fields):
    sample = SampleRecord(project_id=project.id, sample_id=identifier, sample_name=identifier,
                          extra_metadata={'asset_set': '甲'}, **fields)
    db.session.add(sample)
    db.session.commit()
    return sample


def test_stale_same_field_is_rejected_atomically_and_review_can_retry(context):
    app, _, project = context
    sample = create_sample(project)
    identifier = sample.id
    client = app.test_client()
    url = f'/api/samples/{identifier}'
    first = client.put(url, json={'institution': '先保存', 'expected_values': {'institution': None}})
    assert first.status_code == 200
    stale = client.put(url, json={'institution': '后保存', 'illness': '本次新增',
                                 'expected_values': {'institution': None, 'illness': None}})
    assert stale.status_code == 409
    assert stale.json['error_code'] == 'SAMPLE_RECORD_CHANGED'
    assert stale.json['details']['conflicts']['institution'] == {
        'expected': None, 'current': '先保存', 'submitted': '后保存'}
    assert stale.json['details']['sample']['id'] == identifier
    db.session.expire_all()
    current = db.session.get(SampleRecord, identifier)
    assert current.institution == '先保存'
    assert current.illness is None, 'A conflict cannot partially apply other fields.'
    reviewed = client.put(url, json={'institution': '后保存', 'illness': '本次新增',
                                    'expected_values': {'institution': '先保存', 'illness': None}})
    assert reviewed.status_code == 200
    assert reviewed.json['institution'] == '后保存'
    assert reviewed.json['illness'] == '本次新增'
    assert reviewed.json['sample_id'] == '001'


def test_stale_different_field_merges_without_whole_record_overwrite(context):
    app, _, project = context
    sample = create_sample(project)
    url = f'/api/samples/{sample.id}'
    client = app.test_client()
    assert client.put(url, json={'institution': '机构甲', 'expected_values': {'institution': None}}).status_code == 200
    response = client.put(url, json={'illness': '疾病乙', 'expected_values': {'illness': None}})
    assert response.status_code == 200
    assert response.json['institution'] == '机构甲'
    assert response.json['illness'] == '疾病乙'
    assert set(response.json['extra_metadata']['manual_fields']) == {'institution', 'illness'}


@pytest.mark.parametrize('expected', [{}, {'institution': []}, {'institution': None, 'illness': None}, None])
def test_invalid_expected_values_cannot_bypass_conflict_check(context, expected):
    app, _, project = context
    sample = create_sample(project)
    response = app.test_client().put(f'/api/samples/{sample.id}', json={
        'institution': '不应保存', 'expected_values': expected})
    assert response.status_code == 400
    db.session.refresh(sample)
    assert sample.institution is None


def test_registration_mapping_route_checks_conflict_and_preserves_identity(context):
    app, _, project = context
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name='指标.csv',
        storage_path='/synthetic/profile.csv', metadata_json={'asset_set': '甲', 'validation': {
            'status': 'valid', 'summary': {'inputs': [{'samples': ['001']}]}}}))
    sample = create_sample(project, 'RNA-001', institution='原机构')
    sample.extra_metadata = {'asset_set': '甲', 'input_sample_id': '001', 'source_asset_id': 'synthetic'}
    db.session.commit()
    url = f'/api/projects/{project.id}/samples/registration'
    client = app.test_client()
    read = client.get(url, query_string={'asset_set': '甲', 'sample_id': '001'})
    assert read.json['sample']['sample_id'] == 'RNA-001'
    changed = client.post(url, json={'asset_set': '甲', 'sample_id': '001',
        'fields': {'institution': '最新机构', 'expected_values': {'institution': '原机构'}}})
    assert changed.status_code == 200
    stale = client.post(url, json={'asset_set': '甲', 'sample_id': '001',
        'fields': {'institution': '旧页面修改', 'expected_values': {'institution': '原机构'}}})
    assert stale.status_code == 409
    assert stale.json['details']['sample']['sample_id'] == 'RNA-001'
    assert stale.json['details']['sample']['extra_metadata']['input_sample_id'] == '001'
    assert stale.json['details']['sample']['extra_metadata']['source_asset_id'] == 'synthetic'


def test_registration_filter_is_before_paging_across_identity_chunks(context):
    app, _, project = context
    identifiers = [f'{index:03d}' for index in range(506)]
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name='甲.csv',
        storage_path='/synthetic/a.csv', metadata_json={'asset_set': '甲', 'validation': {
            'status': 'valid', 'summary': {'inputs': [{'samples': identifiers}]}}}))
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name='乙.csv',
        storage_path='/synthetic/b.csv', metadata_json={'asset_set': '乙', 'validation': {
            'status': 'valid', 'summary': {'inputs': [{'samples': ['001']}]}}}))
    db.session.add_all([SampleRecord(project_id=project.id, sample_id=value, sample_name=value,
        extra_metadata={'asset_set': '甲'}) for value in identifiers[:500]])
    db.session.add_all([
        SampleRecord(project_id=project.id, sample_id='RNA-001', sample_name='映射登记',
                     extra_metadata={'asset_set': '甲', 'input_sample_id': '001'}),
        SampleRecord(project_id=project.id, sample_id='001', sample_name='明确未关联',
                     extra_metadata={'asset_set': '乙', 'input_sample_id': None}),
    ])
    db.session.commit()
    project_id = project.id
    db.session.expunge_all()
    loaded = []
    def on_load(value, _): loaded.append(value.id)
    event.listen(SampleRecord, 'load', on_load)
    try:
        client = app.test_client()
        url = f'/api/projects/{project_id}/input-samples'
        result = client.get(url, query_string={'asset_set': '甲', 'registration_state': 'unregistered', 'page_size': 2})
        assert result.status_code == 200
        assert result.json['pagination']['total'] == 6
        assert [row['sample_id'] for row in result.json['samples']] == ['500', '501']
        second = client.get(url, query_string={'asset_set': '甲', 'registration_state': 'unregistered', 'page_size': 2, 'page': 2}).json
        assert [row['sample_id'] for row in second['samples']] == ['502', '503']
        multiple = client.get(url, query_string={'asset_set': '甲', 'registration_state': 'multiple'}).json
        assert multiple['pagination']['total'] == 1
        assert multiple['samples'][0]['sample_id'] == '001'
        registered = client.get(url, query_string={'asset_set': '甲', 'registration_state': 'registered', 'page_size': 2}).json
        assert registered['pagination']['total'] == 499
        assert not loaded, 'Filtering must use projected identities rather than hydrated registration rows.'
        other = client.get(url, query_string={'asset_set': '乙', 'registration_state': 'unregistered'}).json
        assert other['pagination']['total'] == 1
        assert other['samples'][0]['sample_id'] == '001'
        assert client.get(url, query_string={'registration_state': 'wrong'}).status_code == 400
    finally:
        event.remove(SampleRecord, 'load', on_load)


def test_duplicate_focus_and_export_share_exact_mapped_identity(context):
    app, _, project = context
    records = [
        ('001', '甲', {}), ('RNA-001', '甲', {'input_sample_id': '001'}),
        ('001', '甲', {'input_sample_id': None}), ('001', '甲', {'input_sample_id': '002'}),
        ('001', '乙', {}), ('001-extra', '甲', {}),
    ]
    db.session.add_all([SampleRecord(project_id=project.id, sample_id=original, sample_name=original,
        extra_metadata={'asset_set': dataset, **metadata}) for original, dataset, metadata in records])
    db.session.commit()
    client = app.test_client()
    scope = {'project_id': project.id, 'asset_set': '甲', 'input_sample_id': '001'}
    result = client.get('/api/samples', query_string={**scope, 'page_size': 1, 'page': 1})
    assert result.status_code == 200
    assert result.json['pagination']['total'] == 2
    rows = client.get('/api/samples', query_string=scope).json['samples']
    assert {row['sample_id'] for row in rows} == {'001', 'RNA-001'}
    exported = client.get('/api/samples/export', query_string={**scope, 'columns': 'business', 'format': 'csv'})
    assert exported.status_code == 200
    table = list(csv.DictReader(io.StringIO(exported.data.decode('utf-8-sig'))))
    assert {row['样本编号'] for row in table} == {'001', 'RNA-001'}
    assert client.get('/api/samples', query_string={'input_sample_id': '001'}).status_code == 400
