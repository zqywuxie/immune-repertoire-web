import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.services.igh_subclass_topclone_service import (
    IgSubclassTopCloneService,
    normalize_c_call,
)


def _pep_rows(sample_index):
    rows = []
    for index in range(12):
        rows.append({"c_call": "IGHM*01", "CDR3(pep)": f"M{index}", "copy": sample_index + index + 1})
    for index in range(12):
        rows.append({"c_call": "IGHA1*01", "CDR3(pep)": f"A{index}", "copy": index + sample_index + 1})
    rows.extend([
        {"c_call": "IGHA1*01/IGHG1*01", "CDR3(pep)": "ambiguous", "copy": 10},
        {"c_call": "unknown", "CDR3(pep)": "unmatched", "copy": 7},
        {"c_call": "IGHG1*01", "CDR3(pep)": "bad", "copy": -2},
    ])
    return pd.DataFrame(rows)


def _write_inputs(root: Path):
    pep_root = root / "pep" / "IGH"
    pep_root.mkdir(parents=True)
    sample_ids = ["A1", "A2", "B1", "B2"]
    profile = root / "profile.csv"
    pd.DataFrame({"sample": sample_ids, "group": ["A", "A", "B", "B"]}).to_csv(profile, index=False)
    for index, sample in enumerate(sample_ids):
        _pep_rows(index).to_csv(pep_root / f"{sample}__IGH.csv", index=False)
    return pep_root, profile


def test_igh_subclass_topclone_preserves_normalization_and_outputs_complete_results(tmp_path):
    pep_root, profile = _write_inputs(tmp_path)
    report = IgSubclassTopCloneService(output_parent=tmp_path / "results").generate_report(
        pep_paths=[str(pep_root)], datapoint_path=str(profile), group_column="group",
        group_order=["B", "A"], output_name="igh-topclone",
    )

    assert report.metadata["group_order"] == ["B", "A"]
    assert report.metadata["top_n_values"] == [10, 20, 50, 100]
    assert "within each IGH subclass" in report.metadata["denominator"]
    values = pd.read_csv(report.csv_paths[0])
    row = values.loc[values["sample"] == "A1"].iloc[0]
    assert row["top10IGHM"] == pytest.approx(sum(range(3, 13)) / sum(range(1, 13)))
    assert row["top20IGHM"] == 1.0
    assert row["top10IGHA1"] == pytest.approx(sum(range(3, 13)) / sum(range(1, 13)))
    stats = pd.read_csv(report.csv_paths[1])
    assert set(stats["comparison"]) == {"B - A"}
    assert {"p_value", "fdr", "q_value", "raw_p_significance", "fdr_significance"}.issubset(stats.columns)
    qc = pd.read_csv(report.csv_paths[2])
    assert len(qc) == 4
    assert qc["n_ambiguous"].sum() == 4
    assert qc["n_unmatched"].sum() == 4
    assert len(report.png_paths) == 1
    assert all(path.is_file() and path.stat().st_size > 0 for path in report.png_paths + report.csv_paths)
    with open(report.output_base / "analysis_metadata.json", encoding="utf-8") as handle:
        assert json.load(handle)["sample_count"] == 4


def test_igh_classification_rejects_ambiguous_and_unmatched_calls():
    assert normalize_c_call("IGHG1*01") == ("IGHG1", "matched")
    assert normalize_c_call("IGHA1*01,IGHA1*02") == ("IGHA1", "matched")
    assert normalize_c_call("IGHA1*01/IGHG1*01") == ("Ambiguous", "ambiguous")
    assert normalize_c_call("unknown") == ("Unmatched", "unmatched")


def _write_batched_inputs(root: Path, *, profile_batches=("batch-1", "batch-1", "batch-2", "batch-2")):
    pep_root = root / "pep"
    pep_root.mkdir(parents=True)
    profile = root / "profile-batched.csv"
    pd.DataFrame({
        "sample": ["A1", "B1", "A1", "B1"],
        "group": ["A", "B", "A", "B"],
        "batch": list(profile_batches),
    }).to_csv(profile, index=False)
    for batch, sample, index in zip(profile_batches, ["A1", "B1", "A1", "B1"], range(4)):
        chain_dir = pep_root / batch / "IGH"
        chain_dir.mkdir(parents=True, exist_ok=True)
        _pep_rows(index).to_csv(chain_dir / f"{sample}__IGH.csv", index=False)
    return pep_root, profile


