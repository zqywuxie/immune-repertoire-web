"""V/J usage selections use actual upstream rows and preserve the reference statistics."""
from itertools import combinations
from pathlib import Path
import pandas as pd
import pytest
from flask_app.services.volcano_service import VolcanoService
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register


def test_selected_file_is_inspected_without_sibling_tables(tmp_path):
    from flask import Flask
    from flask_app.routes.api_script_hub import script_hub_bp
    source = tmp_path / "selected.csv"
    source.write_text("sample,Category,V1\n001,01,1\n002,02,3\n", encoding="utf-8")
    (tmp_path / "df_other.csv").write_text("sample,Category,V1\nother,wrong,9\n", encoding="utf-8")
    app = Flask(__name__); app.config.update(TESTING=True, REQUIRE_LOGIN=False); app.register_blueprint(script_hub_bp)
    response = app.test_client().post("/api/script-hub/volcano/inspect", json={"data_dir": str(source)})
    assert response.status_code == 200, response.json
    assert response.json["data_dir"] == str(source.resolve())
    assert response.json["files"] == ["selected.csv"]
    assert response.json["samples_by_value"] == {"01": ["001"], "02": ["002"]}


def test_chinese_pairs_have_distinct_output_files(tmp_path):
    source = tmp_path / "usage.csv"
    groups = ["对照", "治疗", "随访"]
    pd.DataFrame([{"sample": f"{group}-{i}", "Category": group, "V1": i + j * 10}
        for j, group in enumerate(groups) for i in range(1, 5)]).to_csv(source, index=False)
    report = VolcanoService(output_parent=tmp_path / "out").generate_report(data_dir=str(source))
    assert len(set(report.csv_paths)) == len(set(report.png_paths)) == 3
    assert all(Path(path).is_file() for path in report.csv_paths + report.png_paths)
    assert {tuple([row["group1"], row["group2"]]) for row in report.metadata["comparisons"]} == set(combinations(groups, 2))


def test_real_pep_selected_volcano_and_downloads(profile_app, mapping_project, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services.analysis_artifacts import resolve_upstream_input
    rows = []
    for batch in ["001", "002"]:
        for index in range(1, 9):
            sample = f"{index:03d}"
            rows.append({"sample": sample, "batch": batch, "group": "01" if index <= 4 else "02"})
            path = tmp_path / "pep" / batch / "TRB" / f"{sample}__TRB.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            pd.DataFrame({"CDR3(pep)": ["CASSAAA", "CASSBBB"], "V": ["TRBV1", "TRBV2"],
                "J": ["TRBJ1", "TRBJ2"], "copy": [index, 10-index]}).to_csv(path, index=False)
            register(mapping_project, "pep", path)
    profile = tmp_path / "profile.csv"
    pd.DataFrame(rows).to_csv(profile, index=False); register(mapping_project, "profile", profile)
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kw: fn(task, **kw))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kw: "isolated-result")
    monkeypatch.setattr("flask_app.services.mongo_service.get_cached_usage", lambda *a, **kw: [])
    monkeypatch.setattr("flask_app.services.mongo_service.save_cached_usage", lambda *a, **kw: "isolated-cache")
    client = profile_app.test_client()
    source = client.post("/api/script-hub/jobs", json={"project_id": mapping_project.id, "asset_set": "Set2", "module": "pep-analysis",
        "group_fields": ["group"], "batch_field": "batch", "selected_chains": ["TRB"], "optional_steps": [], "force_rerun": True})
    assert source.status_code == 200, source.json
    assert shared._get_task_state(source.json["task_id"])["status"] == "completed"
    candidates = client.get("/api/script-hub/pep-cache-candidates", query_string={"project_id": mapping_project.id,
        "asset_set": "Set2", "cache_type": "volcano"}).json["candidates"]
    artifact = next(c for c in candidates if "usage_cate" in c["path"] and Path(c["path"]).name == "1VJusage")
    originals = {path: path.read_bytes() for path in Path(artifact["path"]).glob("*.csv")}
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "volcano", "input_mode": "usage",
        "upstream_artifact_id": artifact["artifact_id"], "selected_categories": ["01", "02"], "comparisons": [["02", "01"]],
        "selected_samples": [f"002::{i:03d}" for i in range(1, 9)], "output_name": "选定批次差异分析", "force_rerun": True,
        "selected_group_values": {"group": ["01", "02"]}, "selected_samples_by_group": {"group": {"01": ["001"], "02": ["005"]}}}
    inspected = client.post("/api/script-hub/volcano/inspect", json=payload)
    assert inspected.status_code == 200, inspected.json
    assert inspected.json["groups"] == ["01", "02"]
    assert inspected.json["sample_count"] == 16
    assert "002::001" in inspected.json["samples_by_value"]["01"]
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    with profile_app.test_request_context(json=payload):
        resolved = dict(payload); resolve_upstream_input("volcano", resolved)
        cache = shared._cache_context_from_script_request(resolved, "volcano")
        assert cache["analysis_signature"] == task["analysis_signature"]
        changed = {**resolved, "selected_samples": [f"001::{i:03d}" for i in range(1, 9)]}
        assert shared._cache_context_from_script_request(changed, "volcano")["analysis_signature"] != task["analysis_signature"]
    result = task["result"]; meta = result["metadata"]
    assert meta["selected_samples"] == payload["selected_samples"]
    assert meta["sample_count"] == 8 and meta["output_name"] == "选定批次差异分析"
    assert meta["comparisons"][0]["group1"] == "02"
    assert Path(result["output_base"]).parent.name == "volcano"
    viewer = client.get(result["viewer_url"]).data.decode("utf-8")
    assert "分析说明与样本范围" in viewer and "前组 4 个样本，后组 4 个样本" in viewer
    assert 'id="sigToggle"' not in viewer and '<em class="is-ns">' not in viewer
    selected = VolcanoService.prepare_usage_inputs(artifact["path"], selected_samples=payload["selected_samples"])
    manual = tmp_path / "manual.csv"; selected["tables"][0][1].to_csv(manual, index=False)
    expected = VolcanoService(output_parent=tmp_path / "expected").generate_report(data_dir=str(manual), comparisons=[["02", "01"]])
    actual = pd.read_csv(Path(result["output_base"]) / result["csv_urls"][0].split("/")[-1])
    pd.testing.assert_frame_equal(actual, pd.read_csv(expected.csv_paths[0]))
    assert not actual.empty
    assert actual["max_nonzero_n"].max() == 4
    for url in result["csv_urls"] + result["png_urls"] + [result["viewer_url"], result["zip_url"]]:
        assert client.get(url).status_code == 200
    assert all(path.read_bytes() == content for path, content in originals.items())
    for changes in ({"selected_samples": []}, {"selected_categories": []}, {"selected_samples": ["不存在"]},
                    {"pvalue_threshold": -1}, {"comparisons": []}, {"asset_set": "Set1"}):
        rejected = client.post("/api/script-hub/jobs", json={**payload, **changes})
        assert rejected.status_code == 400, (changes, rejected.json)


