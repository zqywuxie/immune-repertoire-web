"""Regression coverage for Profile-only inputs and data-set selection."""
import sys
from importlib import import_module
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
from flask import Flask

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def profile_app(tmp_path):
    api = import_module('flask_app.routes.api_script_hub')
    from flask_app.models.database import db
    app = Flask(__name__, root_path=str(tmp_path))
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, RESULTS_FOLDER=str(tmp_path / 'results'))
    db.init_app(app)
    app.register_blueprint(api.script_hub_bp)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_selected_profile_set_is_used_for_inspection_and_execution(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='Profile only')
    db.session.add(project)
    db.session.flush()
    for name, sample in [('Set1', 'old'), ('Set2', 'selected')]:
        path = tmp_path / f'{name}.csv'
        path.write_text(f'sample,group,metric\n{sample}1,A,1\n{sample}2,B,8\n', encoding='utf-8')
        db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=path.name,
                                   storage_path=str(path), size=path.stat().st_size, metadata_json={'asset_set': name}))
    db.session.commit()
    client = profile_app.test_client()
    selection = {'project_id': project.id, 'asset_set': 'Set2'}
    response = client.post('/api/script-hub/data-selection/inspect', json=selection)
    assert response.status_code == 200
    data = response.get_json()
    assert Path(data['profile_path']).name == 'Set2.csv'
    assert data['pep_file_count'] == 0
    assert data['sample_count'] == 2
    assert data['samples'] == ['selected1', 'selected2']
    response = client.post('/api/script-hub/profile/inspect', json=selection)
    assert response.status_code == 200
    assert Path(response.get_json()['datapoint_path']).name == 'Set2.csv'
    executor = Mock()
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    response = client.post('/api/script-hub/profile/run', json={**selection, 'grouptype_fields': ['group'],
                           'param_begin': 'metric', 'param_over': 'metric', 'force_rerun': True})
    assert response.status_code == 200
    assert Path(executor.submit.call_args.kwargs['datapoint_path']).name == 'Set2.csv'
    assert executor.submit.call_args.kwargs['grouptype_fields'] == ['group']


def test_topclone_run_forwards_batch_field_to_worker(profile_app, tmp_path, monkeypatch):
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    pep_root = tmp_path / 'pep'
    for batch in ('batch_001', 'batch_002'):
        chain_dir = pep_root / batch / 'TRA'
        chain_dir.mkdir(parents=True)
        pd.DataFrame({'CDR3(pep)': ['CASS'], 'copy': [1], 'v': ['TRAV1'], 'j': ['TRAJ1']}).to_csv(
            chain_dir / 'S01__TRA.csv', index=False
        )
    profile_path = tmp_path / 'profile.csv'
    pd.DataFrame({'sample': ['S01', 'S01'], 'batch': ['batch_001', 'batch_002'], 'group': ['A', 'B']}).to_csv(
        profile_path, index=False
    )
    executor = Mock()
    monkeypatch.setattr(routes, '_pep_paths_from_request', lambda _data: [str(pep_root)])
    monkeypatch.setattr(routes, '_primary_pep_path_from_request', lambda *_args: str(pep_root))
    monkeypatch.setattr(routes, '_profile_path_from_request', lambda *_args: str(profile_path))
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **_kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())

    client = profile_app.test_client()
    payload = {
        'pep_data_path': str(pep_root),
        'datapoint_path': str(profile_path),
        'mode': 'trace',
        'selected_chains': ['TRA'],
        'force_rerun': True,
    }
    response = client.post('/api/script-hub/topclone/run', json=payload)

    assert response.status_code == 400
    assert 'sample_conflicts' in response.get_json()['details']
    executor.submit.assert_not_called()

    response = client.post('/api/script-hub/topclone/run', json={**payload, 'batch_field': 'batch'})

    assert response.status_code == 200
    assert executor.submit.call_args.kwargs['batch_field'] == 'batch'


