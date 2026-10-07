import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.services.profile_composition_service import ProfileCompositionService


def _datapoint(path: Path) -> pd.DataFrame:
    frame = pd.DataFrame({
        "sample": ["B-02", "A-01", "A-02", "B-01"],
        "group": ["乙", "甲", "甲", "乙"],
        "TRA_Percent": [40, 2, 2, 25],
        "TRB_Percent": [60, 1, np.nan, 75],
        "IGH_Percent": [20, 50, 0, 15],
        "IGK_Percent": [80, 50, 100, 85],
        "IGHM_percent_by_reads": [12, 20, 35, 15],
        "IGHA1_percent_by_reads": [88, 80, 65, 85],
    })
    frame.to_csv(path, index=False)
    return frame


def test_profile_composition_closes_sample_fractions_and_exports_quality(tmp_path):
    source = tmp_path / "datapoint.csv"
    _datapoint(source)
    report = ProfileCompositionService(output_parent=tmp_path / "results").generate_report(
        datapoint_path=str(source), group_column="group", group_order=["甲", "乙"], measure="reads"
    )

    assert len(report.png_paths) == 2
    assert len(report.csv_paths) == 3
    chain = pd.read_csv(next(path for path in report.csv_paths if "受体链构成" in path.name))
    qc = pd.read_csv(next(path for path in report.csv_paths if path.name == "样本质量与排序.csv"))
    np.testing.assert_allclose(chain.groupby("sample")["percent"].sum().sort_index(), 100.0, atol=1e-12)
    a02 = chain[chain["sample"] == "A-02"].set_index("component")["percent"]
    np.testing.assert_allclose(a02[["TRA_Percent", "TRB_Percent", "IGH_Percent", "IGK_Percent"]], [2 / 102 * 100, 0, 0, 100 / 102 * 100], atol=1e-12)
    assert qc.loc[qc["sample"] == "A-02", "missing_components_replaced_with_zero"].item() == 1
    assert report.metadata["group_order"] == ["甲", "乙"]
    assert report.zip_path.is_file()


def test_profile_composition_rejects_negative_or_empty_sample_compositions(tmp_path):
    source = tmp_path / "bad.csv"
    frame = _datapoint(source)
    frame.loc[0, ["TRA_Percent", "TRB_Percent", "IGH_Percent", "IGK_Percent"]] = [-1, 0, 0, 0]
    frame.to_csv(source, index=False)
    with pytest.raises(ValueError, match="不能为负数"):
        ProfileCompositionService(output_parent=tmp_path / "negative").generate_report(datapoint_path=str(source), group_column="group")

    frame.loc[0, ["TRA_Percent", "TRB_Percent", "IGH_Percent", "IGK_Percent"]] = [0, 0, 0, 0]
    frame.to_csv(source, index=False)
    with pytest.raises(ValueError, match="至少要有一个"):
        ProfileCompositionService(output_parent=tmp_path / "empty").generate_report(datapoint_path=str(source), group_column="group")


def test_profile_composition_matches_original_r_helper(tmp_path):
    reference_root = os.environ.get("REFERENCE_PIPELINE")
    if not reference_root:
        pytest.skip("需要只读挂载原始 pipeline 并设置 REFERENCE_PIPELINE")

    source = tmp_path / "datapoint.csv"
    _datapoint(source)
    report = ProfileCompositionService(output_parent=tmp_path / "platform").generate_report(
        datapoint_path=str(source), group_column="group", group_order=["甲", "乙"], measure="reads"
    )
    original_root = Path(reference_root) / "01.Profile" / "2.composition"
    r_script = tmp_path / "compare.R"
    r_script.write_text(
        '''args <- commandArgs(trailingOnly=TRUE)
source(file.path(args[[1]], "plot_percent_composition_common.R"))
dat <- read.csv(args[[2]], check.names=FALSE, stringsAsFactors=FALSE)
components <- c("TRA_Percent", "TRB_Percent", "IGH_Percent", "IGK_Percent")
labels <- setNames(c("TRA", "TRB", "IGH", "IGK"), components)
palette <- setNames(c("#4E79A7", "#79A9CF", "#9CC9D5", "#A8D5C2"), components)
groups <- c("甲", "乙")
group_labels <- setNames(groups, groups)
group_palette <- setNames(c("#5B82A6", "#D29A61"), groups)
result <- plot_percent_composition(dat, "sample", "group", components, labels, palette,
  groups, group_labels, group_palette, "", args[[3]])
write.csv(result$source_data, args[[4]], row.names=FALSE, fileEncoding="UTF-8")
write.csv(result$qc, args[[5]], row.names=FALSE, fileEncoding="UTF-8")
''',
        encoding="utf-8",
    )
    original_long = tmp_path / "original-long.csv"
    original_qc = tmp_path / "original-qc.csv"
    original_png = tmp_path / "original.png"
    subprocess.run([
        "Rscript", str(r_script), str(original_root), str(source), str(original_png),
        str(original_long), str(original_qc),
    ], check=True, capture_output=True, text=True)

    platform_long = pd.read_csv(next(path for path in report.csv_paths if path.name == "受体链构成_样本构成.csv"))
    original_long_df = pd.read_csv(original_long)
    pd.testing.assert_frame_equal(
        platform_long[["sample", "group", "component", "fraction", "percent"]],
        original_long_df[["sample", "Group", "Component", "Fraction", "Percent"]].rename(
            columns={"Group": "group", "Component": "component", "Fraction": "fraction", "Percent": "percent"}
        ), check_dtype=False, check_exact=False, rtol=1e-12, atol=1e-12,
    )
    assert original_png.is_file()
    platform_qc = pd.read_csv(next(path for path in report.csv_paths if path.name == "样本质量与排序.csv"))
    original_qc_df = pd.read_csv(original_qc).rename(columns={"Group": "group"})
    pd.testing.assert_frame_equal(
        platform_qc[["sample", "group", "missing_components_replaced_with_zero", "total_before_closure", "total_after_closure", "plot_order"]],
        original_qc_df[["sample", "group", "missing_components_replaced_with_zero", "total_before_closure", "total_after_closure", "plot_order"]],
        check_dtype=False, check_exact=False, rtol=1e-12, atol=1e-12,
    )