def test_igh_subclass_topclone_matches_duplicate_samples_by_batch_directory(tmp_path):
    pep_root, profile = _write_batched_inputs(tmp_path)
    report = IgSubclassTopCloneService(output_parent=tmp_path / "results").generate_report(
        pep_paths=[str(pep_root)], datapoint_path=str(profile), group_column="group",
        batch_field="batch", group_order=["A", "B"],
    )

    wide = pd.read_csv(report.csv_paths[0])
    assert len(wide) == 4
    assert set(wide["batch"]) == {"batch-1", "batch-2"}
    assert report.metadata["sample_count"] == 4
    assert report.metadata["batch_count"] == 2
    totals = pd.read_csv(report.csv_paths[3])
    assert set(zip(totals["sample"], totals["batch"])) == {
        ("A1", "batch-1"), ("B1", "batch-1"), ("A1", "batch-2"), ("B1", "batch-2")
    }


def test_igh_subclass_topclone_requires_batch_field_for_duplicate_profile_samples(tmp_path):
    pep_root, profile = _write_batched_inputs(tmp_path)
    with pytest.raises(ValueError, match="选择批次字段"):
        IgSubclassTopCloneService(output_parent=tmp_path / "results").generate_report(
            pep_paths=[str(pep_root)], datapoint_path=str(profile), group_column="group",
        )


def test_igh_subclass_topclone_rejects_pep_batch_directory_mismatch(tmp_path):
    pep_root, profile = _write_batched_inputs(
        tmp_path, profile_batches=("batch-1", "batch-1", "batch-2", "batch-3")
    )
    (pep_root / "batch-3").rename(pep_root / "wrong-batch")
    with pytest.raises(ValueError, match="匹配批次"):
        IgSubclassTopCloneService(output_parent=tmp_path / "results").generate_report(
            pep_paths=[str(pep_root)], datapoint_path=str(profile), group_column="group",
            batch_field="batch",
        )


def test_igh_subclass_topclone_matches_reference_pipeline_tables_when_mounted(tmp_path):
    pipeline = Path(os.environ.get("REFERENCE_PIPELINE", ""))
    reference = pipeline / "02.immunoglobulin/2.subclass_topclone/01.subclass_topclone_effect_heatmap.py"
    if not reference.is_file():
        pytest.skip("原始 pipeline 未以 REFERENCE_PIPELINE 挂载")
    pep_root, profile = _write_inputs(tmp_path)
    output_root = tmp_path / "reference-output"
    config = tmp_path / "pipeline-config.json"
    config.write_text(json.dumps({
        "paths": {"datapoint_input": str(profile), "pep_input": str(pep_root.parent)},
        "outputs": {"root": str(output_root)},
    }), encoding="utf-8")
    subprocess.run([
        sys.executable, str(reference), "--config", str(config), "--input-root", str(pep_root),
        "--datapoint", str(profile), "--sample-field", "sample", "--group-field", "group",
        "--group-order", "A,B", "--top-ns", "10,20,50,100", "--output-dir", str(output_root),
    ], check=True, capture_output=True, text=True, timeout=120)
    platform = IgSubclassTopCloneService(output_parent=tmp_path / "platform-output").generate_report(
        pep_paths=[str(pep_root)], datapoint_path=str(profile), group_column="group",
        group_order=["A", "B"], output_name="platform",
    )
    expected_wide = pd.read_csv(output_root / "file" / "subclass_topclone.csv")
    actual_wide = pd.read_csv(platform.csv_paths[0])
    actual_wide = actual_wide[expected_wide.columns]
    pd.testing.assert_frame_equal(actual_wide, expected_wide, check_dtype=False, check_like=True, rtol=1e-12, atol=1e-12)

    expected_stats = pd.read_csv(output_root / "file" / "subclass_topclone_effect_heatmap_stats__A__B.csv")
    actual_stats = pd.read_csv(platform.csv_paths[1])
    key_columns = ["subclass", "top_n"]
    expected_stats = expected_stats.sort_values(key_columns).reset_index(drop=True)
    actual_stats = actual_stats.sort_values(key_columns).reset_index(drop=True)
    for column in expected_stats.columns:
        if column in actual_stats and pd.api.types.is_numeric_dtype(expected_stats[column]):
            np.testing.assert_allclose(actual_stats[column], expected_stats[column], rtol=1e-12, atol=1e-12, equal_nan=True)
        elif column in actual_stats:
            assert actual_stats[column].astype(str).tolist() == expected_stats[column].astype(str).tolist()