def test_profile_composition_inspection_and_run_use_selected_profile_asset(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='Profile composition')
    db.session.add(project)
    db.session.flush()
    selected_path = tmp_path / 'Selected.csv'
    pd.DataFrame({
        'sample': ['001', '002'], 'group': ['A', 'B'],
        'TRA_Percent': [0.4, 0.2], 'TRB_Percent': [0.6, 0.8],
        'IGHM_percent_by_reads': [0.7, 0.5], 'IGHA_percent_by_reads': [0.3, 0.5],
    }).to_csv(selected_path, index=False)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=selected_path.name,
                                storage_path=str(selected_path), size=selected_path.stat().st_size,
                                metadata_json={'asset_set': 'Selected'}))
    db.session.commit()
    client = profile_app.test_client()
    selection = {'project_id': project.id, 'asset_set': 'Selected'}
    inspection = client.post('/api/script-hub/profile/inspect', json=selection)
    assert inspection.status_code == 200
    assert inspection.json['composition_columns']['reads']['chains'] == ['TRA_Percent', 'TRB_Percent']
    assert inspection.json['composition_columns']['reads']['subclass_columns'] == ['IGHM_percent_by_reads', 'IGHA_percent_by_reads']

    executor = Mock()
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    response = client.post('/api/script-hub/profile/run', json={
        **selection, 'analysis_type': 'composition', 'group_column': 'group',
        'group_order': ['B', 'A'], 'subclass_measure': 'reads', 'force_rerun': True,
    })
    assert response.status_code == 200
    assert executor.submit.call_args.args[0] is routes._run_profile_composition_task
    assert Path(executor.submit.call_args.kwargs['datapoint_path']).name == 'Selected.csv'
    assert executor.submit.call_args.kwargs['group_column'] == 'group'


def test_profile_composition_task_registers_charts_and_download(tmp_path, monkeypatch):
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    profile_path = tmp_path / 'profile.csv'
    pd.DataFrame({
        'sample': ['001', '002', '003', '004'], 'group': ['A', 'A', 'B', 'B'],
        'TRA_Percent': [0.2, 0.4, 0.7, 0.3], 'TRB_Percent': [0.8, 0.6, 0.3, 0.7],
        'IGHM_percent_by_reads': [0.6, 0.2, 0.4, 0.5], 'IGHA_percent_by_reads': [0.4, 0.8, 0.6, 0.5],
    }).to_csv(profile_path, index=False)
    completed = Mock()
    monkeypatch.setattr(routes, 'script_output_parent', lambda task, base, app=None: tmp_path / 'outputs')
    monkeypatch.setattr(routes, '_record_stage', Mock())
    monkeypatch.setattr(routes, '_get_task_state', lambda task: {'history': []})
    monkeypatch.setattr(routes, '_complete_script_task', completed)

    routes._run_profile_composition_task(
        'task-composition', results_root=tmp_path, datapoint_path=str(profile_path),
        group_column='group', group_order=['A', 'B'], measure='reads',
    )

    assert completed.call_args.kwargs['module_name'] == 'profile-composition'
    result = completed.call_args.kwargs['result']
    assert len(result['png_urls']) == 2
    assert len(result['csv_urls']) == 3
    assert result['zip_url'].endswith('.zip')
    assert Path(result['output_base']).is_dir()


def test_profile_csr_inspection_and_run_use_selected_profile_asset(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='Profile CSR')
    db.session.add(project)
    db.session.flush()
    selected_path = tmp_path / 'CSR.csv'
    pd.DataFrame({
        'sample': ['001', '002', '003', '004'], 'group': ['A', 'A', 'B', 'B'],
        'IGHM-IGHD_CSR_ratio': [0.1, 0.2, 0.4, 0.5],
        'IGHM-IGHD_CSR0': [1, 2, 3, 4],
    }).to_csv(selected_path, index=False)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=selected_path.name,
                                storage_path=str(selected_path), size=selected_path.stat().st_size,
                                metadata_json={'asset_set': 'CSR'}))
    db.session.commit()
    client = profile_app.test_client()
    selection = {'project_id': project.id, 'asset_set': 'CSR'}
    inspection = client.post('/api/script-hub/profile/inspect', json=selection)
    assert inspection.status_code == 200
    assert inspection.json['csr_measures'] == {
        'CSR_ratio': ['IGHM-IGHD_CSR_ratio'], 'CSR0': ['IGHM-IGHD_CSR0'],
    }

    executor = Mock()
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    response = client.post('/api/script-hub/profile/run', json={
        **selection, 'analysis_type': 'csr', 'group_column': 'group',
        'group_order': ['B', 'A'], 'csr_measure': 'auto', 'force_rerun': True,
    })
    assert response.status_code == 200
    assert executor.submit.call_args.args[0] is routes._run_profile_csr_task
    assert Path(executor.submit.call_args.kwargs['datapoint_path']).name == 'CSR.csv'
    assert executor.submit.call_args.kwargs['group_column'] == 'group'


