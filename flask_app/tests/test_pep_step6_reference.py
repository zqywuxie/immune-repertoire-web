import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from flask_app.services.pep_analysis_service import PepAnalysisService


REFERENCE_PIPELINE = os.environ.get('REFERENCE_PIPELINE')


@pytest.mark.skipif(not REFERENCE_PIPELINE, reason='Reference pipeline is not mounted')
def test_step6_classification_matches_reference_pipeline(tmp_path):
    samples = {
        'S01': {'CASSA': (10, 'TRBV1', 'TRBJ1-1'), 'CASSB': (8, 'TRBV1', 'TRBJ2-1'), 'CASSD': (2, 'TRBV2', 'TRBJ1-1'), 'CASSF': (1, 'TRBV3', 'TRBJ2-1')},
        'S02': {'CASSA': (12, 'TRBV1', 'TRBJ1-1'), 'CASSB': (6, 'TRBV1', 'TRBJ2-1')},
        'S03': {'CASSA': (9, 'TRBV1', 'TRBJ1-1'), 'CASSC': (7, 'TRBV2', 'TRBJ2-1'), 'CASSD': (2, 'TRBV2', 'TRBJ1-1')},
        'S04': {'CASSA': (11, 'TRBV1', 'TRBJ1-1'), 'CASSC': (5, 'TRBV2', 'TRBJ2-1')},
    }
    groups = {'S01': 'control', 'S02': 'control', 'S03': 'case', 'S04': 'case'}
    inputs = tmp_path / 'input'
    inputs.mkdir()
    for sample, clones in samples.items():
        rows = [(cdr3, v_gene, j_gene, count) for cdr3, (count, v_gene, j_gene) in clones.items()]
        pd.DataFrame(rows, columns=['CDR3(pep)', 'V', 'J', 'copy']).to_csv(inputs / f'{sample}__TRB.csv', index=False)
    profile = tmp_path / 'profile.csv'
    pd.DataFrame({'sample': list(groups), 'group': list(groups.values())}).to_csv(profile, index=False)

    platform = PepAnalysisService(output_parent=tmp_path / 'platform').generate_report(
        pep_data_dir=str(inputs), profile_path=str(profile), group_fields=['group'], selected_chains=['TRB'],
        optional_steps={6}, min_sample_threshold=0,
    )
    platform_arr = platform.output_base / 'group/arrage_pep/Pep_shared_cate/Pep_shared/TRB.csv'
    platform_prop = platform.output_base / 'group/prop_pep/Pep_shared_cate/Pep_shared/TRB.csv'
    reference_output = tmp_path / 'reference'
    reference_category = reference_output / '03.UCDR3/1.Pep/3.add_cate_shared'
    reference_category.mkdir(parents=True)
    source_category = platform.output_base / 'group/Pep_shared_cate/Pep_shared/TRB.csv'
    reference_category.joinpath('TRB.csv').write_bytes(source_category.read_bytes())
    config = tmp_path / 'reference-config.json'
    config.write_text(json.dumps({
        'outputs': {'root': str(reference_output)},
        'cdr3_heatmap': {'within_dataset': {'min_total_present_samples': 1}},
    }), encoding='utf-8')
    script = Path(REFERENCE_PIPELINE) / '03.UCDR3/1.Pep/6.Pep_statistication.py'
    subprocess.run(
        [sys.executable, str(script), f'--config={config}'],
        check=True, capture_output=True, text=True,
    )
    reference_arr = reference_output / '03.UCDR3/1.Pep/6.Pep_statistication/CDR3_arranged/TRB.csv'
    reference_prop = reference_output / '03.UCDR3/1.Pep/6.Pep_statistication/CDR3_proportion/TRB.csv'

    def read_proportions(path):
        frame = pd.read_csv(path).sort_values('cate').reset_index(drop=True)
        frame['prop'] = pd.to_numeric(frame['prop'])
        return frame

    assert_frame_equal(
        read_proportions(platform_prop), read_proportions(reference_prop),
        check_dtype=False, check_names=False, rtol=1e-12, atol=1e-12,
    )

    def read_classification(path):
        frame = pd.read_csv(path, dtype={'CDR3(pep)': str, 'category': str}).iloc[1:].copy()
        count_columns = [
            column for column in frame
            if column.endswith('__sum') or column.endswith('__count') or column == 'all_num'
        ]
        for column in count_columns:
            frame[column] = pd.to_numeric(frame[column], errors='coerce').fillna(0).astype(int)
        return frame.sort_values(['CDR3(pep)', 'category']).reset_index(drop=True)

    assert_frame_equal(
        read_classification(platform_arr), read_classification(reference_arr),
        check_dtype=False, check_names=False, rtol=0, atol=0,
    )
