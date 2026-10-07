import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.services.boxplot_service import BoxPlotService
from flask_app.tests.test_profile_workflow import profile_app


def test_profile_boxplot_matches_original_pipeline_mann_whitney(profile_app, tmp_path):
    reference_root = os.environ.get("REFERENCE_PIPELINE")
    if not reference_root:
        pytest.skip("需要只读挂载原始 pipeline 并设置 REFERENCE_PIPELINE")

    datapoint = tmp_path / "datapoint.csv"
    metric = [0.2, 0.4, 0.3, 0.5, 0.1] + [0.18, 0.38, 0.32, 0.45, 0.15] + [2.0, 2.2, 1.8, 2.4, 2.1]
    pd.DataFrame({
        "sample": [f"S{i}" for i in range(1, 16)],
        "group": ["甲"] * 5 + ["乙"] * 5 + ["丙"] * 5,
        "metric1": metric,
        "metric2": [value * 3 + 1 for value in metric],
    }).to_csv(datapoint, index=False)

    platform = BoxPlotService(output_parent=tmp_path / "platform").generate_report(
        datapoint_path=str(datapoint),
        grouptype_fields=["group"],
        param_begin="metric1",
        param_over="metric2",
        group_order="甲,乙,丙",
    )
    platform_all_stats = pd.concat([pd.read_csv(path) for path in platform.pvalue_paths], ignore_index=True)
    assert (platform_all_stats["pvalue"] > 0.05).any()
    platform_stats = platform_all_stats[platform_all_stats["pvalue"] <= 0.05].copy()
    platform_stats = platform_stats.rename(columns={"group_a": "group1", "group_b": "group2"})
    platform_stats["pair"] = platform_stats.apply(
        lambda row: tuple(sorted((str(row.group1), str(row.group2)))), axis=1
    )
    platform_stats = platform_stats.set_index(["pair", "param"]).sort_index()

    reference_output = tmp_path / "original"
    config_path = tmp_path / "original-config.json"
    config_path.write_text(json.dumps({
        "default_profile": "default",
        "datapoint_profiles": {"default": {
            "input_path_key": "datapoint_input",
            "sample_column": "sample",
            "group_column": "group",
            "group_order": ["甲", "乙", "丙"],
        }},
        "paths": {"datapoint_input": str(datapoint)},
        "outputs": {"root": str(tmp_path / "original-project")},
        "profile": {"parameter_selection": {
            "mode": "explicit",
            "include": ["metric1", "metric2"],
            "exclude": [],
        }},
    }, ensure_ascii=False), encoding="utf-8")
    script = Path(reference_root) / "01.Profile" / "1.Box" / "01.Box.py"
    subprocess.run([
        "python", str(script),
        "--config", str(config_path),
        "--input", str(datapoint),
        "--output-dir", str(reference_output),
        "--group-column", "group",
        "--sample-column", "sample",
        "--param-mode", "explicit",
        "--param-include", "metric1,metric2",
    ], check=True, capture_output=True, text=True)
    reference_table = next(reference_output.rglob("significant_pvalue_all.txt"))
    reference_stats = pd.read_csv(reference_table, sep="\t")
    reference_stats["pair"] = reference_stats.apply(
        lambda row: tuple(sorted((str(row.group1), str(row.group2)))), axis=1
    )
    reference_stats = reference_stats.set_index(["pair", "param"]).sort_index()

    assert platform_stats.index.equals(reference_stats.index)
    assert len(platform_stats) == 4
    np.testing.assert_allclose(platform_stats["pvalue"], reference_stats["pvalue"], rtol=1e-12, atol=1e-12)
