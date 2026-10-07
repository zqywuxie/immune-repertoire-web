import importlib.util
import json
import os
import sys
from argparse import Namespace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.services.unified_umap_service import (
    UnifiedUmapService,
    calculate_permanova,
    preprocess_features,
    select_features_by_raw_p,
)


def _reference_module(tmp_path, monkeypatch):
    pipeline = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    script = pipeline / "10.Umap" / "01.umap_analysis.py"
    if not script.is_file():
        pytest.skip("未找到原始 10.Umap/01.umap_analysis.py")
    output_root = tmp_path / "ref"
    metadata = output_root / "0.config" / "01.prepare_pep" / "datapoint.csv"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("sample,group\nS1,A\n", encoding="utf-8")
    config = tmp_path / "analysis.json"
    config.write_text(json.dumps({"outputs": {"root": str(output_root)}}), encoding="utf-8")
    monkeypatch.syspath_prepend(str(pipeline))
    monkeypatch.setattr(sys, "argv", [str(script), "--config", str(config)])
    module_spec = importlib.util.spec_from_file_location("reference_unified_umap", script)
    module = importlib.util.module_from_spec(module_spec)
    assert module_spec and module_spec.loader
    module_spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_unified_umap_feature_selection_scaling_and_permanova_match_reference(tmp_path, monkeypatch):
    reference = _reference_module(tmp_path, monkeypatch)
    frame = pd.DataFrame({
        "sample": [f"S{i}" for i in range(8)],
        "label": ["A"] * 4 + ["B"] * 4,
        "VJ__TRA__V1": [0, 0, 1, 0, 8, 9, 8, 10],
        "PROFILE__metric": [2, 1, 2, 3, 9, 8, 9, 10],
        "PROFILE__stable": [1] * 8,
    })
    features = ["VJ__TRA__V1", "PROFILE__metric", "PROFILE__stable"]
    actual_selected, actual_selection = select_features_by_raw_p(frame, features, "A", "B", 0.05)
    expected_selected, expected_selection = reference.select_features_by_raw_p(frame, features, "A", "B", 0.05)
    assert actual_selected == expected_selected
    np.testing.assert_allclose(actual_selection["raw_p_value"], expected_selection["raw_p_value"], rtol=0, atol=1e-15, equal_nan=True)

    actual_values, actual_retained, _ = preprocess_features(frame, actual_selected)
    expected_values, expected_retained, _ = reference.preprocess_features(frame, expected_selected)
    assert actual_retained == expected_retained
    np.testing.assert_allclose(actual_values, expected_values, rtol=0, atol=1e-12)

    actual_stats = calculate_permanova(actual_values, frame["label"], permutations=49, random_state=42)
    expected_stats = reference.calculate_permanova(actual_values, frame["label"], permutations=49, random_state=42)
    for key in ("pseudo_F", "R2", "raw_p_value"):
        assert actual_stats[key] == pytest.approx(expected_stats[key], rel=1e-12, abs=1e-12)
    assert actual_stats["status"] == expected_stats["status"] == "ok"


def test_unified_umap_service_exports_pairwise_results_and_projection(tmp_path):
    profile = tmp_path / "profile.csv"
    pd.DataFrame({
        "sample": [f"S{i}" for i in range(8)],
        "group": ["A"] * 4 + ["B"] * 4,
        "metric_1": [0, 1, 2, 1, 12, 11, 10, 13],
        "metric_2": [3, 2, 4, 3, 9, 11, 10, 12],
    }).to_csv(profile, index=False)

    events = []
    report = UnifiedUmapService(output_parent=tmp_path / "results").generate_report(
        profile_path=str(profile), sample_column="sample", label_column="group",
        configurations=["profile"], profile_start="metric_1", profile_end="metric_2",
        raw_p_threshold=0.05, n_neighbors=3, min_dist=0.01, n_epochs=30,
        permutations=19, random_state=42, permanova_random_state=42,
        progress_callback=lambda *event: events.append(event),
    )

    stats = pd.read_csv(report.output_base / "profile" / "pairwise_permanova.csv")
    coordinates = pd.read_csv(report.output_base / "profile" / "umap_coordinates.csv")
    selection = pd.read_csv(report.output_base / "profile" / "selected_features.csv")
    assert stats.loc[0, "status"] == "ok"
    assert len(coordinates) == 8
    assert coordinates[["UMAP1", "UMAP2"]].notna().all().all()
    assert set(selection.loc[selection["selection_status"] == "selected", "feature"]) == {
        "PROFILE__metric_1", "PROFILE__metric_2"
    }
    assert report.png_paths and report.zip_path.is_file()
    assert [event[0] for event in events] == sorted(event[0] for event in events)
    assert any(event[1] == "UMAP 降维" and "首次启动" in event[2] for event in events)


