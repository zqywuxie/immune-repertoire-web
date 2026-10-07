import importlib.util
import json
import os
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import matplotlib as mpl
from pandas.testing import assert_frame_equal
from sklearn.preprocessing import LabelEncoder

from flask_app.services.ml_analysis_service import MLAnalysisService


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_ml_profile_cohort_and_feature_matrix_match_reference(tmp_path, monkeypatch):
    pipeline = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    script = pipeline / "09.ML" / "01.ML.py"
    if not script.is_file():
        pytest.skip(f"ML reference script not found: {script}")

    profile = tmp_path / "profile.csv"
    frame = pd.DataFrame({
        "Sample": ["S01", "S02", "S03", "S04", "S05", "S06"],
        "Disease": ["Control", "Control", "Control", "Case", "Case", "Case"],
        "feature_a": [0.1, 0.2, 0.3, 1.1, 1.2, 1.3],
        "annotation": ["low", "medium", "high", "low", "medium", "high"],
        "feature_b": [5, 4, 3, 2, 1, 0],
        "outside_range": [99, 98, 97, 96, 95, 94],
    })
    frame.to_csv(profile, index=False)
    config = tmp_path / "reference-config.json"
    config.write_text(json.dumps({
        "default_profile": "default",
        "datapoint_profiles": {"default": {
            "input_path_key": "datapoint_input",
            "sample_column": "Sample",
            "group_column": "Disease",
            "group_order": ["Control", "Case"],
        }},
        "paths": {"datapoint_input": str(profile)},
        "outputs": {"root": str(tmp_path / "reference-output")},
        "profile": {"parameter_selection": {
            "mode": "explicit",
            "start": "feature_a",
            "end": "feature_b",
            "include": ["feature_a", "feature_b"],
            "exclude": [],
        }},
    }), encoding="utf-8")

    monkeypatch.syspath_prepend(str(pipeline))
    monkeypatch.setattr(sys, "argv", [str(script), "--config", str(config)])
    plotting_style = mpl.rcParams.copy()
    spec = importlib.util.spec_from_file_location("reference_ml_for_test", script)
    reference = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(reference)
    mpl.rcParams.update(plotting_style)

    args = Namespace(
        profile_input=profile,
        sample_column="Sample",
        profile_id_column="Sample",
        label_column="Disease",
        include_labels=[],
        exclude_groups=[],
        param_start="feature_a",
        param_end="feature_b",
    )
    reference_metadata = reference.load_metadata(args)
    reference_features, _ = reference.load_profile(args)

    platform_features, platform_labels, encoder = MLAnalysisService._prepare_profile_xy(
        frame,
        sample_col="Sample",
        label_col="Disease",
        param_begin="feature_a",
        param_over="feature_b",
    )
    expected = (
        reference_features
        .drop(columns="sample")
        .rename(columns=lambda column: column.removeprefix("PROFILE__"))
        .reset_index(drop=True)
    )
    assert_frame_equal(
        platform_features.reset_index(drop=True),
        expected,
        check_dtype=False,
        check_names=True,
        check_exact=True,
    )
    assert reference_metadata["sample"].tolist() == frame["Sample"].tolist()
    assert reference_metadata["label"].tolist() == frame["Disease"].tolist()
    np.testing.assert_array_equal(
        platform_labels,
        LabelEncoder().fit_transform(reference_metadata["label"].astype(str)),
    )
    assert encoder.classes_.tolist() == ["Case", "Control"]



@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_ml_vj_matrix_merges_disjoint_chain_rows_and_rejects_overlaps(tmp_path, monkeypatch):
    pipeline = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    script = pipeline / "09.ML" / "01.ML.py"
    if not script.is_file():
        pytest.skip(f"ML reference script not found: {script}")

    profile = tmp_path / "profile.csv"
    pd.DataFrame({
        "Sample": ["S01", "S02"],
        "Disease": ["Control", "Case"],
        "feature": [1.0, 2.0],
    }).to_csv(profile, index=False)
    config = tmp_path / "reference-config.json"
    config.write_text(json.dumps({
        "default_profile": "default",
        "datapoint_profiles": {"default": {
            "input_path_key": "datapoint_input",
            "sample_column": "Sample",
            "group_column": "Disease",
        }},
        "paths": {"datapoint_input": str(profile)},
        "outputs": {"root": str(tmp_path / "reference-output")},
    }), encoding="utf-8")
    monkeypatch.syspath_prepend(str(pipeline))
    monkeypatch.setattr(sys, "argv", [str(script), "--config", str(config)])
    plotting_style = mpl.rcParams.copy()
    spec = importlib.util.spec_from_file_location("reference_ml_vj_for_test", script)
    reference = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(reference)
    mpl.rcParams.update(plotting_style)
    args = Namespace(vj_usage_dir=None, vj_id_column="sample")

    usage_dir = tmp_path / "usage"
    usage_dir.mkdir()
    usage = pd.DataFrame({
        "sample": ["S01__TRB", "S01__TRA", "S02__TRB"],
        "gene_a": [1.0, np.nan, 4.0],
        "gene_b": [np.nan, 3.0, 5.0],
        "Category": ["Control", "Control", "Case"],
    })
    usage.to_csv(usage_dir / "TRB.csv", index=False)
    args.vj_usage_dir = usage_dir

    reference_matrix, _ = reference.load_vj_usage_dir(args, {"S01", "S02"})
    platform_matrix = MLAnalysisService(output_parent=tmp_path / "platform")._build_usage_feature_matrix(
        {"S01", "S02"}, usage_dir, "Sample",
    )
    expected = (
        reference_matrix.rename(columns={"sample": "Sample"})
        .rename(columns=lambda column: column.removeprefix("VJ__"))
        .sort_values("Sample")
        .reset_index(drop=True)
    )
    actual = platform_matrix.sort_values("Sample").reset_index(drop=True)
    assert_frame_equal(actual, expected, check_dtype=False, check_exact=True)

    overlap = usage.copy()
    overlap.loc[1, "gene_a"] = 2.0
    overlap.to_csv(usage_dir / "TRB.csv", index=False)
    with pytest.raises(ValueError, match="VJ .*重叠"):
        reference.load_vj_usage_dir(args, {"S01", "S02"})
    with pytest.raises(ValueError, match="VJ .*overlap"):
        MLAnalysisService(output_parent=tmp_path / "platform-overlap")._build_usage_feature_matrix(
            {"S01", "S02"}, usage_dir, "Sample",
        )
