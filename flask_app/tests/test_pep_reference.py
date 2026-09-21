"""Compare synthetic matrices against the mounted original pipeline scripts."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from flask_app.services.pep_analysis_service import PepAnalysisService


@pytest.mark.parametrize('suffix', ['__TRB.csv', '_TRB.csv', '__TRB.csv.gz'])
def test_original_category_outputs(tmp_path, suffix):
    reference = os.environ.get('REFERENCE_PIPELINE')
    if not reference:
        pytest.skip('需要只读挂载原始 pipeline 并设置 REFERENCE_PIPELINE')
    samples = ['001', '1', 'patient__A', 'missing', 'unmatched']
    names = [sample + suffix for sample in samples]
    profile = pd.DataFrame({'sample': samples[:-1], 'group': ['A', 'B', 'A', None]})
    profile_path = tmp_path / 'profile.csv'
    profile.to_csv(profile_path, index=False)
    base = tmp_path / 'outputs' / '03.UCDR3' / '1.Pep'
    usage = base / '2.Pep_shared' / 'usage'
    shared = base / '2.Pep_shared' / 'Pep_shared'
    usage.mkdir(parents=True)
    shared.mkdir(parents=True)
    pd.DataFrame({'Unnamed: 0': names, 'TRBV1': [.1,.2,.3,.4,.5], 'TRBV2': [.9,.8,.7,.6,.5]}).to_csv(usage/'TRB.csv', index=False)
    pd.DataFrame({'CDR3(pep)': ['CASSA','CASSB'], **{name:[i+1,i+2] for i,name in enumerate(names)}}).to_csv(shared/'TRB.csv', index=False)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'outputs': {'root': str(tmp_path/'outputs')}, 'paths': {
        'datapoint_input': str(profile_path), 'pep_usage_output': str(usage),
        'pep_shared_output': str(shared), 'pep_usage_cate_output': str(tmp_path/'reference_usage'),
        'pep_category_output': str(tmp_path/'reference_shared')},
        'datapoint': {'sample_column':'sample', 'group_column':'group', 'group_order':['A','B']}}))
    for script in ['3.add_cate_shared.py','4.add_cate_usage.py']:
        subprocess.run([sys.executable, '-B', str(Path(reference)/'03.UCDR3'/'1.Pep'/script), '--config', str(config)], check=True, capture_output=True, text=True)
    PepAnalysisService._add_cate_usage(usage/'TRB.csv', tmp_path/'platform_usage.csv', profile, 'group')
    PepAnalysisService._add_cate_shared(shared/'TRB.csv', tmp_path/'platform_shared.csv', profile, 'group')
    expected = pd.read_csv(base/'4.add_cate_usage'/'TRB.csv').rename(columns={'group':'Category'}).sort_values('sample').reset_index(drop=True)
    actual = pd.read_csv(tmp_path/'platform_usage.csv').sort_values('sample').reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected)
    assert set(actual['sample']) == set(names[:3])
    expected = pd.read_csv(base/'3.add_cate_shared'/'TRB.csv', dtype=str)
    actual = pd.read_csv(tmp_path/'platform_shared.csv', dtype=str)
    expected.iloc[0,0] = 'category'  # Existing platform contract for the group row.
    pd.testing.assert_frame_equal(actual[sorted(actual.columns)], expected[sorted(expected.columns)])


@pytest.mark.parametrize('identifiers', [['001','001'], ['001',None]])
def test_invalid_metadata_rejected_before_analysis(tmp_path, identifiers):
    pep = tmp_path/'pep'
    pep.mkdir()
    profile = tmp_path/'profile.csv'
    pd.DataFrame({'sample': identifiers, 'group':['A','B']}).to_csv(profile,index=False)
    with pytest.raises(ValueError, match='样本编号'):
        PepAnalysisService(output_parent=tmp_path/'results').generate_report(
            pep_data_dir=str(pep),profile_path=str(profile),group_fields=['group'],selected_chains=['TRB'],optional_steps=set())


@pytest.mark.parametrize('selected', ['A-1', 'A1', '病例甲', '病例乙'])
def test_selection_preserves_distinct_identifiers(tmp_path, selected):
    samples = ['A-1', 'A1', '病例甲', '病例乙']
    pep = tmp_path/'pep'
    pep.mkdir()
    profile = tmp_path/'profile.csv'
    pd.DataFrame({'sample': samples, 'group': ['A']*4}).to_csv(profile,index=False)
    for sample in samples:
        pd.DataFrame({'CDR3(pep)':['CASSA'], 'V':['TRBV1'], 'J':['TRBJ1'], 'copy':[5]}).to_csv(pep/f'{sample}__TRB.csv',index=False)
    report = PepAnalysisService(output_parent=tmp_path/'results').generate_report(
        pep_data_dir=str(pep), profile_path=str(profile), group_fields=['group'],
        selected_chains=['TRB'], selected_samples=[selected], optional_steps=set())
    tables = list(report.output_base.rglob('df_VJ_all.csv'))
    assert tables
    table = pd.read_csv(tables[0])
    assert table['sample'].tolist() == [f'{selected}__TRB.csv']
