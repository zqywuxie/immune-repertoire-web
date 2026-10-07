import importlib.util
import json
import os
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import matplotlib


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_vj_usage_volcano_matches_reference_for_every_group_pair(tmp_path, monkeypatch):
    from flask_app.services.volcano_service import VolcanoService

    pipeline = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    reference_script = pipeline / "05.Gene" / "1.VJ" / "04.volcano.py"
    if not reference_script.is_file():
        pytest.skip(f"V/J volcano reference script not found: {reference_script}")

    groups = ["对照", "治疗A", "治疗B"]
    rows = []
    feature_values = {
        "TRAV1": ([10, 11, 12, 13], [0, 0, 0, 0], [2, 2, 2, 2]),
        "TRBV2": ([0, 0, 0, 0], [9, 10, 11, 12], [0, 0, 0, 0]),
        "TRAV_Rare": ([8, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]),
        "TRBV_Stable": ([1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]),
    }
    for group_idx, group in enumerate(groups):
        for sample_idx in range(4):
            row = {"sample": f"S{group_idx}_{sample_idx}", "Category": group}
            for feature, values in feature_values.items():
                row[feature] = values[group_idx][sample_idx]
            rows.append(row)

    usage_csv = tmp_path / "df_1VJusage_all.csv"
    pd.DataFrame(rows).to_csv(usage_csv, index=False)
    output_root = tmp_path / "reference-results"
    config_path = tmp_path / "analysis.json"
    config_path.write_text(json.dumps({"outputs": {"root": str(output_root)}}), encoding="utf-8")

    plotting_style = matplotlib.rcParams.copy()
    monkeypatch.setattr(sys, "argv", [str(reference_script), "--config", str(config_path)])
    monkeypatch.setattr(os, "chdir", lambda _path: None)
    spec = importlib.util.spec_from_file_location("reference_vj_volcano_for_test", reference_script)
    reference = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(reference)
    reference.GROUP_COL = "Category"
    reference.GROUP_ORDER = tuple(groups)
    reference.MIN_NONZERO_SAMPLES_IN_ANY_GROUP = 3

    expected_by_pair = {}
    for group1, group2 in combinations(groups, 2):
        pair_dir = tmp_path / "reference" / f"{group1}_vs_{group2}"
        expected_by_pair[(group1, group2)] = reference.volcano_one_file(
            str(usage_csv), group_order=[group1, group2], out_dir=str(pair_dir)
        )
    matplotlib.rcParams.update(plotting_style)

    report = VolcanoService(output_parent=tmp_path / "platform-results").generate_report(
        data_dir=str(usage_csv),
    )

    assert len(report.png_paths) == len(groups) * (len(groups) - 1) // 2
    assert len(report.csv_paths) == len(expected_by_pair)
    assert report.metadata["comparisons"] == [
        {"group1": group1, "group2": group2, "input_file": usage_csv.name}
        for group1, group2 in combinations(groups, 2)
    ]

    for csv_path, pair in zip(report.csv_paths, expected_by_pair):
        actual = pd.read_csv(csv_path)
        expected = expected_by_pair[pair].reset_index(drop=True)
        assert actual["Gene"].tolist() == expected["Gene"].tolist()
        assert actual["significant"].tolist() == expected["significant"].tolist()
        assert actual["passes_support_filter"].tolist() == expected["passes_support_filter"].tolist()
        for column in ("log2FC", "P-value", "q_value", "FC", "nonzero_n_group1", "nonzero_n_group2", "max_nonzero_n"):
            np.testing.assert_allclose(
                pd.to_numeric(actual[column], errors="coerce"),
                pd.to_numeric(expected[column], errors="coerce"),
                rtol=1e-6,
                atol=1e-6,
                equal_nan=True,
            )
    assert not any("TRAV_Rare" in pd.read_csv(path)["Gene"].tolist() for path in report.csv_paths)


def test_vj_usage_volcano_honors_selected_comparison_and_rejects_unknown_group(tmp_path):
    from flask_app.services.volcano_service import VolcanoService

    usage_csv = tmp_path / "usage.csv"
    pd.DataFrame({
        "sample": ["a1", "a2", "b1", "b2", "c1", "c2"],
        "Category": ["A", "A", "B", "B", "C", "C"],
        "V1": [1, 2, 3, 4, 5, 6],
    }).to_csv(usage_csv, index=False)
    service = VolcanoService(output_parent=tmp_path / "results")

    report = service.generate_report(data_dir=str(usage_csv), comparisons=[["C", "A"]])
    assert report.metadata["comparisons"] == [{"group1": "C", "group2": "A", "input_file": "usage.csv"}]

    with pytest.raises(ValueError, match="Unknown usage comparison group"):
        service.generate_report(data_dir=str(usage_csv), comparisons=[["missing", "A"]])


def test_vj_usage_volcano_inspect_returns_groups_and_comparisons(tmp_path):
    from flask import Flask
    from flask_app.routes.api_script_hub import script_hub_bp

    usage_csv = tmp_path / "usage.csv"
    pd.DataFrame({
        "sample": ["a1", "a2", "b1", "b2", "c1", "c2"],
        "Category": ["治疗", "治疗", "基线", "基线", "随访", "随访"],
        "V1": [1, 2, 3, 4, 5, 6],
    }).to_csv(usage_csv, index=False)
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False)
    app.register_blueprint(script_hub_bp)

    response = app.test_client().post("/api/script-hub/volcano/inspect", json={"data_dir": str(usage_csv)})
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["groups"] == ["治疗", "基线", "随访"]
    assert payload["group_counts"] == {"治疗": 2, "基线": 2, "随访": 2}
    assert payload["suggested_comparisons"] == [
        {"group1": "治疗", "group2": "基线"},
        {"group1": "治疗", "group2": "随访"},
        {"group1": "基线", "group2": "随访"},
    ]


def test_vj_usage_volcano_run_preserves_selected_comparisons(tmp_path, monkeypatch):
    from flask import Flask
    from flask_app.routes.api_script_hub import script_hub_bp
    from flask_app.routes.api_script_hub import _script_executor

    usage_csv = tmp_path / "usage.csv"
    pd.DataFrame({
        "sample": ["a1", "a2", "b1", "b2"],
        "Category": ["A", "A", "B", "B"],
        "V1": [1, 2, 3, 4],
    }).to_csv(usage_csv, index=False)
    submitted = {}

    def fake_submit(fn, *args, **kwargs):
        submitted["fn"] = fn
        submitted["kwargs"] = kwargs

    monkeypatch.setattr(_script_executor, "submit", fake_submit)
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False)
    app.register_blueprint(script_hub_bp)
    client = app.test_client()

    response = client.post("/api/script-hub/volcano/run", json={
        "data_dir": str(usage_csv),
        "comparisons": [["B", "A"]],
        "force_rerun": True,
    })
    assert response.status_code == 200
    assert submitted["kwargs"]["comparisons"] == [["B", "A"]]

    empty_response = client.post("/api/script-hub/volcano/run", json={
        "data_dir": str(usage_csv),
        "comparisons": [],
    })
    assert empty_response.status_code == 400
