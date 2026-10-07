import numpy as np
import pandas as pd
import pytest
from scipy.stats import mannwhitneyu
from statsmodels.stats.multitest import multipletests

from flask_app.tests.test_profile_workflow import profile_app
from flask_app.exceptions import ValidationError
from flask_app.services.infiltration_service import generate_report, inspect_pathway
from flask_app.services.pathway_artifacts import GO_BP_TERMS


def inputs(tmp_path):
    profile=tmp_path/'profile.csv';deconv=tmp_path/'deconv.csv';go=tmp_path/'go.csv'
    ids=[f'{i:03d}' for i in range(8)]
    pd.DataFrame({'sample':ids,'group':['病例']*4+['对照']*4}).to_csv(profile,index=False)
    pd.DataFrame({'Mixture':ids,'正向':[5,6,7,8,1,2,3,4],
                  '反向':[1,2,3,4,5,6,7,8],'零效应':[1,4,2,3,4,1,3,2]}).to_csv(deconv,index=False)
    pd.DataFrame({'ID':GO_BP_TERMS,'Description':['通路'+str(i) for i in range(10)],
                  'setSize':[20]*10,'NES':[1.2,-1.2]*5,'pvalue':[.01,.03]*5,
                  'p.adjust':[.1]*10,'qvalue':[.1]*10}).to_csv(go,index=False)
    return profile,deconv,go


def test_real_pathway_direction_preserves_original_joint_statistics(profile_app,tmp_path):
    profile,deconv,go=inputs(tmp_path)
    _,output,summary=generate_report(str(profile),str(deconv),'group',['正向','反向','零效应'],
        tmp_path/'results',lambda *args:None,lambda:False,score_type='absolute',
        analysis_kind='pathway',go_gsea_path=str(go),comparison=['病例','对照'])
    statistics=pd.read_csv(next(output.rglob('D1_GO_cell_full_statistics.csv')))
    source=pd.read_csv(go).set_index('ID')
    cells=pd.read_csv(deconv)
    expected=[]
    for row in statistics.itertuples():
        x=cells[row.CellType][:4];y=cells[row.CellType][4:]
        effect=np.median(x)-np.median(y)
        p_up=mannwhitneyu(x,y,alternative='greater',method='asymptotic').pvalue
        p_down=mannwhitneyu(x,y,alternative='less',method='asymptotic').pvalue
        pathway=source.loc[row.ID]
        up=pathway.pvalue if pathway.NES>0 else 1
        down=pathway.pvalue if pathway.NES<0 else 1
        same=min(1,2*min(max(up,p_up),max(down,p_down)))
        opposite=min(1,2*min(max(up,p_down),max(down,p_up)))
        joint=1 if effect==0 else same if np.sign(pathway.NES)==np.sign(effect) else opposite
        expected.append(joint)
        assert row.cell_effect==effect
        if effect==0:assert row.concordance=='Neutral'
    np.testing.assert_allclose(statistics.joint_p,expected,rtol=1e-12)
    np.testing.assert_allclose(statistics.joint_q,multipletests(expected,method='fdr_bh')[1],rtol=1e-12)
    assert set(statistics.Group1)=={'病例'} and set(statistics.Group2)=={'对照'}
    assert summary['sample_count']==8 and summary['analysis_kind']=='pathway'
    assert (output/'GO_BP_full.csv').read_bytes()==go.read_bytes()
    assert pd.read_csv(output/'input.csv',dtype=str)['sample'].tolist()==[f'{i:03d}' for i in range(8)]
    assert len(list(output.rglob('*.png')))==1


def test_pathway_rejects_unavailable_group_before_execution(profile_app,tmp_path):
    profile,deconv,go=inputs(tmp_path)
    with pytest.raises(ValidationError,match='比较组别'):
        inspect_pathway(str(profile),str(deconv),'group',['正向'],str(go),['病例','未知'])


def test_pathway_api_executes_registered_source_and_downloads(profile_app,tmp_path,monkeypatch):
    from flask_app.tests.pathway_test_support import source_fixture
    from flask_app.models.database import ProjectAsset,db
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services.background_job_service import get_background_job_service
    data,source,table,frame,expression=source_fixture(profile_app,tmp_path)
    profile,deconv,_=inputs(tmp_path)
    df=pd.read_csv(profile,dtype=str);df['group']=df['group'].map({'病例':'A','对照':'B'});df.to_csv(profile,index=False)
    for kind,path in [('profile',profile),('deconvolution',deconv)]:
        db.session.add(ProjectAsset(project_id=data['project_id'],asset_type=kind,storage_path=str(path),
            original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'Set1'}))
    db.session.commit()
    monkeypatch.setattr(shared._script_executor,'submit',lambda fn,task,**kwargs:fn(task,**kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result',lambda **kwargs:'pathway-result')
    payload={**data,'group_field':'group','cell_columns':['正向','反向'],'score_type':'absolute'}
    client=profile_app.test_client()
    response=client.post('/api/script-hub/immune-infiltration-pathway/inspect',json=payload)
    assert response.status_code==200,response.json
    assert response.json['sample_count']==8
    response=client.post('/api/script-hub/immune-infiltration-pathway/run',json=payload)
    assert response.status_code==200,response.json
    job=get_background_job_service().get_job(response.json['task_id'])
    assert job['status']=='completed',job
    assert job['payload']['upstream_input']['source_job_id']=='go-source'
    assert job['result']['metadata']['analysis_kind']=='pathway'
    for url in job['result']['png_urls']+job['result']['csv_urls']+[job['result']['zip_url']]:
        result=client.get(url)
        assert result.status_code==200,url
        assert result.data
