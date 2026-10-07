"""Exact input identities are restored in bounded batches, never with current replacements."""
import json
from unittest.mock import patch
import pytest
from sqlalchemy import event
from flask_app.models.database import Project, ProjectAsset, db
from flask_app.tests.test_data_management_contracts import context
from flask_app.tests.test_compact_input_selection import asset

def test_batch_restores_exact_history_and_aliases_with_one_lightweight_asset_query(context):
    _, service, project = context
    rows = [asset(project, f'clone-{n:03d}') for n in range(251)] + [
        asset(project, 'old-profile', 'datapoint', history=True),
        asset(project, 'old-rna', 'expression', history=True),
        asset(project, 'old-immune', 'cibersort', history=True)]
    db.session.add_all(rows); db.session.commit()
    project_id = project.id
    identifiers = [row.id for row in reversed(rows)]
    statements = []
    def record(_conn, _cursor, statement, _params, _ctx, _executemany): statements.append(statement)
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        result = service.resolve_input_selection(project_id, ' 甲 ', identifiers + identifiers[:2])
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert [row['id'] for row in result['assets']] == identifiers
    assert len(result['assets']) == 254 and result['asset_set'] == '甲'
    assert all(row['metadata']['asset_set'] == '甲' for row in result['assets'])
    assert all(row['metadata']['superseded'] for row in result['assets'][:3])
    assert result['assets'][0]['metadata']['content_version'] == 'version-old-immune'
    assert 'samples' not in json.dumps(result) and 'upload_operation' not in json.dumps(result)
    assert len(json.dumps(result).encode()) < 180000
    queries = [statement for statement in statements if 'FROM project_assets' in statement]
    assert len(queries) == 1
    assert not any('project_assets.metadata_json AS project_assets_metadata_json' in statement for statement in queries)

@pytest.mark.parametrize('unavailable', ['missing', 'foreign', 'other-set', 'attachment'])
def test_any_unavailable_identity_rejects_the_entire_batch_without_returning_partial_assets(context, unavailable):
    app, _, project = context
    other = Project(name='其他项目'); db.session.add(other); db.session.flush()
    old = asset(project, 'old', 'profile', history=True)
    db.session.add_all([old, asset(project, 'current', 'profile'), asset(other, 'foreign'),
        asset(project, 'other-set', dataset='乙'), asset(project, 'attachment', 'project_file')])
    db.session.commit()
    response = app.test_client().post(f'/api/projects/{project.id}/input-selection/resolve',
        json={'asset_set': '甲', 'asset_ids': ['old', unavailable]})
    assert response.status_code == 400
    assert 'assets' not in response.json
    assert db.session.get(ProjectAsset, old.id).metadata_json['content_version'] == 'version-old'

@pytest.mark.parametrize('payload', [None, [], {'asset_set': 7, 'asset_ids': []},
    {'asset_set': '', 'asset_ids': []}, {'asset_set': '甲'}, {'asset_set': '甲', 'asset_ids': 'a'},
    {'asset_set': '甲', 'asset_ids': [7]}, {'asset_set': '甲', 'asset_ids': ['']},
    {'asset_set': '甲', 'asset_ids': [' padded']}, {'asset_set': '甲', 'asset_ids': ['a' * 37]},
    {'asset_set': '甲', 'asset_ids': ['a'] * 501}])
def test_invalid_or_oversize_requests_are_client_errors(context, payload):
    app, _, project = context
    response = app.test_client().post(f'/api/projects/{project.id}/input-selection/resolve', json=payload)
    assert response.status_code == 400
    assert 'assets' not in response.json

def test_empty_explicit_selection_remains_empty_and_500_id_boundary_is_supported(context):
    app, _, project = context
    identifiers = [f'clone-{n:03d}' for n in range(500)]
    db.session.add_all([asset(project, identifier) for identifier in identifiers]); db.session.commit()
    client = app.test_client(); url = f'/api/projects/{project.id}/input-selection/resolve'
    empty = client.post(url, json={'asset_set': '甲', 'asset_ids': []})
    assert empty.status_code == 200 and empty.json == {'asset_set': '甲', 'assets': []}
    full = client.post(url, json={'asset_set': '甲', 'asset_ids': identifiers})
    assert full.status_code == 200 and [row['id'] for row in full.json['assets']] == identifiers

def test_restore_checks_project_ownership_and_synchronizes_terminal_validation(context):
    app, _, project = context
    db.session.add(asset(project, 'a')); db.session.commit()
    with patch('flask_app.services.input_validation_cache.synchronize_validation_jobs') as sync:
        response = app.test_client().post(f'/api/projects/{project.id}/input-selection/resolve',
            json={'asset_set': '甲', 'asset_ids': ['a']})
    assert response.status_code == 200
    sync.assert_called_once_with(project.id)
    app.config['REQUIRE_LOGIN'] = True
    forbidden = app.test_client().post(f'/api/projects/{project.id}/input-selection/resolve',
        json={'asset_set': '甲', 'asset_ids': ['a']})
    assert forbidden.status_code == 400 and 'assets' not in forbidden.json