def test_unified_umap_projection_value_error_is_recorded_as_skipped(tmp_path, monkeypatch):
    import umap.umap_

    def fail_projection(self, values):
        raise ValueError("合成投影失败")

    monkeypatch.setattr(umap.umap_.UMAP, "fit_transform", fail_projection)
    profile = tmp_path / "profile.csv"
    pd.DataFrame({
        "sample": [f"S{i}" for i in range(8)],
        "group": ["A"] * 4 + ["B"] * 4,
        "metric": [0, 1, 2, 1, 12, 11, 10, 13],
    }).to_csv(profile, index=False)

    report = UnifiedUmapService(output_parent=tmp_path / "results").generate_report(
        profile_path=str(profile), sample_column="sample", label_column="group",
        configurations=["profile"], profile_start="metric", profile_end="metric",
        raw_p_threshold=0.05, n_neighbors=3, n_epochs=30, permutations=9,
    )

    stats = pd.read_csv(report.output_base / "profile" / "pairwise_permanova.csv")
    coordinates = pd.read_csv(report.output_base / "profile" / "umap_coordinates.csv")
    assert stats.loc[0, "status"] == "skipped"
    assert stats.loc[0, "reason"] == "合成投影失败"
    assert coordinates.empty
    assert report.zip_path.is_file()


def test_unified_umap_uses_batch_composite_identity_for_repeated_samples(tmp_path):
    profile = tmp_path / "profile.csv"
    rows = []
    usage_rows = []
    for batch, group, offset in (("run-a", "A", 0), ("run-b", "B", 10)):
        for index in range(4):
            sample = f"S{index + 1}"
            rows.append({"sample": sample, "batch": batch, "group": group, "metric": offset + index})
            usage_rows.append({"sample": f"{batch}::{sample}", "Category": group, "feature": offset + index})
    pd.DataFrame(rows).to_csv(profile, index=False)
    usage = tmp_path / "vj_usage.csv"
    pd.DataFrame(usage_rows).to_csv(usage, index=False)

    report = UnifiedUmapService(output_parent=tmp_path / "results").generate_report(
        profile_path=str(profile), sample_column="sample", label_column="group",
        batch_field="batch", configurations=["vj"], vj_usage_path=str(usage),
        raw_p_threshold=0.05, n_neighbors=3, n_epochs=30, permutations=9,
    )

    coordinates = pd.read_csv(report.output_base / "vj" / "umap_coordinates.csv", dtype=str)
    stats = pd.read_csv(report.output_base / "vj" / "pairwise_permanova.csv")
    assert len(coordinates) == 8
    assert set(coordinates["sample"]) == {f"{batch}::S{index}" for batch in ("run-a", "run-b") for index in range(1, 5)}
    assert set(coordinates["source_batch"]) == {"run-a", "run-b"}
    assert set(coordinates["source_sample"]) == {f"S{index}" for index in range(1, 5)}
    assert stats.loc[0, "n_samples"] == 8
    assert report.metadata["sample_identity_rule"] == "batch::sample"


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_unified_umap_coordinates_match_reference_embedding(tmp_path, monkeypatch):
    reference = _reference_module(tmp_path, monkeypatch)
    profile = tmp_path / "profile.csv"
    frame = pd.DataFrame({
        "sample": [f"S{i}" for i in range(8)],
        "group": ["A"] * 4 + ["B"] * 4,
        "metric_1": [0, 1, 2, 1, 12, 11, 10, 13],
        "metric_2": [3, 2, 4, 3, 9, 11, 10, 12],
    })
    frame.to_csv(profile, index=False)
    report = UnifiedUmapService(output_parent=tmp_path / "results").generate_report(
        profile_path=str(profile), sample_column="sample", label_column="group",
        configurations=["profile"], profile_start="metric_1", profile_end="metric_2",
        raw_p_threshold=0.05, n_neighbors=3, min_dist=0.01, n_epochs=30,
        permutations=19, random_state=42, permanova_random_state=42,
    )

    comparison = frame.rename(columns={"group": "label"})
    features = ["PROFILE__metric_1", "PROFILE__metric_2"]
    feature_frame = pd.DataFrame({"sample": comparison["sample"], "label": comparison["label"], **{
        "PROFILE__metric_1": comparison["metric_1"],
        "PROFILE__metric_2": comparison["metric_2"],
    }})
    selected, _ = reference.select_features_by_raw_p(feature_frame, features, "A", "B", 0.05)
    values, _, _ = reference.preprocess_features(feature_frame, selected)
    expected, _ = reference.compute_umap(values, feature_frame["sample"], feature_frame["label"], Namespace(
        n_neighbors=3, min_dist=0.01, metric="euclidean", n_epochs=30, random_state=42,
    ))
    actual = pd.read_csv(report.output_base / "profile" / "umap_coordinates.csv")
    np.testing.assert_allclose(actual[["UMAP1", "UMAP2"]], expected[["UMAP1", "UMAP2"]], rtol=1e-6, atol=1e-6)
