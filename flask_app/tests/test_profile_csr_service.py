import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import mannwhitneyu

from flask_app.services.profile_csr_service import ProfileCsrService, discover_csr_measures


def test_csr_service_matches_reference_pipeline_tables_when_mounted(tmp_path):
    pipeline = Path(os.environ.get("REFERENCE_PIPELINE", ""))
    reference = pipeline / "02.immunoglobulin/1.CSR/01.csr_matrix.py"
    if not reference.is_file():
        pytest.skip("原始 pipeline 未以 REFERENCE_PIPELINE 挂载")
    profile = tmp_path / "reference-input.csv"
    pd.DataFrame({
        "sample": ["甲1", "甲2", "甲3", "乙1", "乙2", "乙3", "丙1", "丙2", "丙3"],
        "group": ["甲"] * 3 + ["乙"] * 3 + ["丙"] * 3,
        "IGHM-IGHD_CSR_ratio": [0.1, 0.2, 0.4, 0.6, 0.7, 0.9, 0.8, 1.0, 1.2],
        "IGHM-IGHA_CSR_ratio": [0.8, 0.7, 0.6, 0.4, 0.3, 0.2, 0.1, 0.2, 0.3],
        "IGHA-IGHG3_CSR_ratio": [0.1, 0.3, 0.2, 0.4, 0.6, 0.5, 0.9, 0.7, 0.8],
    }).to_csv(profile, index=False)
    reference_output = tmp_path / "reference-output"
    config = tmp_path / "pipeline-config.json"
    config.write_text(json.dumps({
        "paths": {"datapoint_input": str(profile)},
        "outputs": {"root": str(reference_output)},
    }), encoding="utf-8")
    subprocess.run([
        sys.executable, str(reference), "--config", str(config), "--input", str(profile),
        "--output-dir", str(reference_output), "--group-column", "group",
        "--group-order", "甲,乙,丙", "--csr-measure", "CSR_ratio",
    ], check=True, capture_output=True, text=True, timeout=120)
    reference_base = reference_output / "reference-input"

    platform = ProfileCsrService(output_parent=tmp_path / "platform-output").generate_report(
        datapoint_path=str(profile), group_column="group", measure="CSR_ratio",
        group_order=["甲", "乙", "丙"], output_name="platform",
    )
    for reference_name, actual_path in [
        ("CSR_group_median_matrix_source.csv", platform.csv_paths[0]),
        ("CSR_pairwise_mannwhitney_stats.csv", platform.csv_paths[1]),
        ("CSR_kruskal_fdr.csv", platform.csv_paths[2]),
    ]:
        expected = pd.read_csv(reference_base / "file" / reference_name)
        actual = pd.read_csv(actual_path)
        if "field" in expected:
            expected = expected.sort_values([column for column in ("comparison", "group", "field") if column in expected]).reset_index(drop=True)
            actual = actual.sort_values([column for column in ("comparison", "group", "field") if column in actual]).reset_index(drop=True)
        for column in set(expected.columns).intersection(actual.columns):
            if pd.api.types.is_numeric_dtype(expected[column]):
                np.testing.assert_allclose(actual[column], expected[column], rtol=1e-11, atol=1e-12, equal_nan=True)
            else:
                assert actual[column].astype(str).tolist() == expected[column].astype(str).tolist()


