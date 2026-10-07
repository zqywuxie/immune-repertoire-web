from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import pearsonr
from statsmodels.stats.multitest import multipletests

from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_infiltration import inputs
from flask_app.services.infiltration_service import inspect_consistency


def test_consistency_real_r_api(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import db, Project, ProjectAsset
    from flask_app.routes.api_script_hub import _common as shared
    profile, deconv = inputs(tmp_path)
    values = pd.DataFrame({'T cells': [1,3,2,4,8,5,7,6], 'B cells': [4,1,3,2,5,8,6,7], 'NK cells': [1,4,2,3,7,5,8,6]})
    table = values.copy()
    table.insert(0, 'Mixture', [f'{i:03d}' for i in range(8)])
    table.to_csv(deconv, index=False)
    project = Project(name='细胞相关性验收')
    db.session.add(project)
    db.session.flush()
    for kind, path in [('profile', profile), ('deconvolution', deconv)]:
        db.session.add(ProjectAsset(project_id=project.id, asset_type=kind, storage_path=str(path), original_name=path.name, size=path.stat().st_size, metadata_json={'asset_set':'test'}))
    db.session.commit()
    monkeypatch.setattr(shared._script_executor, 'submit', lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result', lambda **kwargs: 'synthetic-consistency')
    client = profile_app.test_client()
    payload = {'project_id':project.id, 'asset_set':'test', 'group_field':'group', 'cell_columns':list(values), 'score_type':'absolute'}
    response = client.post('/api/script-hub/immune-infiltration-consistency/run', json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json['task_id'])
    assert task['status'] == 'completed', task
    result = task['result']
    assert result['module'] == 'immune-infiltration-consistency'
    assert result['metadata']['analysis_kind'] == 'consistency'
    output = Path(result['output_base'])
    assert len(result['png_urls']) == 1
    assert not list(output.rglob('*C2*'))
    assert pd.read_csv(output/'input.csv', dtype={'sample':str})['sample'].tolist() == [f'{i:03d}' for i in range(8)]
    stats = pd.read_csv(next(output.rglob('panel_C_correlation_stats.csv')))
    ranks = values.rank()
    residuals = ranks - ranks.groupby(pd.Series(['A']*4+['B']*4)).transform('mean')
    pairs = [('T cells','B cells'), ('T cells','NK cells'), ('B cells','NK cells')]
    expected = [pearsonr(residuals[a], residuals[b]) for a,b in pairs]
    qs = multipletests([p.pvalue for p in expected], method='fdr_bh')[1]
    for (a,b), pair, q in zip(pairs, expected, qs):
        row = stats[(stats.Cell1==a)&(stats.Cell2==b)].iloc[0]
        np.testing.assert_allclose([row.rho,row.p_value,row.q_value], [pair.statistic,pair.pvalue,q], atol=1e-10)
    assert ProjectAsset.query.filter_by(project_id=project.id, asset_type='processed_result').count() == 1
    for url in [result['viewer_url'], result['zip_url'], *result['png_urls'], *result['csv_urls']]:
        assert client.get(url).status_code == 200


def test_consistency_rejects_unestimable_inputs(profile_app, tmp_path):
    from flask_app.exceptions import ValidationError
    profile, deconv = inputs(tmp_path)
    with pytest.raises(ValidationError, match='两个细胞'):
        inspect_consistency(str(profile), str(deconv), 'group', ['T cells'])
    table = pd.read_csv(deconv, dtype={'Mixture':str})
    table['T cells'] = [1]*4+[2]*4
    table.to_csv(deconv, index=False)
    with pytest.raises(ValidationError, match='校正后无变化'):
        inspect_consistency(str(profile), str(deconv), 'group')
    profile, deconv = inputs(tmp_path)
    table = pd.read_csv(deconv, dtype={'Mixture':str}).iloc[[0,1,4,5]]
    table.to_csv(deconv, index=False)
    with pytest.raises(ValidationError, match='三个匹配样本'):
        inspect_consistency(str(profile), str(deconv), 'group')
