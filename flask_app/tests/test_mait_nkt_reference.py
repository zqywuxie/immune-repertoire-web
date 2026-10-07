import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_mait_nkt_profile_matches_reference_script(tmp_path):
    from flask_app.services.mait_nkt_service import MaitNktService

    pipeline = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    reference_script = pipeline / "03.UCDR3" / "3.MAIT_NKT" / "01.MAIT_NKT_analysis.py"
    if not reference_script.is_file():
        pytest.skip(f"MAIT/NKT reference script not found: {reference_script}")

    output_root = tmp_path / "pipeline-results"
    pep_category_output = output_root / "03.UCDR3" / "1.Pep" / "3.add_cate_shared"
    pep_category_output.mkdir(parents=True)
    tra_path = pep_category_output / "TRA.csv"
    pd.DataFrame([
        ["group", "A", "B", "Zero"],
        ["CASSAAA", 10, 20, 0],
        ["ASSAAA", 40, 0, 0],
        ["CASSBBB", 5, 0, 0],
        ["CASSCCC", 0, 10, 0],
        ["OTHER", 45, 60, 0],
    ], columns=["CDR3", "sample_a__TRA.csv", "sample_b__TRA.csv", "sample_zero__TRA.csv"]).to_csv(
        tra_path, index=False
    )

    reference_path = tmp_path / "Alpha_Restrict.csv"
    pd.DataFrame([
        {"CDR3": "CASSAAA", "Type": "MAIT"},
        {"CDR3": "CASSBBB", "Type": "MAIT"},
        # Exact matching must not turn ASSAAAF into the observed ASSAAA.
        {"CDR3": "ASSAAAF", "Type": "MAIT"},
        {"CDR3": "CASSCCC", "Type": "iNKT"},
    ]).to_csv(reference_path, index=False)

    config_path = tmp_path / "analysis.json"
    config_path.write_text(json.dumps({
        "outputs": {"root": str(output_root)},
        "references": {"mait_nkt_reference": str(reference_path)},
        "datapoint": {"group_column": "group", "group_order": ["A", "B", "Zero"]},
    }), encoding="utf-8")

    subprocess.run(
        [sys.executable, str(reference_script), "--config", str(config_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    expected = pd.read_csv(
        output_root / "03.UCDR3" / "3.MAIT_NKT" / "01.MAIT_NKT_analysis" / "MAIT_iNKT_profile.csv"
    ).rename(columns={"group": "category"})

    service = MaitNktService(output_parent=tmp_path / "platform-results")
    service._reference_path = reference_path
    progress = []
    report = service.generate_report(
        tra_df=pd.read_csv(tra_path),
        profile_df=pd.DataFrame(),
        group_field="group",
        group_order=["A", "B", "Zero"],
        progress_callback=lambda percent, stage, detail: progress.append((stage, detail)),
    )
    actual = pd.read_csv(report.csv_paths[0])
    reference_version = report.metadata["reference_version"]
    assert reference_version["available"] is True
    assert reference_version["path"] == str(reference_path.resolve())
    assert len(reference_version["sha256"]) == 64

    assert [stage for stage, _ in progress] == ["读取参考数据", "计算样本指标", "生成分组图表", "整理结果页面", "分析完成"]
    assert all("Loading" not in stage and "Generating" not in detail for stage, detail in progress)
    assert actual["sample"].tolist() == expected["sample"].tolist()
    for column in ("MAIT_sum", "MAIT_log10", "MAIT_fraction", "iNKT_sum", "iNKT_log10", "iNKT_fraction"):
        np.testing.assert_allclose(actual[column], expected[column], rtol=0, atol=1e-12, equal_nan=True)
    assert actual.loc[actual["sample"] == "sample_a__TRA.csv", "MAIT_sum"].iloc[0] == 15
    assert np.isnan(actual.loc[actual["sample"] == "sample_zero__TRA.csv", "MAIT_fraction"]).all()


def test_mait_nkt_profile_preserves_leading_zero_sample_ids(monkeypatch, tmp_path):
    from flask_app.services.mait_nkt_service import MaitNktService

    monkeypatch.setattr(MaitNktService, "_load_reference", lambda self: {"MAIT": ["CASSAAA"]})
    monkeypatch.setattr(
        MaitNktService,
        "_make_boxplot",
        lambda self, **kwargs: Path(kwargs["out_path"]).write_bytes(b"png"),
    )
    service = MaitNktService(output_parent=tmp_path / "results")
    reference_path = tmp_path / "Alpha_Restrict.csv"
    reference_path.write_text("CDR3,Type\nCASSAAA,MAIT\n", encoding="utf-8")
    service._reference_path = reference_path
    report = service.generate_report(
        tra_df=pd.DataFrame([["CASSAAA", 5]], columns=["CDR3", "001__TRA.csv"]),
        profile_df=pd.DataFrame({"sample": ["001"], "group": ["病例"]}),
        group_field="group",
    )

    result = pd.read_csv(report.csv_paths[0], dtype={"sample": str})
    assert result["sample"].tolist() == ["001__TRA.csv"]
    assert report.metadata["reference_version"]["sha256"]
    assert result["category"].tolist() == ["病例"]


@pytest.mark.parametrize(
    ("sample_columns", "profile_samples", "message"),
    [
        (["sample_1__TRA.csv"], ["sample_1", "sample_1.csv"], "样本编号“sample_1”重复"),
        (["sample_1__TRA.csv", "sample_2__TRA.csv"], ["sample_1"], "未匹配到 1 个 TRA 样本"),
        (["sample_1__TRA.csv", "sample_1.csv"], ["sample_1"], "无法区分的同名样本"),
    ],
)
def test_mait_nkt_rejects_ambiguous_or_unmatched_samples(
    monkeypatch, tmp_path, sample_columns, profile_samples, message
):
    from flask_app.services.mait_nkt_service import MaitNktService

    monkeypatch.setattr(MaitNktService, "_load_reference", lambda self: {"MAIT": ["CASSAAA"]})
    service = MaitNktService(output_parent=tmp_path / "results")
    tra_df = pd.DataFrame([["CASSAAA", *([5] * len(sample_columns))]], columns=["CDR3", *sample_columns])
    profile_df = pd.DataFrame({"sample": profile_samples, "group": ["病例"] * len(profile_samples)})

    with pytest.raises(ValueError, match=message):
        service.generate_report(tra_df=tra_df, profile_df=profile_df, group_field="group")
