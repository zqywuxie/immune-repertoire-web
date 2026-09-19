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
