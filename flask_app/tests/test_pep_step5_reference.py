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
def test_step5_differential_usage_matrix_matches_reference_pipeline(tmp_path):
    rows = []
    for index in range(6):
        sample = f'C{index + 1:02d}'
        rows.append({
            'sample': sample, 'group': 'control',
            'TRBV1': index + 1, 'TRBV2': 20 + index, 'TRBV3': index + 1,
            'TRBV10': [1, 2, 3, 4, 5, 12][index],
        })
    for index in range(6):
        sample = f'P{index + 1:02d}'
        rows.append({
            'sample': sample, 'group': 'case',
            'TRBV1': 20 + index, 'TRBV2': index + 1, 'TRBV3': index + 1,
            'TRBV10': [1, 2, 3, 4, 5, 6][index],
        })
    usage = tmp_path / 'usage.csv'
    pd.DataFrame(rows).to_csv(usage, index=False)

    platform_output = tmp_path / 'platform'
    _, platform_csvs = PepAnalysisService._run_heatmap(usage, platform_output, 0.05)
    assert len(platform_csvs) == 1

    reference_output = tmp_path / 'reference'
    reference_input = reference_output / '03.UCDR3/1.Pep/4.add_cate_usage/usage/1Vusage'
    reference_input.mkdir(parents=True)
    (reference_input / 'TRB.csv').write_bytes(usage.read_bytes())
    config = tmp_path / 'reference-config.json'
    config.write_text(json.dumps({
        'outputs': {'root': str(reference_output)},
        'datapoint': {'group_column': 'group', 'excluded_groups': []},
    }), encoding='utf-8')
    script = Path(REFERENCE_PIPELINE) / '03.UCDR3/1.Pep/5.Heat_map_Thread.py'
    subprocess.run(
        [sys.executable, str(script), f'--config={config}', '--workers=1'],
        check=True, capture_output=True, text=True,
    )
    reference_csv = (
        reference_output / '03.UCDR3/1.Pep/5.Heat_map_Thread/usage/1Vusage/TRB/csv_file/group.csv'
    )
    actual = pd.read_csv(platform_csvs[0], index_col=0)
    expected = pd.read_csv(reference_csv, index_col=0)
    assert_frame_equal(actual, expected, check_dtype=False, check_names=False, check_exact=True)
