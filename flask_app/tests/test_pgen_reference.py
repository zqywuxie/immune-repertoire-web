import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_pgen_distribution_aggregation_matches_reference(tmp_path, monkeypatch):
    from flask_app.services.pgen_analysis_service import PgenAnalysisService

    pipeline = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    script_path = pipeline / "03.UCDR3" / "4.Pgen" / "02.plot_pgen_cdr3.py"
    if not script_path.is_file():
        pytest.skip(f"Pgen reference script not found: {script_path}")

    profile_path = tmp_path / "Profile.csv"
    profile_path.write_text("sample,group\ns1,A\ns2,A\ns3,A\ns4,B\ns5,B\ns6,B\n", encoding="utf-8")
    config_path = tmp_path / "analysis.json"
    config_path.write_text(json.dumps({
        "paths": {
            "output_root": str(tmp_path / "results"),
            "datapoint_input": str(profile_path),
        },
        "datapoint": {"group_column": "group", "group_order": ["A", "B"]},
    }), encoding="utf-8")

    monkeypatch.syspath_prepend(str(pipeline))
    monkeypatch.setattr(sys, "argv", [str(script_path), "--config", str(config_path)])
    spec = importlib.util.spec_from_file_location("pgen_reference_for_test", script_path)
    reference = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(reference)

    rows = [
        ("s1", "PUB1", 1e-2), ("s2", "PUB1", 1e-4),
        ("s1", "PUB2", 1e-6), ("s2", "PUB2", 1e-8),
        ("s1", "RARE", 1e-3), ("s3", "ONLY_ONE_SAMPLE", 1e-5),
        ("s4", "B1", 1e-3), ("s5", "B2", 1e-5),
        ("s6", "B3", 1e-7),
    ]
    sample_category = {"s1": "A", "s2": "A", "s3": "A", "s4": "B", "s5": "B", "s6": "B"}
    available_samples = set(sample_category)

    for public_only, classification in ((True, "public"), (False, "all")):
        expected_values, expected_stats, _ = reference.aggregate_group_pgen(
            rows, sample_category, available_samples, public_only=public_only,
        )
        actual_values, actual_stats, _ = PgenAnalysisService._classify_public_pgen_by_category(
            rows, sample_category, available_samples=available_samples, public_only=public_only,
        )
        assert actual_stats.keys() == expected_stats.keys()
        for category in expected_values:
            np.testing.assert_allclose(actual_values[category], expected_values[category], rtol=0, atol=1e-12)
            assert actual_stats[category]["samples"] == expected_stats[category]["samples"]
            assert actual_stats[category]["threshold"] == expected_stats[category]["threshold"]
            assert actual_stats[category]["total_cdr3"] == expected_stats[category]["total_cdr3"]
            assert actual_stats[category]["public_cdr3"] == expected_stats[category]["public_cdr3"]
            assert actual_stats[category]["selected_cdr3"] == expected_stats[category]["selected_cdr3"]
            assert actual_stats[category]["public_nonzero"] == expected_stats[category]["non_zero"]

        expected_ks = reference.run_ks_tests("TRA", expected_values)
        actual_ks = PgenAnalysisService._compare_distribution_categories("TRA", actual_values, classification)
        assert len(actual_ks) == len(expected_ks)
        for expected, actual in zip(expected_ks.to_dict("records"), actual_ks):
            assert actual["category_1"] == expected["category_1"]
            assert actual["category_2"] == expected["category_2"]
            np.testing.assert_allclose(actual["ks_statistic"], expected["ks_statistic"], rtol=0, atol=1e-12, equal_nan=True)
            np.testing.assert_allclose(actual["p_value"], expected["p_value"], rtol=0, atol=1e-12, equal_nan=True)
            np.testing.assert_allclose(actual["p_value_bh"], expected["p_value_bh"], rtol=0, atol=1e-12, equal_nan=True)
            np.testing.assert_allclose(actual["median_difference"], expected["median_difference"], rtol=0, atol=1e-12, equal_nan=True)
            np.testing.assert_allclose(actual["cliffs_delta"], expected["cliffs_delta"], rtol=0, atol=1e-12, equal_nan=True)
            np.testing.assert_allclose(actual["pgen_cliffs_delta"], expected["pgen_cliffs_delta"], rtol=0, atol=1e-12, equal_nan=True)
