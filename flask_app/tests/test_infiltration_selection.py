"""Actual matched infiltration identities reach native R and result retrieval."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy.stats import mannwhitneyu
from flask_app.exceptions import ValidationError
from flask_app.services import infiltration_service as service
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register


def batch_inputs(folder):
    ids = [f"{batch}::{i:03d}" for batch in ["甲", "乙"] for i in range(1, 5)]
    profile = folder / "profile.csv"; deconv = folder / "deconv.csv"
    pd.DataFrame({"sample": ids, "group": ["01"]*4+["02"]*4, "IGHA1": [1, 4, 2, 3, 8, 10, 9, 7]}).to_csv(profile, index=False)
    pd.DataFrame({"Mixture": ids, "T cells": [0.1, 0.3, 0.2, 0.4, 0.6, 0.9, 0.8, 0.7],
                  "B cells": [0.8, 0.6, 0.5, 0.7, 0.2, 0.4, 0.1, 0.3]}).to_csv(deconv, index=False)
    return profile, deconv, ids


def test_native_infiltration_subset_cache_and_downloads(profile_app, mapping_project, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    profile, deconv, ids = batch_inputs(tmp_path)
    register(mapping_project, "profile", profile); register(mapping_project, "deconvolution", deconv)
    original = [path.read_bytes() for path in [profile, deconv]]
    selected = ids[:3] + ids[4:7]
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kw: fn(task, **kw))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kw: "isolated-infiltration")
    client = profile_app.test_client()
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "immune-infiltration", "group_field": "group",
               "score_type": "relative", "cell_columns": ["T cells", "B cells"], "selected_infiltration_samples": selected,
               "output_name": "选定浸润样本", "force_rerun": True, "selected_samples": ["ignored-profile"]}
    discovered = client.post("/api/script-hub/immune-infiltration/inspect", json={**payload, "sample_scope_only": True})
    assert discovered.status_code == 200, discovered.json
    assert discovered.json["samples_by_value"] == {"01": ids[:4], "02": ids[4:]}
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    job = shared._get_task_state(response.json["task_id"])
    assert job["status"] == "completed", job
    result = job["result"]; output = Path(result["output_base"])
    assert output.parent.name == "immune-infiltration"
    assert result["metadata"]["selected_infiltration_samples"] == selected
    assert result["metadata"]["sample_count"] == 6 and result["metadata"]["group_counts"] == {"01": 3, "02": 3}
    assert result["metadata"]["unused_deconvolution_count"] == 2
    assert result["metadata"]["output_name"] == "选定浸润样本"
    assert pd.read_csv(output / "input.csv", dtype=str)["sample"].tolist() == selected
    matrix = pd.read_csv(next(output.rglob("panel_A_shift_normalized_matrix.csv")), dtype={"sample": str, "group": str}).set_index("sample")
    assert set(matrix.index) == set(selected) and set(matrix["group"]) == {"01", "02"}
    stats = pd.read_csv(next(output.rglob("panel_B_pairwise_stats.csv")))
    frame = pd.read_csv(deconv, dtype={"Mixture": str}).set_index("Mixture")
    for cell in ["T cells", "B cells"]:
        expected = mannwhitneyu(frame.loc[selected[:3], cell], frame.loc[selected[3:], cell], alternative="two-sided", method="asymptotic").pvalue
        np.testing.assert_allclose(stats.loc[stats["CellType"].eq(cell), "p_value"], expected)
    with profile_app.test_request_context(json=payload):
        context = shared._cache_context_from_script_request(payload, "immune-infiltration")
        assert context["analysis_signature"] == job["analysis_signature"]
        changed = {**payload, "selected_infiltration_samples": ids}
        assert shared._cache_context_from_script_request(changed, "immune-infiltration")["analysis_signature"] != job["analysis_signature"]
    viewer = client.get(result["viewer_url"])
    assert viewer.status_code == 200 and "本次分析 6 个实际匹配样本" in viewer.get_data(as_text=True)
    for url in [result["zip_url"], *result["csv_urls"], *result["png_urls"]]:
        assert client.get(url).status_code == 200
    for changes in [{"selected_infiltration_samples": []}, {"selected_infiltration_samples": ["001"]}, {"selected_infiltration_groups": []},
                    {"selected_infiltration_samples": ids[:2]+ids[4:5]}, {"selected_infiltration_samples": ids[:2], "sample_scope_only": True}]:
        rejected = client.post("/api/script-hub/jobs", json={**payload, **changes})
        assert rejected.status_code == 400, (changes, rejected.json)
    assert original == [path.read_bytes() for path in [profile, deconv]]


@pytest.mark.parametrize("kind", ["consistency", "concordance"])
def test_related_inspectors_use_actual_scope(profile_app, tmp_path, kind):
    profile, deconv, ids = batch_inputs(tmp_path); selected = ids[:3]+ids[4:7]
    inspector = service.inspect_consistency if kind == "consistency" else service.inspect_concordance
    summary, prepared, metadata = inspector(str(profile), str(deconv), "group", ["T cells", "B cells"], selected_infiltration_samples=selected)
    assert prepared["sample"].tolist() == selected and metadata["sample"].tolist() == selected
    assert summary["group_counts"] == {"01": 3, "02": 3}
    if kind == "consistency":
        with pytest.raises(ValidationError, match="三个"):
            inspector(str(profile), str(deconv), "group", ["T cells", "B cells"], selected_infiltration_samples=ids[:2]+ids[4:6])


def test_sample_pathway_scope_is_three_way_and_minimum_count_remains(profile_app, tmp_path):
    from flask_app.tests.test_infiltration_sample_pathway import make_inputs
    from flask_app.services.infiltration_sample_pathway import inspect_sample_pathway
    profile, deconv, expression, ids = make_inputs(tmp_path)
    selected = ids[:5]+ids[6:11]
    summary, prepared, metadata = inspect_sample_pathway(str(profile), str(deconv), str(expression), "group", ["T cells"], ["病例", "对照"], selected_infiltration_samples=selected)
    assert summary["sample_count"] == 10 and prepared["sample"].tolist() == selected
    with pytest.raises(ValidationError, match="10 个"):
        inspect_sample_pathway(str(profile), str(deconv), str(expression), "group", ["T cells"], ["病例", "对照"], selected_infiltration_samples=selected[:-1])
