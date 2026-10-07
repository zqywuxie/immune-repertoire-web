from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.stats import pearsonr
from statsmodels.stats.multitest import multipletests
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.services.infiltration_pairing import inspect_paired


def paired_inputs(tmp_path):
    profile=tmp_path/'profile.csv';deconv=tmp_path/'deconv.csv'
    pids=[f'{i:04d}' for i in range(100,108)]
    dids=[f'{i:03d}' for i in range(8)]
    frame=pd.DataFrame({'sample':pids,'group':['甲']*4+['乙']*4,'IGHA1':[1,4,2,3,7,5,8,6]})
    frame.iloc[[2,0,6,1,5,4,7,3]].to_csv(profile,index=False)
    values=pd.DataFrame({'Mixture':dids,'T cells':[1,3,2,4,8,5,7,6],'B cells':[4,1,3,2,5,8,6,7]})
    values.to_csv(deconv,index=False)
    pairs=[{'deconvolution_sample':d,'profile_sample':p} for d,p in zip(dids,reversed(pids))]
    return profile,deconv,frame,values,pairs


def test_real_paired_analysis_uses_manifest_not_row_order(profile_app,tmp_path,monkeypatch):
    from flask_app.models.database import db,Project,ProjectAsset
    from flask_app.routes.api_script_hub import _common as shared
    profile,deconv,frame,values,pairs=paired_inputs(tmp_path)
    project=Project(name='明确配对验收');db.session.add(project);db.session.flush()
    for kind,path in [('profile',profile),('deconvolution',deconv)]:
        db.session.add(ProjectAsset(project_id=project.id,asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'test'}))
    db.session.commit()
    monkeypatch.setattr(shared._script_executor,'submit',lambda fn,task,**kwargs:fn(task,**kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result',lambda **kwargs:'synthetic-paired')
    payload={'project_id':project.id,'asset_set':'test','group_field':'group','cell_columns':['T cells','B cells'],'subclass_columns':['IGHA1'],'sample_pairs':pairs,'score_type':'relative'}
    client=profile_app.test_client()
    assert client.post('/api/script-hub/immune-infiltration-paired/inspect',json=payload).status_code==200
    response=client.post('/api/script-hub/immune-infiltration-paired/run',json=payload)
    assert response.status_code==200,response.json
    task=shared._get_task_state(response.json['task_id'])
    assert task['status']=='completed',task
    result=task['result'];output=Path(result['output_base'])
    assert result['module']=='immune-infiltration-paired'
    assert len(result['png_urls'])==1
    assert result['metadata']['sample_pairs']==pairs
    manifest=pd.read_csv(output/'sample_manifest.csv',dtype=str)
    assert manifest.cibersort_id.tolist()==[pair['deconvolution_sample'] for pair in pairs]
    assert manifest.profile_sample.tolist()==[pair['profile_sample'] for pair in pairs]
    ordered=frame.set_index('sample').loc[manifest.profile_sample].reset_index(drop=True)
    ranks=pd.concat([values[['T cells','B cells']],ordered[['IGHA1']]],axis=1).rank()
    residuals=ranks-ranks.groupby(ordered.group).transform('mean')
    expected=[pearsonr(residuals[cell],residuals.IGHA1) for cell in ['T cells','B cells']]
    stats=pd.read_csv(next(output.rglob('panel_C2_sample_subclass_deconv_stats.csv'))).set_index('CellType').loc[['T cells','B cells']]
    np.testing.assert_allclose(stats.partial_rho,[result.statistic for result in expected],atol=1e-10)
    np.testing.assert_allclose(stats.partial_p,[result.pvalue for result in expected],atol=1e-10)
    np.testing.assert_allclose(stats.partial_q,multipletests([result.pvalue for result in expected],method='fdr_bh')[1],atol=1e-10)
    assert stats.n.tolist()==[8,8]
    assert ProjectAsset.query.filter_by(project_id=project.id,asset_type='processed_result').count()==1
    for url in [result['viewer_url'],result['zip_url'],*result['png_urls'],*result['csv_urls']]:
        assert client.get(url).status_code==200


def test_pairing_rejects_missing_duplicate_and_unknown_ids(profile_app,tmp_path):
    from flask_app.exceptions import ValidationError
    profile,deconv,_,_,pairs=paired_inputs(tmp_path)
    preview=inspect_paired(str(profile),str(deconv))
    assert preview['profile_samples'][0]=='0102'
    assert preview['deconvolution_samples'][0]=='000'
    cases=[(None,'明确填写'),(pairs+[pairs[0]],'只能参与一次'),([{**pairs[0],'profile_sample':'unknown'}]+pairs[1:],'不属于'),(pairs[:3],'至少需要两个分组')]
    for chosen,message in cases:
        with pytest.raises(ValidationError,match=message):
            inspect_paired(str(profile),str(deconv),'group',sample_pairs=chosen)
