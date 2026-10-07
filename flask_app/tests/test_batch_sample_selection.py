"""Batch-aware UI choices must select the same identities in real PEP output."""
from pathlib import Path

import pandas as pd
import pytest

from flask_app.tests.test_sample_input_mapping import mapping_project, register
from flask_app.tests.test_profile_workflow import profile_app


def test_group_lookup_preserves_text_ids_and_exposes_distinct_batch_choices(profile_app, tmp_path):
    source = tmp_path / 'profile.csv'
    source.write_text('sample,batch,group\n001,001,A\n001,002,A\n002,002,B\n', encoding='utf-8')
    client = profile_app.test_client()
    payload = {'file_path': str(source), 'column': 'group'}
    plain = client.post('/api/script-hub/boxplot/group-values', json=payload)
    assert plain.status_code == 200
    assert plain.json['samples_by_value'] == {'A': ['001'], 'B': ['002']}
    scoped = client.post('/api/script-hub/boxplot/group-values', json={**payload, 'batch_field': 'batch'})
    assert scoped.status_code == 200
    assert scoped.json['samples_by_value'] == {'A': ['001::001', '002::001'], 'B': ['002::002']}
    assert scoped.json['sample_labels']['001::001'] == '001 / 001'
    assert scoped.json['sample_ids']['002::001'] == '001'
    bulk = client.post('/api/script-hub/boxplot/group-values-bulk', json={'file_path': str(source), 'columns': ['group']})
    assert bulk.json['groups']['group']['samples_by_value'] == plain.json['samples_by_value']


@pytest.mark.parametrize('batch_field,content', [
    ('missing', 'sample,batch,group\n001,A,A\n'),
    ('sample', 'sample,batch,group\n001,A,A\n'),
    ('batch', 'sample,batch,group\n001,,A\n'),
    ('batch', 'sample,batch,group\n001,A,A\n001,A,A\n'),
])
def test_invalid_batch_lookup_returns_actionable_error(profile_app, tmp_path, batch_field, content):
    source = tmp_path / 'profile.csv'
    source.write_text(content, encoding='utf-8')
    response = profile_app.test_client().post('/api/script-hub/boxplot/group-values', json={
        'file_path': str(source), 'column': 'group', 'batch_field': batch_field,
    })
    assert response.status_code == 400
    assert '批次' in response.json['message']


@pytest.mark.parametrize('mode,selection,expected', [
    ('sample', ['001'], {'批次甲::001', '批次乙::001'}),
    ('batch_sample', ['批次乙::001'], {'批次乙::001'}),
    ('batch_sample', ['批次甲::002', '批次乙::001'], {'批次甲::002', '批次乙::001'}),
])
def test_selected_batch_samples_reach_real_api_task_results(profile_app, mapping_project, tmp_path, monkeypatch, mode, selection, expected):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.routes.api_script_hub._common import _cache_context_from_script_request
    source = tmp_path / 'profile.csv'
    source.write_text('sample,batch,group\n001,批次甲,A\n002,批次甲,A\n001,批次乙,A\n002,批次乙,A\n', encoding='utf-8')
    original = source.read_bytes()
    register(mapping_project, 'profile', source)
    for batch in ['批次甲', '批次乙']:
        for sample in ['001', '002']:
            folder = tmp_path / 'pep' / batch / 'TRB'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f'{sample}__TRB.csv'
            pd.DataFrame({'CDR3(pep)': [f'CASS-{batch}-{sample}'], 'V': ['TRBV1'], 'J': ['TRBJ1'], 'copy': [3]}).to_csv(path, index=False)
            register(mapping_project, 'pep', path)
    monkeypatch.setattr(shared._script_executor, 'submit', lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result', lambda **kwargs: 'synthetic-result')
    payload = {'project_id': mapping_project.id, 'asset_set': 'Set2', 'module': 'pep-analysis',
        'selected_chains': ['TRB'], 'group_fields': ['group'], 'batch_field': 'batch',
        'selected_group_values': {'group': ['A']}, 'selected_samples_by_group': {'group': {'A': selection}},
        'group_sample_identity': mode, 'optional_steps': [], 'force_rerun': True}
    client = profile_app.test_client()
    response = client.post('/api/script-hub/jobs', json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json['task_id'])
    assert task['status'] == 'completed', task
    assert task['config_json']['group_sample_identity'] == mode
    with profile_app.test_request_context(json=payload):
        cached = _cache_context_from_script_request(payload, 'pep-analysis')
    assert cached['analysis_signature'] == task['analysis_signature']
    shared_matrix = pd.read_csv(Path(task['result']['output_base']) / 'Pep_shared' / 'TRB.csv')
    assert set(shared_matrix.columns[1:]) == expected
    output = pd.read_csv(next(Path(task['result']['output_base']).rglob('df_VJ_all.csv')))
    assert set(output['sample']) == expected
    assert set(output['Category']) == {'A'}
    assert client.get(task['result']['zip_url']).status_code == 200
    assert source.read_bytes() == original
    # Direct run endpoints must reject a stale/nonexistent selected identity before queuing.
    invalid = {**payload, 'group_sample_identity': 'batch_sample',
        'selected_samples_by_group': {'group': {'A': ['不存在::001']}}}
    rejected = client.post('/api/script-hub/pep-analysis/run', json=invalid)
    assert rejected.status_code == 400, rejected.json
    assert rejected.json['details']['invalid_samples'] == ['不存在::001']


def test_escaped_batch_identifiers_are_returned_without_collisions(profile_app, tmp_path):
    source = tmp_path / 'profile.csv'
    source.write_text('sample,batch,group\n001,批次::甲%,A\n甲%::001,批次,A\n', encoding='utf-8')
    response = profile_app.test_client().post('/api/script-hub/boxplot/group-values', json={
        'file_path': str(source), 'column': 'group', 'batch_field': 'batch',
    })
    assert response.status_code == 200
    assert set(response.json['samples_by_value']['A']) == {'批次%3A%3A甲%25::001', '批次::甲%25%3A%3A001'}
    assert set(response.json['sample_labels'].values()) == {'批次::甲% / 001', '批次 / 甲%::001'}


@pytest.mark.parametrize('mode', [['invalid'], 'batch_sample'])
def test_invalid_identity_mode_is_rejected_before_queuing(profile_app, mode):
    response = profile_app.test_client().post('/api/script-hub/pep-analysis/run', json={
        'group_sample_identity': mode,
    })
    assert response.status_code == 400
    assert response.json['details']['field'] == 'group_sample_identity'
