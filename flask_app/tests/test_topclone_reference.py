import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_topclone_trace_matches_reference_for_sample_join_and_proportions(tmp_path, monkeypatch):
    from flask_app.services.boxplot_service import BoxPlotService
    from flask_app.services.topclone_service import TopCloneService

    pipeline = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    reference_script = pipeline / "03.UCDR3" / "2.topclone" / "0.CDR3_trace.py"
    if not reference_script.is_file():
        pytest.skip(f"TopClone reference script not found: {reference_script}")

    pep_root = tmp_path / "pep"
    for chain in ("TRA", "TRB"):
        (pep_root / chain).mkdir(parents=True)

    def write_sample(sample: str, chain: str, counts: list[int]) -> None:
        frame = pd.DataFrame({
            "CDR3(pep)": [f"{chain}CLONE{index}" for index in range(1, len(counts) + 1)],
            "copy": counts,
        })
        if sample == "001" and chain == "TRA":
            frame = pd.concat([frame, pd.DataFrame({
                "CDR3(pep)": ["TRACLONE1", "excluded*", "excluded_"],
                "copy": [5, 100, 100],
            })], ignore_index=True)
        frame.to_csv(pep_root / chain / f"{sample}__{chain}.csv", index=False)

    for sample, counts in (("001", list(range(12, 0, -1))), ("2", list(range(24, 0, -2)))):
        for chain in ("TRA", "TRB"):
            write_sample(sample, chain, counts)
    for chain in ("TRA", "TRB"):
        write_sample("03", chain, [0])
    for chain in ("TRA", "TRB"):
        write_sample("04", chain, list(range(18, 6, -1)))
    write_sample("5", "TRB", list(range(12, 0, -1)))

    profile = tmp_path / "Profile.csv"
    profile.write_text("sample,group\n001,A\n2,A\n03,B\n04,B\n5,B\n", encoding="utf-8")
    config = tmp_path / "analysis.json"
    config.write_text(json.dumps({
        "outputs": {"root": str(tmp_path / "pipeline-results")},
        "paths": {"datapoint_input": str(profile)},
        "datapoint": {"sample_column": "sample", "group_column": "group", "group_order": ["A", "B"]},
    }), encoding="utf-8")
    expected_path = tmp_path / "reference-topclone.csv"
    completed = subprocess.run(
        [sys.executable, str(reference_script), "--config", str(config), "--input", str(pep_root), "--output", str(expected_path)],
        check=True, capture_output=True, text=True,
    )
    assert "[done]" in completed.stdout

    effect_script = pipeline / "03.UCDR3" / "2.topclone" / "01.topclone_effect_heatmap.py"
    monkeypatch.setattr(sys, "argv", [str(effect_script), "--config", str(config)])
    effect_spec = importlib.util.spec_from_file_location("topclone_effect_reference_for_test", effect_script)
    reference_effect = importlib.util.module_from_spec(effect_spec)
    assert effect_spec and effect_spec.loader
    effect_spec.loader.exec_module(reference_effect)
    reference_effect.INPUT_FILE = expected_path
    reference_effect.OUTPUT_DIR = tmp_path / "reference-effects"
    reference_effect.GROUP_COLUMN = "group"
    reference_effect.GROUP_ORDER = ("A", "B")
    reference_long, _, _ = reference_effect.load_long(expected_path)
    reference_groups = reference_effect.resolve_order(
        reference_long["group"].drop_duplicates().astype(str).tolist(),
        reference_effect.GROUP_ORDER,
        reference_effect.APPEND_UNLISTED_GROUPS,
    )
    expected_effect_statistics = reference_effect.compute_stats(reference_long, reference_groups)

    monkeypatch.setattr(
        BoxPlotService,
        "generate_report",
        lambda self, **kwargs: SimpleNamespace(png_paths=[]),
    )
    box_script = pipeline / "03.UCDR3" / "2.topclone" / "box.py"
    spec = importlib.util.spec_from_file_location("topclone_box_reference_for_test", box_script)
    reference_box = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(reference_box)
    monkeypatch.setattr(reference_box, "plot_metric", lambda *args, **kwargs: None)
    monkeypatch.setattr(reference_box, "plot_summary", lambda *args, **kwargs: None)
    expected_statistics = reference_box.run(
        expected_path, tmp_path / "reference-boxplots", "group", ["A", "B"], [],
    )

    report = TopCloneService(output_parent=tmp_path / "platform-results").generate_report(
        pep_data_path=str(pep_root), datapoint_path=str(profile),
        mode="trace", group_field="group", group_order="A,B", selected_chains=["TRA", "TRB"],
    )

    expected = pd.read_csv(expected_path, dtype={"sample": str}).set_index("sample")
    actual = pd.read_csv(report.topclone_csv_path, dtype={"sample": str}).set_index("sample")
    assert actual.index.tolist() == ["001", "2", "03", "04"]
    assert actual.index.tolist() == expected.index.tolist()
    metric_columns = [column for column in expected.columns if column.startswith("top")]
    for column in metric_columns:
        np.testing.assert_allclose(actual[column], expected[column], rtol=0, atol=1e-12, equal_nan=True)
    assert report.metadata["sample_count"] == 4
    assert report.metadata["profile_sample_count"] == 5
    assert report.metadata["excluded_unmatched_sample_count"] == 1
    assert np.isnan(actual.loc["03", "top10TRA"])
    actual_statistics = pd.read_csv(report.stats_csv_path)
    pd.testing.assert_frame_equal(
        actual_statistics,
        expected_statistics,
        check_dtype=False,
        check_exact=False,
        rtol=0,
        atol=1e-12,
    )
    assert len(report.effect_heatmap_paths or []) == 1
    heatmap_file = Path(report.effect_heatmap_paths[0])
    assert heatmap_file.is_file() and heatmap_file.stat().st_size > 1000
    assert heatmap_file.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert len(report.effect_statistics_paths or []) == 1
    actual_effect_statistics = pd.read_csv(report.effect_statistics_paths[0])
    pd.testing.assert_frame_equal(
        actual_effect_statistics,
        expected_effect_statistics,
        check_dtype=False,
        check_exact=False,
        rtol=0,
        atol=1e-12,
    )
