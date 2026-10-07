from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.stats import mannwhitneyu
from statsmodels.stats.multitest import multipletests
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_infiltration import inputs
from flask_app.services.infiltration_service import inspect_concordance


def test_concordance_real_r_and_chinese_comparisons(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import db, Project, ProjectAsset
    from flask_app.routes.api_script_hub import _common as shared
    sample_ids = [f'{i:03d}' for i in range(12)]
    groups = ['甲组']*4+['乙组']*4+['丙组']*4
    profile = pd.DataFrame({'sample':sample_ids, 'group':groups, 'IGHM':[1,2,3,4]*3, 'IGHA1':[1,3,2,4,5,8,6,7,10,12,9,11]})
    deconv = pd.DataFrame({'Mixture':sample_ids, 'T cells':np.arange(1,13), 'B cells':np.arange(12,0,-1)})
    profile_path=tmp_path/'profile.csv'; deconv_path=tmp_path/'deconv.csv'
    profile.to_csv(profile_path,index=False); deconv.to_csv(deconv_path,index=False)
    project=Project(name='方向比较验收');db.session.add(project);db.session.flush()
    for kind,path in [('profile',profile_path),('deconvolution',deconv_path)]:
        db.session.add(ProjectAsset(project_id=project.id,asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'test'}))
    db.session.commit()
    monkeypatch.setattr(shared._script_executor,'submit',lambda fn,task,**kwargs:fn(task,**kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result',lambda **kwargs:'synthetic-concordance')
    payload={'project_id':project.id,'asset_set':'test','group_field':'group','cell_columns':['T cells','B cells'],'score_type':'other','subclass_columns':['IGHM','IGHA1']}
    client=profile_app.test_client()
    assert client.post('/api/script-hub/immune-infiltration-concordance/inspect',json=payload).status_code==200
    response=client.post('/api/script-hub/immune-infiltration-concordance/run',json=payload)
    assert response.status_code==200,response.json
    task=shared._get_task_state(response.json['task_id'])
    assert task['status']=='completed',task
    result=task['result'];output=Path(result['output_base'])
    assert result['module']=='immune-infiltration-concordance'
    assert result['metadata']['selected_subclasses']==['IGHM','IGHA1']
    assert len(result['png_urls'])==3
    files=list(output.rglob('panel_C2_comparison_*_stats.csv'))
    assert len(files)==3
    seen=set()
    for file in files:
        stats=pd.read_csv(file);a,b=stats.iloc[0][['Group1','Group2']]
        seen.add((a,b));pvalues=[]
        for _,row in stats.iterrows():
            masks=[np.array(groups)==group for group in [a,b]]
            x=[deconv.loc[mask,row.CellType] for mask in masks]
            y=[profile.loc[mask,row.Subclass] for mask in masks]
            cx=float(x[0].median()-x[1].median());cy=float(y[0].median()-y[1].median())
            upx=mannwhitneyu(*x,alternative='greater',method='asymptotic').pvalue
            downx=mannwhitneyu(*x,alternative='less',method='asymptotic').pvalue
            upy=mannwhitneyu(*y,alternative='greater',method='asymptotic').pvalue
            downy=mannwhitneyu(*y,alternative='less',method='asymptotic').pvalue
            concordant=min(1,2*min(max(upx,upy),max(downx,downy)))
            discordant=min(1,2*min(max(upx,downy),max(downx,upy)))
            expected=concordant if np.sign(cx)==np.sign(cy) else discordant
            np.testing.assert_allclose([row.cell_effect,row.subclass_effect,row.joint_p],[cx,cy,expected])
            if cx==0 or cy==0: assert row.concordance=='No estimable effect'
            pvalues.append(expected)
        np.testing.assert_allclose(stats.directional_q,multipletests(pvalues,method='fdr_bh')[1])
    assert seen=={('甲组','乙组'),('甲组','丙组'),('乙组','丙组')}
    assert pd.read_csv(output/'groups.csv',dtype={'sample':str})['sample'].tolist()==sample_ids
    assert ProjectAsset.query.filter_by(project_id=project.id,asset_type='processed_result').count()==1
    for url in [result['zip_url'],result['viewer_url'],*result['png_urls'],*result['csv_urls']]:
        assert client.get(url).status_code==200


def test_concordance_required_metrics_and_missing_values(profile_app,tmp_path):
    from flask_app.exceptions import ValidationError
    profile,deconv=inputs(tmp_path)
    with pytest.raises(ValidationError,match='没有可用'):
        inspect_concordance(str(profile),str(deconv))
    frame=pd.read_csv(profile,dtype=str);frame['IGHA1']=['1','2','3','','5','6','7','8'];frame.to_csv(profile,index=False)
    assert inspect_concordance(str(profile),str(deconv))['subclass_columns']==['IGHA1']
    with pytest.raises(ValidationError,match='不会自动填零'):
        inspect_concordance(str(profile),str(deconv),'group',subclass_columns=['IGHA1'])
    with pytest.raises(ValidationError,match='有效且不重复'):
        inspect_concordance(str(profile),str(deconv),'group',subclass_columns=['not-present'])