def test_expression_config_preserves_zero_and_normalizes_comparison_labels():
    from flask_app.routes.api_script_hub.enrichment import _volcano_config
    config = _volcano_config({"input_mode": "expression", "logfc_cutoff": 0, "comparisons": [["tpm_A_1", "tpm_B_2"]]})
    assert config["comparisons"] == [["A", "B"]] and config["logfc_cutoff"] == 0
    from flask_app.exceptions import ValidationError
    with pytest.raises(ValidationError):
        _volcano_config({"input_mode": "expression", "comparisons": []})


def test_worker_failure_preserves_last_observed_progress(profile_app, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.routes.api_script_hub.enrichment import _run_volcano_task
    def failing_report(self, **kwargs):
        kwargs["progress_callback"](44, "计算中", "当前比较")
        raise ValueError("合成输入计算失败")
    monkeypatch.setattr(VolcanoService, "generate_report", failing_report)
    task_id = "volcano_failure_test"
    shared._set_task_state(task_id, status="running", progress=5, stage="准备", detail="准备合成输入")
    _run_volcano_task(task_id, results_root=tmp_path, data_dir=str(tmp_path), app_context_app=profile_app)
    task = shared._get_task_state(task_id)
    assert task["status"] == "failed" and task["progress"] == 44
    assert task["detail"] == "合成输入计算失败"


def test_result_counts_only_samples_in_requested_comparisons(tmp_path):
    source = tmp_path / "usage.csv"
    pd.DataFrame({"sample": ["a1", "a2", "b1", "b2", "c1", "c2"], "Category": ["A", "A", "B", "B", "C", "C"],
        "V1": [1, 2, 3, 4, 5, 6]}).to_csv(source, index=False)
    report = VolcanoService(output_parent=tmp_path / "out").generate_report(data_dir=str(source), comparisons=[["B", "A"]])
    assert report.metadata["sample_count"] == 4 and report.metadata["selected_sample_count"] == 6
    assert report.metadata["analyzed_samples"] == ["a1", "a2", "b1", "b2"]
    assert report.metadata["unused_selected_samples"] == ["c1", "c2"]
    counts = report.metadata["comparison_sample_counts"][0]
    assert counts["group1_n"] == counts["group2_n"] == 2 and counts["significant_feature_count"] == 0
    assert len(report.metadata["warnings"]) == 2