def test_profile_csr_task_registers_figures_tables_and_download(tmp_path, monkeypatch):
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    profile_path = tmp_path / 'profile-csr.csv'
    pd.DataFrame({
        'sample': ['A1', 'A2', 'A3', 'B1', 'B2', 'B3'], 'group': ['A'] * 3 + ['B'] * 3,
        'IGHM-IGHD_CSR_ratio': [0.1, 0.2, 0.3, 0.7, 0.8, 0.9],
        'IGHA-IGHG3_CSR_ratio': [0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
    }).to_csv(profile_path, index=False)
    completed = Mock()
    monkeypatch.setattr(routes, 'script_output_parent', lambda task, base, app=None: tmp_path / 'outputs')
    monkeypatch.setattr(routes, '_record_stage', Mock())
    monkeypatch.setattr(routes, '_get_task_state', lambda task: {'history': []})
    monkeypatch.setattr(routes, '_complete_script_task', completed)

    routes._run_profile_csr_task(
        'task-csr', results_root=tmp_path, datapoint_path=str(profile_path),
        group_column='group', group_order=['A', 'B'], measure='auto',
    )

    assert completed.call_args.kwargs['module_name'] == 'profile-csr'
    result = completed.call_args.kwargs['result']
    assert len(result['png_urls']) == 3
    assert len(result['csv_urls']) == 4
    assert result['zip_url'].endswith('.zip')


def test_igh_subclass_topclone_run_uses_selected_project_igh_and_profile_assets(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='IGH subclass TopClone')
    db.session.add(project)
    db.session.flush()
    profile_path = tmp_path / 'Profile.csv'
    pd.DataFrame({'sample': ['A1', 'A2', 'B1', 'B2'], 'group': ['A', 'A', 'B', 'B'], 'batch': ['batch-1'] * 4}).to_csv(profile_path, index=False)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=profile_path.name,
        storage_path=str(profile_path), size=profile_path.stat().st_size, metadata_json={'asset_set': 'IGH'}))
    pep_paths = []
    for sample in ['A1', 'A2', 'B1', 'B2']:
        pep_path = tmp_path / f'{sample}__IGH.csv'
        pd.DataFrame({'c_call': ['IGHM*01'], 'CDR3(pep)': [f'{sample}-cdr3'], 'copy': [4]}).to_csv(pep_path, index=False)
        pep_paths.append(pep_path)
        db.session.add(ProjectAsset(project_id=project.id, asset_type='pep', original_name=pep_path.name,
            storage_path=str(pep_path), size=pep_path.stat().st_size, metadata_json={'asset_set': 'IGH'}))
    db.session.commit()

    executor = Mock()
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    response = profile_app.test_client().post('/api/script-hub/topclone/run', json={
        'project_id': project.id, 'asset_set': 'IGH', 'analysis_type': 'igh_subclass_topclone',
        'group_field': 'group', 'batch_field': 'batch', 'group_order': ['B', 'A'], 'force_rerun': True,
    })
    assert response.status_code == 200
    assert executor.submit.call_args.args[0] is routes._run_igh_subclass_topclone_task
    assert set(executor.submit.call_args.kwargs['pep_paths']) == {str(path) for path in pep_paths}
    assert Path(executor.submit.call_args.kwargs['datapoint_path']) == profile_path
    assert executor.submit.call_args.kwargs['group_field'] == 'group'
    assert executor.submit.call_args.kwargs['batch_field'] == 'batch'


