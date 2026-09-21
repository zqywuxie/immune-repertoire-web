from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pandas as pd
import pytest
from scipy.stats import mannwhitneyu
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.services.infiltration_service import inspect_inputs


def inputs(tmp_path):
    profile=tmp_path/'profile.csv';deconv=tmp_path/'deconv.csv'
    samples=[f'{i:03d}' for i in range(8)]
    pd.DataFrame({'sample':samples,'group':['A']*4+['B']*4}).to_csv(profile,index=False)
    pd.DataFrame({'Mixture':samples,'T cells':np.arange(1,9)/10,'B cells':np.arange(9,1,-1)/10,'P-value':[.01]*8}).to_csv(deconv,index=False)
    return profile,deconv


def test_real_api_execution_registers_results_and_downloads(profile_app,tmp_path,monkeypatch):
    from flask_app.models.database import db,Project,ProjectAsset
    from flask_app.routes.api_script_hub import _common as shared
    profile,deconv=inputs(tmp_path)
    project=Project(name='合成浸润验收');db.session.add(project);db.session.flush()
    for kind,path in [('profile',profile),('deconvolution',deconv)]:
        db.session.add(ProjectAsset(project_id=project.id,asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'test'}))
    db.session.commit()
    # Execute the same worker synchronously; only external Mongo is isolated.
    monkeypatch.setattr(shared._script_executor,'submit',lambda fn,task,**kwargs:fn(task,**kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result',lambda **kwargs:'synthetic-result')
    data={'project_id':project.id,'asset_set':'test','group_field':'group','cell_columns':['T cells','B cells']}
    client=profile_app.test_client()
    assert client.post('/api/script-hub/immune-infiltration/inspect',json=data).json['group_counts']=={'A':4,'B':4}
    assert client.post('/api/script-hub/immune-infiltration/inspect',json={**data,'asset_set':'missing'}).status_code==400
    response=client.post('/api/script-hub/immune-infiltration/run',json=data)
    assert response.status_code==200,response.json
    task=shared._get_task_state(response.json['task_id'])
    assert task['status']=='completed',task
    result=task['result'];output=Path(result['output_base'])
    assert task['stage']=='分析完成'
    assert len(result['png_urls'])>=2
    viewer=client.get(result['viewer_url']).get_data(as_text=True)
    assert '数据与统计表' in viewer
    assert 'id="sigToggle"' not in viewer
    for url in result['csv_urls']:
        assert url in viewer
        assert client.get(url).status_code==200
    matrix=pd.read_csv(next(output.rglob('panel_A_shift_normalized_matrix.csv')),dtype={'sample':str}).sort_values('sample')
    assert matrix['sample'].tolist()==[f'{i:03d}' for i in range(8)]
    raw=np.column_stack([np.arange(1,9)/10,np.arange(9,1,-1)/10]);shifted=raw-raw.min()+1e-6
    np.testing.assert_allclose(matrix[['fraction_T cells','fraction_B cells']],shifted/shifted.sum(axis=1)[:,None])
    stats=pd.read_csv(next(output.rglob('panel_B_pairwise_stats.csv')))
    expected=mannwhitneyu(raw[:4,0],raw[4:,0],alternative='two-sided',method='asymptotic').pvalue
    np.testing.assert_allclose(stats['p_value'],expected)
    np.testing.assert_allclose(stats['q_value'],expected)
    asset=ProjectAsset.query.filter_by(project_id=project.id,asset_type='processed_result').one()
    assert asset.storage_path==str(output)
    for url in [result['zip_url'],result['viewer_url'],*result['png_urls']]:
        download=client.get(url)
        assert download.status_code==200,(url,download.json)
        assert len(download.data)>100


def test_missing_sample_and_insufficient_groups_rejected(profile_app,tmp_path):
    from flask_app.exceptions import ValidationError
    profile,deconv=inputs(tmp_path)
    frame=pd.read_csv(profile,dtype=str);frame.loc[0,'sample']='different';frame.to_csv(profile,index=False)
    with pytest.raises(ValidationError,match='缺少分组'):inspect_inputs(str(profile),str(deconv),'group')
    profile,deconv=inputs(tmp_path)
    frame=pd.read_csv(profile,dtype=str);frame['group']='A';frame.to_csv(profile,index=False)
    with pytest.raises(ValidationError,match='两个分组'):inspect_inputs(str(profile),str(deconv),'group')
