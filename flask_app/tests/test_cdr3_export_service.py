"""Tests for CDR3 export directory layout."""

from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

try:
    from flask_app.services.cdr3_export_service import CDR3ExportService
except ModuleNotFoundError:
    from services.cdr3_export_service import CDR3ExportService


def _sample_df(shared_suffix: str, unique_suffix: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            'cdr3': [f'SHARED_{shared_suffix}', f'UNIQUE_{unique_suffix}'],
            'copy': [10, 5],
        }
    )


def test_write_complete_export_directory_uses_chain_subfolders():
    service = CDR3ExportService()
    sample_data = {
        'IGH': {
            'SampleA': _sample_df('IGH', 'A_IGH'),
            'SampleB': _sample_df('IGH', 'B_IGH'),
        },
        'IGK': {
            'SampleA': _sample_df('IGK', 'A_IGK'),
            'SampleB': _sample_df('IGK', 'B_IGK'),
        },
    }

    with TemporaryDirectory() as tmp_dir:
        output_dir = Path(tmp_dir)
        service.write_complete_export_directory(output_dir=output_dir, sample_data=sample_data)

        assert (output_dir / 'README.txt').exists()
        assert (output_dir / 'IGH' / 'CDR3_Shared_List.xlsx').exists()
        assert (output_dir / 'IGH' / 'Abundance_Union_Top100.xlsx').exists()
        assert (output_dir / 'IGH' / 'Abundance_Union_Full.xlsx').exists()
        assert (output_dir / 'IGH' / 'Top100_Analysis.xlsx').exists()
        assert (output_dir / 'IGK' / 'CDR3_Shared_List.xlsx').exists()
        assert (output_dir / 'IGK' / 'Abundance_Union_Top100.xlsx').exists()
        assert (output_dir / 'IGK' / 'Abundance_Union_Full.xlsx').exists()
        assert (output_dir / 'IGK' / 'Top100_Analysis.xlsx').exists()