def test_pgen_run_passes_all_selected_pep_assets_and_batch_field(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='Pgen batch inputs')
    db.session.add(project)
    db.session.flush()
    profile_path = tmp_path / 'Profile.csv'
    pd.DataFrame({
        'sample': ['S1', 'S2', 'S1', 'S2'],
        'batch': ['batch-a', 'batch-a', 'batch-b', 'batch-b'],
        'group': ['A', 'A', 'B', 'B'],
    }).to_csv(profile_path, index=False)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=profile_path.name,
        storage_path=str(profile_path), size=profile_path.stat().st_size, metadata_json={'asset_set': 'PGEN'}))
    pep_paths = []
    for batch in ['batch-a', 'batch-b']:
        for sample in ['S1', 'S2']:
            pep_path = tmp_path / batch / 'TRA' / f'{sample}__TRA.csv'
            pep_path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({'CDR3(pep)': ['CASS'], 'V': ['TRAV1'], 'J': ['TRAJ1']}).to_csv(pep_path, index=False)
            pep_paths.append(pep_path)
            db.session.add(ProjectAsset(project_id=project.id, asset_type='pep', original_name=pep_path.name,
                storage_path=str(pep_path), size=pep_path.stat().st_size, metadata_json={'asset_set': 'PGEN'}))
    db.session.commit()

    executor = Mock()
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    response = profile_app.test_client().post('/api/script-hub/pgen-analysis/run', json={
        'project_id': project.id, 'asset_set': 'PGEN', 'selected_chains': ['TRA'],
        'sample_col': 'sample', 'distribution_category_col': 'group', 'batch_field': 'batch',
        'selected_group_values': {'group': ['A']},
        'selected_samples_by_group': {'group': {'A': ['S1']}},
        'force_rerun': True,
    })

    assert response.status_code == 200
    assert executor.submit.call_args.args[0] is routes._run_pgen_analysis_task
    assert set(executor.submit.call_args.kwargs['pep_paths']) == {str(path) for path in pep_paths}
    assert executor.submit.call_args.kwargs['batch_field'] == 'batch'
    assert executor.submit.call_args.kwargs['selected_group_values'] == {'group': ['A']}
    assert executor.submit.call_args.kwargs['selected_samples_by_group'] == {'group': {'A': ['S1']}}


def test_pep_run_passes_all_selected_assets_and_group_sample_filters(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='PEP multiple selected files')
    db.session.add(project)
    db.session.flush()
    profile_path = tmp_path / 'Profile.csv'
    pd.DataFrame({'sample': ['S1', 'S2'], 'group': ['A', 'B']}).to_csv(profile_path, index=False)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=profile_path.name,
        storage_path=str(profile_path), size=profile_path.stat().st_size, metadata_json={'asset_set': 'PEP'}))
    pep_paths = []
    for sample in ['S1', 'S2']:
        pep_path = tmp_path / f'{sample}__TRB.csv'
        pd.DataFrame({'CDR3(pep)': [f'CASS-{sample}'], 'V': ['TRBV1'], 'J': ['TRBJ1'], 'copy': [3]}).to_csv(pep_path, index=False)
        pep_paths.append(pep_path)
        db.session.add(ProjectAsset(project_id=project.id, asset_type='pep', original_name=pep_path.name,
            storage_path=str(pep_path), size=pep_path.stat().st_size, metadata_json={'asset_set': 'PEP'}))
    db.session.commit()

    executor = Mock()
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    response = profile_app.test_client().post('/api/script-hub/pep-analysis/run', json={
        'project_id': project.id, 'asset_set': 'PEP', 'selected_chains': ['TRB'],
        'group_fields': ['group'], 'selected_group_values': {'group': ['A']},
        'selected_samples_by_group': {'group': {'A': ['S1']}}, 'optional_steps': ['9', '10', '11'], 'force_rerun': True,
    })

    assert response.status_code == 200
    assert executor.submit.call_args.args[0] is routes._run_pep_analysis_task
    assert set(executor.submit.call_args.kwargs['pep_paths']) == {str(path) for path in pep_paths}
    assert executor.submit.call_args.kwargs['selected_group_values'] == {'group': ['A']}
    assert executor.submit.call_args.kwargs['selected_samples_by_group'] == {'group': {'A': ['S1']}}
    assert executor.submit.call_args.kwargs['optional_steps'] == {9, 10, 11}