def test_csr_report_matches_reference_statistics_and_exports_complete_tables(tmp_path):
    profile = tmp_path / "csr.csv"
    frame = pd.DataFrame({
        "sample": ["A1", "A2", "A3", "B1", "B2", "B3"],
        "group": ["A"] * 3 + ["B"] * 3,
        "IGHM-IGHD_CSR_ratio": [0.10, 0.20, 0.30, 0.80, 0.90, 1.00],
        "IGHM-IGHA_CSR_ratio": [0.20, 0.30, 0.40, 0.60, 0.70, 0.80],
        "IGHA-IGHG3_CSR_ratio": [0.10, 0.30, 0.50, 0.20, 0.40, 0.60],
        "IGHM-IGHD_CSR0": [0, 1, 2, 3, 4, 5],
    })
    frame.to_csv(profile, index=False)

    assert set(discover_csr_measures(frame.columns)) == {"CSR_ratio", "CSR0"}
    report = ProfileCsrService(output_parent=tmp_path / "results").generate_report(
        datapoint_path=str(profile), group_column="group", measure="auto",
        group_order=["B", "A"], output_name="task-csr",
    )

    assert report.metadata["measure"] == "CSR_ratio"
    assert report.metadata["group_order"] == ["B", "A"]
    assert report.metadata["sample_count"] == 6
    pairwise = pd.read_csv(report.csv_paths[1])
    target = pairwise[pairwise["field"] == "IGHM-IGHD_CSR_ratio"].iloc[0]
    expected = mannwhitneyu([0.8, 0.9, 1.0], [0.1, 0.2, 0.3], alternative="two-sided").pvalue
    assert target["comparison"] == "B - A"
    assert target["pvalue"] == expected
    assert target["median_a"] == 0.9
    assert target["median_b"] == 0.2
    assert target["log2_median_ratio"] == np.log2((0.9 + 1e-6) / (0.2 + 1e-6))
    assert "qvalue" in pairwise and "marker" in pairwise

    medians = pd.read_csv(report.csv_paths[0])
    assert len(medians) == 6
    kruskal = pd.read_csv(report.csv_paths[2])
    assert len(kruskal) == 3
    qc = pd.read_csv(report.csv_paths[3])
    assert set(qc["subtype"]) == {"IGHM", "IGHD", "IGHA", "IGHG3"}
    assert len(report.png_paths) == 3
    assert all(path.is_file() and path.stat().st_size > 0 for path in report.png_paths)
    with zipfile.ZipFile(report.zip_path) as archive:
        names = archive.namelist()
    assert "analysis_metadata.json" in names
    assert "file/CSR_pairwise_mannwhitney_stats.csv" in names
    metadata = json.loads((report.output_base / "analysis_metadata.json").read_text(encoding="utf-8"))
    assert metadata["minimum_group_n"] == 2


def test_csr_missing_numeric_values_follow_reference_zero_policy(tmp_path):
    profile = tmp_path / "csr-missing.csv"
    pd.DataFrame({
        "sample": ["A1", "A2", "B1", "B2"],
        "group": ["A", "A", "B", "B"],
        "IGHM-IGHD_CSR1": [None, 0.2, 0.4, 0.6],
    }).to_csv(profile, index=False)
    report = ProfileCsrService(output_parent=tmp_path / "results").generate_report(
        datapoint_path=str(profile), group_column="group", measure="CSR1",
    )
    medians = pd.read_csv(report.csv_paths[0])
    assert medians.loc[medians["group"] == "A", "median"].item() == 0.1
    assert report.metadata["missing_value_policy"].startswith("numeric missing values are treated as 0")


def test_csr_mixed_text_column_drops_unparseable_values_like_reference_script(tmp_path):
    profile = tmp_path / "csr-mixed.csv"
    profile.write_text(
        "sample,group,IGHM-IGHD_CSR_ratio\nA1,A,0.2\nA2,A,not-a-number\nB1,B,0.4\nB2,B,0.6\n",
        encoding="utf-8",
    )
    report = ProfileCsrService(output_parent=tmp_path / "results").generate_report(
        datapoint_path=str(profile), group_column="group", measure="CSR_ratio",
    )
    medians = pd.read_csv(report.csv_paths[0]).set_index("group")
    assert medians.loc["A", "n"] == 1
    assert np.isnan(medians.loc["A", "median"])
    stats = pd.read_csv(report.csv_paths[1]).iloc[0]
    assert stats["n_a"] == 1
    assert np.isnan(stats["pvalue"])
