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
def test_step2_shared_and_usage_matrices_match_reference_pipeline(tmp_path):
    samples = {
        'S01': [('CASSA', 'TRBV1', 'TRBJ1-1', 3), ('CASSB', 'TRBV1', 'TRBJ2-1', 1)],
        'S02': [('CASSA', 'TRBV1', 'TRBJ1-1', 2), ('CASSC', 'TRBV2', 'TRBJ2-1', 2)],
        'S03': [('CASSD', 'TRBV2', 'TRBJ1-1', 7), ('CASSB', 'TRBV1', 'TRBJ2-1', 3)],
        'S04': [('CASSE', 'TRBV3', 'TRBJ2-1', 4), ('CASSA', 'TRBV1', 'TRBJ1-1', 6)],
    }
    inputs = tmp_path / 'input'
    inputs.mkdir()
    for sample, rows in samples.items():
        pd.DataFrame(rows, columns=['CDR3(pep)', 'V', 'J', 'copy']).to_csv(
            inputs / f'{sample}__TRB.csv', index=False,
        )
    profile = tmp_path / 'profile.csv'
    pd.DataFrame({'sample': list(samples), 'group': ['control', 'control', 'case', 'case']}).to_csv(profile, index=False)
    reference_output = tmp_path / 'reference'
    config = tmp_path / 'reference-config.json'
    config.write_text(json.dumps({
        'outputs': {'root': str(reference_output)},
        'paths': {'pep_input': str(inputs)},
    }), encoding='utf-8')
    script = Path(REFERENCE_PIPELINE) / '03.UCDR3/1.Pep/2.Pep_shared.py'
    subprocess.run(
        [sys.executable, str(script), f'--config={config}', f'--input={inputs}'],
        check=True, capture_output=True, text=True,
    )

    platform = PepAnalysisService(output_parent=tmp_path / 'platform').generate_report(
        pep_data_dir=str(inputs), profile_path=str(profile), group_fields=[],
        selected_chains=['TRB'], optional_steps=set(),
    )
    reference_base = reference_output / '03.UCDR3/1.Pep/2.Pep_shared'
    comparisons = [
        (reference_base / 'Pep_shared/TRB.csv', platform.output_base / 'Pep_shared/TRB.csv'),
        *[
            (reference_base / f'usage/{usage}/TRB.csv', platform.output_base / f'usage/{usage}/TRB.csv')
            for usage in ['0Vusage', '1Vusage', '0Jusage', '1Jusage', '0VJusage', '1VJusage']
        ],
    ]

    def canonical_matrix(path):
        frame = pd.read_csv(path, index_col=0).fillna(0)
        frame.index = frame.index.map(str)
        frame.columns = frame.columns.map(str)
        frame = frame.sort_index().reindex(sorted(frame.columns), axis=1)
        return frame.astype(float)

    for reference_path, platform_path in comparisons:
        assert_frame_equal(
            canonical_matrix(platform_path), canonical_matrix(reference_path),
            check_dtype=False, check_names=False, rtol=1e-12, atol=1e-12,
            obj=platform_path.relative_to(platform.output_base).as_posix(),
        )
