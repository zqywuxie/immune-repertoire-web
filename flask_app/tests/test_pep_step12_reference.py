import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from flask_app.services.pep_analysis_service import PepAnalysisService


REFERENCE_PIPELINE = os.environ.get("REFERENCE_PIPELINE")


def _usage_frame():
    return pd.DataFrame([
        {"sample": "C1", "Category": "control", "TRBV1": 1, "TRBV2": 9},
        {"sample": "C2", "Category": "control", "TRBV1": 2, "TRBV2": 8},
        {"sample": "C3", "Category": "control", "TRBV1": 1, "TRBV2": 10},
        {"sample": "P1", "Category": "case", "TRBV1": 9, "TRBV2": 2},
        {"sample": "P2", "Category": "case", "TRBV1": 10, "TRBV2": 1},
        {"sample": "P3", "Category": "case", "TRBV1": 8, "TRBV2": 2},
    ])


def test_step12_is_wired_into_pep_report_and_result_archive(tmp_path):
    pep = tmp_path / "pep"
    pep.mkdir()
    profile = tmp_path / "profile.csv"
    samples = ["C1", "C2", "C3", "P1", "P2", "P3"]
    groups = ["control"] * 3 + ["case"] * 3
    pd.DataFrame({"sample": samples, "group": groups}).to_csv(profile, index=False)
    for sample, group in zip(samples, groups):
        high_v1 = group == "case"
        rows = [
            {"CDR3(pep)": f"{sample}-A", "V": "TRBV1" if high_v1 else "TRBV2", "J": "TRBJ1", "copy": 20},
            {"CDR3(pep)": f"{sample}-B", "V": "TRBV2" if high_v1 else "TRBV1", "J": "TRBJ2", "copy": 2},
        ]
        pd.DataFrame(rows).to_csv(pep / f"{sample}__TRB.csv", index=False)

    report = PepAnalysisService(output_parent=tmp_path / "report-results").generate_report(
        pep_data_dir=str(pep), profile_path=str(profile), group_fields=["group"],
        selected_chains=["TRB"], optional_steps={12}, group_order={"group": ["case", "control"]},
    )

    summary = next(item for item in report.metadata["step_summary"] if item["step"] == 12)
    assert summary["status"] == "completed"
    assert summary["output_counts"]["summary_files"] > 0
    assert summary["output_counts"]["usage_diff_images"] > 0
    output = report.output_base / "group/VJ_usage_diff_summary/group/case_vs_control/1Vusage/TRB/top10_diff_genes.csv"
    assert output.is_file()
    table = pd.read_csv(output).set_index("Gene")
    assert table.loc["TRBV1", "diff"] > 0
    with zipfile.ZipFile(report.zip_path) as archive:
        assert any(name.endswith("top10_diff_genes.csv") for name in archive.namelist())
        assert any(name.endswith("top10_usage_diff_barplot.png") for name in archive.namelist())
    assert any(item.get("step") == "12" for item in report.metadata["image_files"])


@pytest.mark.skipif(not REFERENCE_PIPELINE, reason="Reference pipeline is not mounted")
def test_step12_vj_usage_summary_matches_reference_pipeline(tmp_path):
    output_root = tmp_path / "reference-results"
    usage_root = output_root / "03.UCDR3/1.Pep/4.add_cate_usage/group/usage/1Vusage"
    usage_root.mkdir(parents=True)
    _usage_frame().to_csv(usage_root / "TRB.csv", index=False)
    config = tmp_path / "analysis.json"
    config.write_text(json.dumps({
        "outputs": {"root": str(output_root)},
        "datapoint": {"group_column": "Category", "group_order": ["case", "control"]},
    }), encoding="utf-8")

    script = Path(REFERENCE_PIPELINE) / "03.UCDR3/1.Pep/8.VJ_statistication.py"
    subprocess.run(
        [sys.executable, str(script), f"--config={config}"],
        check=True, capture_output=True, text=True,
    )

    platform_usage_root = tmp_path / "platform-results/group/usage_cate/usage"
    platform_usage = platform_usage_root / "1Vusage"
    platform_usage.mkdir(parents=True)
    _usage_frame().to_csv(platform_usage / "TRB.csv", index=False)
    generated = PepAnalysisService._run_step12_for_group(
        platform_usage_root,
        tmp_path / "platform-results/group/VJ_usage_diff_summary",
        group_field="Category",
        group_name="group",
        group_order=["case", "control"],
    )

    reference_csv = output_root / (
        "03.UCDR3/1.Pep/8.top10_usage_diff_summary/group/case_vs_control/1Vusage/TRB/"
        "top10_diff_genes.csv"
    )
    platform_csv = tmp_path / (
        "platform-results/group/VJ_usage_diff_summary/group/case_vs_control/1Vusage/TRB/"
        "top10_diff_genes.csv"
    )
    assert str(platform_csv) in generated
    actual = pd.read_csv(platform_csv).sort_values("Gene").reset_index(drop=True)
    expected = pd.read_csv(reference_csv).sort_values("Gene").reset_index(drop=True)
    assert_frame_equal(actual, expected, check_dtype=False, check_names=False, rtol=1e-12, atol=1e-12)