def test_pep_run_allows_duplicate_samples_when_batch_field_is_selected(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='PEP batch identities')
    db.session.add(project)
    db.session.flush()
    profile_path = tmp_path / 'Profile.csv'
    pd.DataFrame({
        'sample': ['S1', 'S1'], 'batch': ['batch-a', 'batch-b'], 'group': ['A', 'B'],
    }).to_csv(profile_path, index=False)
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=profile_path.name,
        storage_path=str(profile_path), size=profile_path.stat().st_size, metadata_json={'asset_set': 'PEP'}))
    pep_paths = []
    for batch in ['batch-a', 'batch-b']:
        pep_path = tmp_path / batch / 'TRB' / 'S1__TRB.csv'
        pep_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({'CDR3(pep)': [f'CASS-{batch}'], 'V': ['TRBV1'], 'J': ['TRBJ1'], 'copy': [3]}).to_csv(pep_path, index=False)
        pep_paths.append(pep_path)
        db.session.add(ProjectAsset(project_id=project.id, asset_type='pep', original_name=pep_path.name,
            storage_path=str(pep_path), size=pep_path.stat().st_size, metadata_json={'asset_set': 'PEP'}))
    db.session.commit()

    executor = Mock()
    monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    response = profile_app.test_client().post('/api/script-hub/pep-analysis/run', json={
        'project_id': project.id, 'asset_set': 'PEP', 'selected_chains': ['TRB'],
        'group_fields': ['group'], 'batch_field': 'batch', 'force_rerun': True,
    })

    assert response.status_code == 200
    assert set(executor.submit.call_args.kwargs['pep_paths']) == {str(path) for path in pep_paths}
    assert executor.submit.call_args.kwargs['batch_field'] == 'batch'
    invalid = profile_app.test_client().post('/api/script-hub/pep-analysis/run', json={
        'project_id': project.id, 'asset_set': 'PEP', 'selected_chains': ['TRB'],
        'group_fields': ['group'], 'batch_field': 'missing', 'force_rerun': True,
    })
    assert invalid.status_code == 400
    assert invalid.get_json()['details']['field'] == 'batch_field'
    assert executor.submit.call_count == 1


def test_igh_subclass_topclone_task_registers_chart_tables_and_archive(tmp_path, monkeypatch):
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    profile_path = tmp_path / 'Profile.csv'
    pd.DataFrame({'sample': ['A1', 'A2', 'B1', 'B2'], 'group': ['A', 'A', 'B', 'B']}).to_csv(profile_path, index=False)
    pep_root = tmp_path / 'pep' / 'IGH'
    pep_root.mkdir(parents=True)
    pep_paths = []
    for index, sample in enumerate(['A1', 'A2', 'B1', 'B2']):
        pep_path = pep_root / f'{sample}__IGH.csv'
        pd.DataFrame({'c_call': ['IGHM*01', 'IGHM*01'], 'CDR3(pep)': [f'{sample}-1', f'{sample}-2'], 'copy': [index + 1, index + 2]}).to_csv(pep_path, index=False)
        pep_paths.append(str(pep_path))
    completed = Mock()
    monkeypatch.setattr(routes, 'script_output_parent', lambda task, base, app=None: tmp_path / 'outputs')
    monkeypatch.setattr(routes, '_record_stage', Mock())
    monkeypatch.setattr(routes, '_get_task_state', lambda task: {'history': []})
    monkeypatch.setattr(routes, '_complete_script_task', completed)

    routes._run_igh_subclass_topclone_task(
        'task-igh-topclone', results_root=tmp_path, pep_paths=pep_paths,
        datapoint_path=str(profile_path), group_field='group', group_order=['A', 'B'],
    )

    assert completed.call_args.kwargs['module_name'] == 'igh-subclass-topclone'
    result = completed.call_args.kwargs['result']
    assert len(result['png_urls']) == 1
    assert len(result['csv_urls']) == 4
    assert result['zip_url'].endswith('.zip')


