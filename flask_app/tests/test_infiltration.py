from pathlib import Path
import json
import os
import shutil
import subprocess
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
    decoy=tmp_path/'absolute.csv'
    frame=pd.read_csv(deconv,dtype={'Mixture':str})
    frame['T cells']=100
    frame['B cells']=200
    frame.to_csv(decoy,index=False)
    for kind,path in [('deconvolution',decoy),('profile',profile),('deconvolution',deconv)]:
        db.session.add(ProjectAsset(project_id=project.id,asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'test'}))
    db.session.commit()
    # Execute the same worker synchronously; only external Mongo is isolated.
    monkeypatch.setattr(shared._script_executor,'submit',lambda fn,task,**kwargs:fn(task,**kwargs))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result',lambda **kwargs:'synthetic-result')
    data={'project_id':project.id,'asset_set':'test','group_field':'group','cell_columns':['T cells','B cells'],'score_type':'relative','deconvolution_path':str(deconv)}
    client=profile_app.test_client()
    assert client.post('/api/script-hub/immune-infiltration/inspect',json=data).json['group_counts']=={'A':4,'B':4}
    assert client.post('/api/script-hub/immune-infiltration/inspect',json={**data,'asset_set':'missing'}).status_code==400
    ambiguous={key:value for key,value in data.items() if key!='deconvolution_path'}
    assert client.post('/api/script-hub/immune-infiltration/inspect',json=ambiguous).status_code==400
    foreign=tmp_path/'unregistered.csv'
    foreign.write_bytes(deconv.read_bytes())
    assert client.post('/api/script-hub/immune-infiltration/inspect',json={**data,'deconvolution_path':str(foreign)}).status_code==400
    for invalid in [None,'auto',{},['relative']]:
        rejected=client.post('/api/script-hub/immune-infiltration/run',json={**data,'score_type':invalid})
        assert rejected.status_code==400,rejected.json
    response=client.post('/api/script-hub/immune-infiltration/run',json=data)
    assert response.status_code==200,response.json
    task=shared._get_task_state(response.json['task_id'])
    assert task['status']=='completed',task
    result=task['result'];output=Path(result['output_base'])
    assert task['stage']=='分析完成'
    assert len(result['png_urls'])>=2
    viewer=client.get(result['viewer_url']).get_data(as_text=True)
    assert '数据与统计表' in viewer
    assert '输入类型：相对比例' in viewer
    assert result['metadata']['score_type']=='relative'
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


@pytest.mark.skipif(
    not os.environ.get('REFERENCE_PIPELINE') or not shutil.which('Rscript'),
    reason='需要只读挂载的原始 pipeline 与容器内 R 环境',
)
def test_group_comparison_matches_original_pipeline(profile_app, tmp_path):
    from flask_app.services.infiltration_service import generate_report

    reference = Path(os.environ['REFERENCE_PIPELINE']) / '07.immuneInfiltration' / '03.plot_deconv_group_comparison.R'
    if not reference.is_file():
        pytest.skip('未找到原始 07 组间比较脚本')

    groups = ['基线', '治疗A', '治疗B']
    ids = [f'{group}-样本-{index:02d}' for group in groups for index in range(4)]
    labels = [group for group in groups for _ in range(4)]
    profile = tmp_path / 'datapoint.csv'
    pd.DataFrame({'sample': ids, 'group': labels}).to_csv(profile, index=False)
    values = {
        'T cells': [0.03, 0.04, 0.05, 0.07, 0.21, 0.24, 0.28, 0.3, 0.12, 0.16, 0.17, 0.2],
        'B cells': [0.22, 0.22, 0.24, 0.25, 0.1, 0.12, 0.14, 0.16, 0.3, 0.31, 0.31, 0.36],
        'NK cells': [0.1, 0.1, 0.11, 0.13, 0.13, 0.13, 0.14, 0.15, 0.19, 0.2, 0.23, 0.24],
    }
    deconvolution = tmp_path / 'cibersort.csv'
    pd.DataFrame({'Mixture': ids, **values}).to_csv(deconvolution, index=False)
    cells = list(values)

    with profile_app.app_context():
        report = generate_report(
            str(profile), str(deconvolution), 'group', cells,
            tmp_path / 'platform', lambda *_args: None, lambda: False,
            score_type='relative',
        )
    platform_stats = pd.read_csv(next(report[1].rglob('panel_B_pairwise_stats.csv')))

    reference_output = tmp_path / 'reference-output'
    config_path = tmp_path / 'analysis.json'
    config_path.write_text(json.dumps({
        'paths': {
            'datapoint_input': str(profile),
            'deconvolution': str(deconvolution),
            'output_root': str(reference_output),
        },
        'datapoint': {
            'sample_column': 'sample',
            'group_column': 'group',
            'group_order': groups,
        },
        'immune_infiltration': {
            'sample_column': 'sample',
            'group_column': 'category',
            'cell_columns': cells,
            'comparisons': [],
        },
    }), encoding='utf-8')
    composition_script = Path(os.environ['REFERENCE_PIPELINE']) / '07.immuneInfiltration' / '02.plot_deconv_composition.R'
    reference_composition_output = reference_output / '02.composition'
    composition = subprocess.run([
        shutil.which('Rscript'), str(composition_script),
        f'--config={config_path}', f'--input={deconvolution}',
        f'--output={reference_composition_output}', f'--cell-cols={",".join(cells)}',
        '--dpi=100',
    ], cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert composition.returncode == 0, composition.stdout + composition.stderr
    platform_matrix = pd.read_csv(next(report[1].rglob('panel_A_shift_normalized_matrix.csv'))).set_index('sample').sort_index()
    reference_matrix = pd.read_csv(reference_composition_output / 'panel_A_shift_normalized_matrix.csv').set_index('sample').sort_index()
    assert platform_matrix[['group']].astype(str).equals(reference_matrix[['group']].astype(str))
    numeric_columns = [
        *[f'raw_{cell}' for cell in cells],
        *[f'fraction_{cell}' for cell in cells],
        'raw_min', 'global_shift_min', 'positive_epsilon', 'shifted_sum', 'closure_sum',
    ]
    for column in numeric_columns:
        np.testing.assert_allclose(platform_matrix[column], reference_matrix[column], rtol=1e-12, atol=1e-12)

    completed = subprocess.run([
        shutil.which('Rscript'), str(reference),
        f'--config={config_path}', f'--input={deconvolution}',
        f'--output={reference_output}', f'--cell-cols={",".join(cells)}',
        '--split-cell=none', '--dpi=100',
    ], cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    reference_stats = pd.read_csv(reference_output / 'panel_B_pairwise_stats.csv')

    key = ['CellType', 'Group1', 'Group2', 'Comparison', 'display', 'label']
    platform_stats = platform_stats.sort_values(key[:4]).reset_index(drop=True)
    reference_stats = reference_stats.sort_values(key[:4]).reset_index(drop=True)
    assert platform_stats[key].astype(str).equals(reference_stats[key].astype(str))
    for column in ['p_value', 'q_value']:
        np.testing.assert_allclose(
            pd.to_numeric(platform_stats[column], errors='coerce'),
            pd.to_numeric(reference_stats[column], errors='coerce'),
            rtol=1e-12, atol=1e-12, equal_nan=True,
        )
