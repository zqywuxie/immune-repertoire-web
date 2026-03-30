"""Regression tests for gzip support in AutoHeatmapService."""
import gzip
from pathlib import Path

from services.auto_heatmap_service import AutoHeatmapService, FieldMapping


def _write_gzip_table(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wt', encoding='utf-8') as handle:
        handle.write(content)


def test_scan_base_folder_detects_samples_from_csv_gz(tmp_path):
    svc = AutoHeatmapService()

    csv_content = "cdr3,copy\nCASSA,10\nCASSB,20\n"
    _write_gzip_table(tmp_path / "HL_FP1__IGH.csv.gz", csv_content)
    _write_gzip_table(tmp_path / "HL_FP1__IGK.csv.gz", csv_content)
    _write_gzip_table(tmp_path / "HL_FP2__IGH.csv.gz", csv_content)
    _write_gzip_table(tmp_path / "HL_FP2__IGK.csv.gz", csv_content)

    result = svc.scan_base_folder(str(tmp_path))

    assert result.has_chain_suffix is True
    assert set(result.all_chains) == {"IGH", "IGK"}
    assert {sample.original_name for sample in result.samples} == {"HL_FP1", "HL_FP2"}


def test_get_file_columns_supports_tsv_gz_separator_detection(tmp_path):
    svc = AutoHeatmapService()
    tsv_path = tmp_path / "Sample_A__TRB.tsv.gz"
    _write_gzip_table(tsv_path, "cdr3\tcopy\nCASSA\t5\nCASSB\t7\n")

    info = svc.get_file_columns(str(tsv_path))

    assert info["columns"] == ["cdr3", "copy"]
    assert info["suggested_cdr3"] == "cdr3"
    assert info["suggested_copy"] == "copy"


def test_load_sample_data_for_single_chain_with_csv_gz(tmp_path):
    svc = AutoHeatmapService()

    csv_content = "cdr3,copy\nCASSA,10\nCASSB,20\n"
    _write_gzip_table(tmp_path / "HL_FP1__IGH.csv.gz", csv_content)
    _write_gzip_table(tmp_path / "HL_FP2__IGH.csv.gz", csv_content)

    scan_result = svc.scan_base_folder(str(tmp_path))
    mapping = FieldMapping(cdr3_column="cdr3", copy_column="copy")
    sample_data = svc.load_sample_data_for_single_chain(scan_result.samples, "IGH", mapping)

    assert set(sample_data.keys()) == {"HL_FP1", "HL_FP2"}
    for df in sample_data.values():
        assert list(df.columns) == ["cdr3", "copy"]
        assert len(df) == 2


def test_load_sample_data_for_single_chain_with_lowercase_suffix(tmp_path):
    svc = AutoHeatmapService()

    csv_content = "cdr3,copy\nCASSA,10\nCASSB,20\n"
    (tmp_path / "HL_FP1_igh.csv").write_text(csv_content, encoding="utf-8")
    (tmp_path / "HL_FP2_igh.csv").write_text(csv_content, encoding="utf-8")

    scan_result = svc.scan_base_folder(str(tmp_path))
    mapping = FieldMapping(cdr3_column="cdr3", copy_column="copy")
    sample_data = svc.load_sample_data_for_single_chain(scan_result.samples, "IGH", mapping)

    assert scan_result.has_chain_suffix is True
    assert set(scan_result.all_chains) == {"IGH"}
    assert set(sample_data.keys()) == {"HL_FP1", "HL_FP2"}