def test_topclone_task_publishes_effect_heatmap_and_statistics(tmp_path, monkeypatch):
    from types import SimpleNamespace

    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    output = tmp_path / 'outputs' / 'topclone-job'
    output.mkdir(parents=True)
    stats = output / 'pairwise_statistics.csv'
    stats.write_text('chain,top_n,p_value,q_value\nTRA,10,0.01,0.02\n', encoding='utf-8')
    effect_stats = output / 'topclone_effect_heatmap_stats_raw_p.csv'
    effect_stats.write_text('chain,top_n,p_value\nTRA,10,0.01\n', encoding='utf-8')
    effect_png = output / 'topclone_effect_heatmap_raw_p.png'
    effect_png.write_bytes(b'png')
    report = SimpleNamespace(
        job_id=output.name,
        output_base=output,
        topclone_csv_path=None,
        boxplot_report=SimpleNamespace(png_paths=[], pvalue_paths=[], csv_paths=[], viewer_path=None),
        per_sample_files=[],
        metadata={"mode": "trace", "chains": ["TRA"], "sample_count": 2,
                  "profile_sample_count": 2, "excluded_unmatched_sample_count": 0,
                  "top_clone_values": [10, 20, 50, 100]},
        stats_csv_path=str(stats),
        effect_heatmap_paths=[str(effect_png)],
        effect_statistics_paths=[str(effect_stats)],
    )

    class FakeService:
        def __init__(self, *, output_parent):
            assert Path(output_parent) == output.parent

        def generate_report(self, **kwargs):
            captured.update(kwargs)
            return report

    captured = {}
    completed = Mock()
    monkeypatch.setattr(routes, 'TopCloneService', FakeService)
    monkeypatch.setattr(routes, 'script_output_parent', lambda task, base, app=None: output.parent)
    monkeypatch.setattr(routes, '_record_stage', Mock())
    monkeypatch.setattr(routes, '_get_task_state', lambda task: {'history': []})
    monkeypatch.setattr(routes, '_complete_script_task', completed)

    routes._run_topclone_task(
        'task-topclone-effect', results_root=tmp_path,
        pep_data_path=str(tmp_path / 'pep'), datapoint_path=str(tmp_path / 'profile.csv'),
        mode='trace', group_field='group', batch_field='batch', group_order='A,B', selected_chains=['TRA'],
    )

    assert captured['batch_field'] == 'batch'
    result = completed.call_args.kwargs['result']
    assert any(url.endswith('/topclone_effect_heatmap_raw_p.png') for url in result['png_urls'])
    assert any(url.endswith('/pairwise_statistics.csv') for url in result['pvalue_urls'])
    assert any(url.endswith('/topclone_effect_heatmap_stats_raw_p.csv') for url in result['pvalue_urls'])
    assert '优势克隆中位数比值热图' in (output / 'viewer.html').read_text(encoding='utf-8')


def test_profile_boxplot_produces_real_report_and_tables(tmp_path):
    from flask_app.services.boxplot_service import BoxPlotService
    profile = tmp_path / 'profile.csv'
    pd.DataFrame({'sample': ['A1', 'A2', 'A3', 'B1', 'B2', 'B3'],
                  'group': ['A'] * 3 + ['B'] * 3, 'metric': [1, 2, 3, 8, 9, 10]}).to_csv(profile, index=False)
    report = BoxPlotService(output_parent=tmp_path / 'results').generate_report(
        datapoint_path=str(profile), classification_begin='group', classification_over='group',
        grouptype_fields=['group'], param_begin='metric', param_over='metric')
    assert report.png_paths and report.csv_paths
    assert all(Path(path).stat().st_size > 0 for path in report.png_paths + report.csv_paths)
    assert Path(report.viewer_path).is_file()
    assert Path(report.zip_path).is_file()


