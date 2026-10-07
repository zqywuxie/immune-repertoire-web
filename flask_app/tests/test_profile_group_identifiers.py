"""Regression for raw grouping identifiers across the real Profile report outputs."""
import json
from pathlib import Path

import pandas as pd
import pytest
from scipy.stats import mannwhitneyu

from flask_app.services.boxplot_service import BoxPlotService


@pytest.mark.parametrize("suffix", [".csv", ".tsv", ".xlsx"])
@pytest.mark.parametrize("selection", ["fields", "range"])
def test_profile_groups_keep_original_text_and_order(tmp_path, suffix, selection):
    groups = ["01", "1", "02"]
    values = [1., 2., 3., 4., 8., 9., 10., 11., 20., 21., 22., 23.]
    frame = pd.DataFrame({
        "sample": [f"{n:03d}" for n in range(1, 13)],
        "类别": [group for group in groups for _ in range(4)],
        "批次": ["001"] * 12,
        "TRA_Shannon": values,
        "TRB_Shannon": [2.] * 12,
    })
    source = tmp_path / ("样本指标" + suffix)
    if suffix == ".xlsx":
        frame.to_excel(source, index=False)
    else:
        frame.to_csv(source, index=False, sep="\t" if suffix == ".tsv" else ",")
    before = source.read_bytes()
    selected = ["001", "003", "005", "007", "009", "011"]
    selection_args = ({"grouptype_fields": ["类别", "批次"]}
        if selection == "fields" else {"classification_begin": "类别", "classification_over": "批次"})
    report = BoxPlotService(output_parent=tmp_path / "results").generate_report(
        datapoint_path=str(source), param_begin="TRA_Shannon", param_over="TRB_Shannon",
        group_order=json.dumps({"类别": ["02", "01", "1"]}),
        selected_samples=selected,
        selected_samples_by_group={"类别": {"01": selected[:2], "1": selected[2:4], "02": selected[4:]}},
        **selection_args,
    )
    assert source.read_bytes() == before
    assert report.metadata["class_columns"] == ["类别", "批次"]
    assert report.metadata["class_type_counts"] == {"类别": 3, "批次": 1}
    assert report.metadata["sample_filter"]["matched_count"] == 6
    assert report.metadata["sample_filter"]["unmatched_samples"] == []
    table = pd.read_csv(next(p for p in report.csv_paths if Path(p).parent.parent.name == "类别"),
                        dtype={"sample": str, "类别": str})
    assert table["类别"].tolist() == ["02", "02", "01", "01", "1", "1"]
    assert table["sample"].tolist() == ["009", "011", "001", "003", "005", "007"]
    assert table["TRA_Shannon"].tolist() == [20., 22., 1., 3., 8., 10.]
    assert pd.api.types.is_numeric_dtype(table["TRA_Shannon"])
    stats = pd.read_csv(report.pvalue_paths[0], dtype={"group_a": str, "group_b": str})
    assert stats.loc[stats["param"] == "TRB_Shannon", "pvalue"].tolist() == [1., 1., 1.]
    stats = stats[stats["param"] == "TRA_Shannon"]
    assert list(zip(stats["group_a"], stats["group_b"])) == [("02", "01"), ("02", "1"), ("01", "1")]
    expected_values = {"01": [1., 3.], "1": [8., 10.], "02": [20., 22.]}
    for row in stats.itertuples():
        expected = mannwhitneyu(expected_values[row.group_a], expected_values[row.group_b],
                                alternative="two-sided").pvalue
        assert row.pvalue == pytest.approx(expected, rel=1e-12, abs=1e-12)
    summary = pd.read_csv(report.metadata["summary_csv_paths"][0], dtype={"group": str})
    assert set(summary["group"]) == set(groups)
    viewer = report.viewer_path.read_text(encoding="utf-8")
    assert '<strong>分类字段</strong><span>类别, 批次</span>' in viewer
    assert '<strong>分类字段</strong><span>未分组</span>' not in viewer
    assert json.loads((report.output_base / "boxplot_metadata.json").read_text(encoding="utf-8")) == report.metadata


def test_missing_group_retains_existing_zero_category(tmp_path):
    source = tmp_path / "profile.csv"
    source.write_text("sample,group,metric\n001,01,1\n002,01,2\n003,,8\n004,,9\n", encoding="utf-8")
    report = BoxPlotService(output_parent=tmp_path / "results").generate_report(
        datapoint_path=str(source), grouptype_fields=["group"],
        param_begin="metric", param_over="metric", group_order="01,0",
    )
    table = pd.read_csv(report.csv_paths[0], dtype={"sample": str, "group": str})
    assert table["group"].tolist() == ["01", "01", "0", "0"]
    assert report.metadata["class_type_counts"] == {"group": 2}
