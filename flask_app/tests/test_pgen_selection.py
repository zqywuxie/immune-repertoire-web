"""Verify selected Pgen sample identities with the container's real SoNNia model."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register


def test_explicit_sample_column_is_used_by_group_lookup_and_validation(profile_app, tmp_path):
    source = tmp_path / 'profile.csv'
    source.write_text('sample,编号,batch,group\nshadow-a,001,001,A\nshadow-b,001,002,A\n', encoding='utf-8')
    client = profile_app.test_client()
    payload = {'file_path': str(source), 'column': 'group', 'batch_field': 'batch', 'sample_col': '编号'}
    response = client.post('/api/script-hub/boxplot/group-values', json=payload)
    assert response.status_code == 200, response.json
    assert response.json['sample_column'] == '编号'
    assert response.json['samples_by_value'] == {'A': ['001::001', '002::001']}
    from flask_app.services.input_quality import inspect_input_quality
    plain = inspect_input_quality([], str(source), "", "", "batch")
    selected = inspect_input_quality([], str(source), "", "", "batch", "编号")
    restored = inspect_input_quality([], str(source), "", "", "batch")
    assert plain['inputs'][0]['samples'] == restored['inputs'][0]['samples'] == ['shadow-a', 'shadow-b']
    assert selected['inputs'][0]['samples'] == ['001']
    assert selected['inputs'][0]['sample_count'] == 2
    assert selected['inputs'][0]['sample_column'] == '编号'
    invalid_quality = inspect_input_quality([], str(source), "", "", "batch", "missing")
    assert invalid_quality['inputs'][0]['status'] == 'invalid'
    assert '所选样本编号列' in invalid_quality['errors'][0]

    from flask_app.routes.api_script_hub._common import _validate_selected_samples_against_group_values
    validation = {'profile_path': str(source), 'sample_col': '编号', 'batch_field': 'batch',
        'group_sample_identity': 'batch_sample', 'selected_group_values': {'group': ['A']},
        'selected_samples_by_group': {'group': {'A': ['002::001']}}}
    _validate_selected_samples_against_group_values(validation)
    invalid = client.post('/api/script-hub/boxplot/group-values', json={**payload, 'sample_col': 'missing'})
    assert invalid.status_code == 400
    assert invalid.json['details']['field'] == 'sample_col'


def test_pgen_batch_choice_reaches_real_model_api_outputs_and_download(profile_app, mapping_project, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services.pgen_analysis_service import PgenAnalysisService
    from flask_app.routes.api_script_hub._common import _cache_context_from_script_request
    status = PgenAnalysisService.dependency_status()
    assert status['available'], status
    profile = tmp_path / 'profile.csv'
    profile.write_text('sample,编号,batch,group\nshadow-a,001,批次甲,A\nshadow-b,001,批次乙,A\n', encoding='utf-8')
    original = profile.read_bytes()
    register(mapping_project, 'profile', profile)
    paths = []
    for batch in ['批次甲', '批次乙']:
        path = tmp_path / 'pep' / batch / 'TRA' / '001__TRA.csv'
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({'CDR3(pep)': ['CAVRDSNYQLIW', 'CAVMDSNYQLIW'],
            'V': ['TRAV1-2', 'TRAV1-2'], 'J': ['TRAJ33', 'TRAJ33'], 'copy': [7, 3]}).to_csv(path, index=False)
        register(mapping_project, 'pep', path)
        paths.append(path)
    calls = []
    prepare = PgenAnalysisService._prepare_pep_dataframe
    def record(path):
        calls.append(Path(path))
        return prepare(path)
    monkeypatch.setattr(PgenAnalysisService, '_prepare_pep_dataframe', staticmethod(record))
    monkeypatch.setattr(shared._script_executor, 'submit', lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result', lambda **kwargs: 'synthetic-result')
    payload = {'project_id': mapping_project.id, 'asset_set': 'Set2', 'module': 'pgen-analysis',
        'selected_chains': ['TRA'], 'sample_col': '编号', 'batch_field': 'batch', 'species': 'human',
        'distribution_category_col': 'group', 'selected_group_values': {'group': ['A']},
        'selected_samples_by_group': {'group': {'A': ['批次乙::001']}},
        'group_sample_identity': 'batch_sample', 'force_rerun': True}
    client = profile_app.test_client()
    response = client.post('/api/script-hub/jobs', json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json['task_id'])
    assert task['status'] == 'completed', task
    assert calls == [paths[1]], 'Unselected files must not be passed to model preprocessing'
    assert task['config_json']['group_sample_identity'] == 'batch_sample'
    assert task['config_json']['input_alignment']['alignments'][0]['matched_count'] == 1
    with profile_app.test_request_context(json=payload):
        cached = _cache_context_from_script_request(payload, 'pgen-analysis')
    assert cached['analysis_signature'] == task['analysis_signature']
    output = Path(task['result']['output_base'])
    summary = pd.read_csv(output / 'Pgen_mean.csv', dtype={'编号': str})
    assert summary[['编号', 'batch', 'group']].to_dict('records') == [{'编号': '001', 'batch': '批次乙', 'group': 'A'}]
    details = pd.read_csv(output / 'Pgen_detail_index.csv', dtype={'sample': str})
    assert details[['sample', 'batch']].to_dict('records') == [{'sample': '001', 'batch': '批次乙'}]
    detail_path = Path(details['detail_path'].iloc[0])
    assert detail_path.is_relative_to(output)
    values = pd.read_csv(detail_path)
    assert set(values['CDR3(pep)']) == {'CAVRDSNYQLIW', 'CAVMDSNYQLIW'}
    assert np.isfinite(values['Pgen']).all()
    assert (values['Pgen'] > 0).all() and (values['Pgen'] <= 1).all()
    np.testing.assert_allclose(float(summary['Pgen_TRA'].iloc[0]), values['Pgen'].mean(), rtol=1e-10)
    assert client.get(task['result']['zip_url']).status_code == 200
    assert profile.read_bytes() == original
    invalid = {**payload, 'selected_samples_by_group': {'group': {'A': ['不存在::001']}}}
    rejected = client.post('/api/script-hub/pgen-analysis/run', json=invalid)
    assert rejected.status_code == 400, rejected.json
    assert rejected.json['details']['invalid_samples'] == ['不存在::001']


@pytest.mark.parametrize('mode', ['wrong', ['invalid']])
def test_invalid_pgen_identity_mode_is_not_queued(profile_app, tmp_path, mode):
    profile = tmp_path / 'profile.csv'
    profile.write_text('sample,group\n001,A\n', encoding='utf-8')
    path = tmp_path / '001__TRA.csv'
    path.write_text('CDR3(pep),V,J\nCAVRDSNYQLIW,TRAV1-2,TRAJ33\n', encoding='utf-8')
    response = profile_app.test_client().post('/api/script-hub/pgen-analysis/run', json={
        'pep_paths': [str(path)], 'profile_path': str(profile), 'selected_chains': ['TRA'],
        'group_sample_identity': mode,
    })
    assert response.status_code == 400
    assert response.json['details']['field'] == 'group_sample_identity'