def test_four_inputs_remain_scoped_to_dataset(profile_app, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db
    project = Project(name='四类输入')
    db.session.add(project); db.session.flush()
    paths = {}
    for dataset in ['Set1', 'Set2']:
        for kind in ['datapoint', 'pep', 'transcriptome', 'deconvolution']:
            path = tmp_path / f'{dataset}-{kind}.csv'
            path.write_text('sample,group,value\ns1,A,0.2\ns2,B,0.3\n', encoding='utf-8')
            paths[dataset, kind] = str(path)
            db.session.add(ProjectAsset(project_id=project.id, asset_type=kind, original_name=path.name,
                storage_path=str(path), size=path.stat().st_size, metadata_json={'asset_set': dataset}))
    db.session.commit()
    common = import_module('flask_app.routes.api_script_hub._common')
    assets = common._collect_project_script_hub_assets(project.id, 'Set2')
    assert assets['profile_path'] == paths['Set2', 'datapoint']
    assert assets['deconvolution_path'] == paths['Set2', 'deconvolution']
    assert assets['transcriptome_path'] == paths['Set2', 'transcriptome']
    assert assets['pep_paths'] == [paths['Set2', 'pep']]
    response = profile_app.test_client().post('/api/script-hub/data-selection/inspect',
        json={'project_id': project.id, 'asset_set': 'Set2'})
    assert response.status_code == 200
    assert response.json['deconvolution_path'] == paths['Set2', 'deconvolution']


@pytest.mark.parametrize("suffix", [".csv", ".tsv", ".xlsx"])
def test_profile_report_preserves_zero_prefixed_selected_identifiers(profile_app, tmp_path, suffix):
    from flask_app.services.boxplot_service import BoxPlotService
    frame = pd.DataFrame({"sample": [f"{i:03d}" for i in range(1, 9)],
                          "group": ["A"] * 4 + ["B"] * 4, "metric": [i * i + i for i in range(1, 9)]})
    path = tmp_path / ("profile" + suffix)
    if suffix == ".xlsx":
        frame.to_excel(path, index=False)
    else:
        frame.to_csv(path, index=False, sep="\t" if suffix == ".tsv" else ",")
    selected = ["001", "003", "005", "007"]
    report = BoxPlotService(output_parent=tmp_path / "out").generate_report(
        datapoint_path=str(path), grouptype_fields=["group"], param_begin="metric", param_over="metric",
        selected_samples=selected,
        selected_samples_by_group={"group": {"A": selected[:2], "B": selected[2:]}},
    )
    assert report.metadata["sample_filter"]["matched_count"] == 4
    assert report.metadata["sample_filter"]["unmatched_samples"] == []
    assert report.csv_paths and report.pvalue_paths
    stats = pd.concat([pd.read_csv(p) for p in report.pvalue_paths], ignore_index=True)
    from scipy.stats import mannwhitneyu
    expected = mannwhitneyu([2, 12], [30, 56], alternative="two-sided").pvalue
    assert stats["pvalue"].iloc[0] == pytest.approx(expected)


def test_group_scheme_changes_actual_profile_worker_order_and_saves_snapshot(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, ProjectGroupSpec, db
    from flask_app.services.group_spec_service import get_group_spec_service
    routes = import_module('flask_app.routes.api_script_hub.profile_analysis')
    project = Project(name='方案生效项目'); db.session.add(project); db.session.flush()
    path = tmp_path / 'profile.csv'; path.write_text('sample,group,metric\n001,A,1\n002,B,2\n', encoding='utf-8')
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=path.name,
        storage_path=str(path), metadata_json={'asset_set': '甲'}))
    first = ProjectGroupSpec(project_id=project.id, name='顺序一', spec_json={'groups': ['A', 'B']})
    second = ProjectGroupSpec(project_id=project.id, name='顺序二', spec_json={'groups': ['B', 'A']})
    db.session.add_all([first, second]); db.session.commit()
    executor = Mock(); monkeypatch.setattr(routes, '_script_executor', executor)
    monkeypatch.setattr(routes, '_build_script_cache_context', lambda **kwargs: {})
    monkeypatch.setattr(routes, '_set_task_state', Mock())
    payload = {'project_id': project.id, 'asset_set': '甲', 'grouptype_fields': ['group'], 'param_begin': 'metric', 'param_over': 'metric', 'force_rerun': True}
    client = profile_app.test_client()
    for spec, order in [(first, 'A,B'), (second, 'B,A')]:
        response = client.post('/api/script-hub/profile/run', json={**payload, 'group_spec_id': spec.id})
        assert response.status_code == 200, response.json
        assert executor.submit.call_args.kwargs['group_order'] == order
    frozen = get_group_spec_service().apply_to_payload('profile', {**payload, 'group_spec_id': first.id})
    first.spec_json = {'groups': ['B', 'A']}; db.session.commit()
    assert frozen['group_spec_snapshot']['spec_json']['groups'] == ['A', 'B']
    assert frozen['group_order'] == 'A,B'
    foreign = Project(name='其他项目'); db.session.add(foreign); db.session.commit()
    before = executor.submit.call_count
    response = client.post('/api/script-hub/profile/run', json={**payload, 'project_id': foreign.id, 'group_spec_id': first.id})
    assert response.status_code == 400 and executor.submit.call_count == before


def test_profile_cache_context_records_scheme_snapshot(profile_app, tmp_path, monkeypatch):
    common = import_module('flask_app.routes.api_script_hub._common')
    from flask_app.models.database import Project, db
    project = Project(name='任务快照'); db.session.add(project); db.session.commit()
    snapshot = {'id': 'synthetic', 'spec_json': {'groups': ['B', 'A']}}
    monkeypatch.setattr('flask_app.services.input_quality.validate_analysis_inputs', lambda *a, **k: {'alignments': [], 'reference_kind': 'profile'})
    monkeypatch.setattr('flask_app.services.input_quality.require_alignment_review', lambda *a, **k: None)
    with profile_app.test_request_context(json={'group_spec_snapshot': snapshot}):
        context = common._build_script_cache_context(project_id=None, module_name='profile', input_paths=[], config_json={'group_order': 'B,A'})
    assert context['config_json']['group_spec_snapshot'] == snapshot
