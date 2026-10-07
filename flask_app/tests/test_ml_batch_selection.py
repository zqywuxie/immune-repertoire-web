"""Actual grouped ML training must use the selected batch identities and upstream."""
from pathlib import Path

import pandas as pd
import pytest

from flask_app.services.ml_analysis_service import MLAnalysisService
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register


@pytest.mark.parametrize("mode,identity", [("profile", "batch_sample"), ("vj", "batch_sample"),
                                           ("profile_vj", "batch_sample"), ("profile_vj", "sample")])
def test_real_pep_to_ml_selected_samples_training_and_downloads(profile_app, mapping_project, tmp_path, monkeypatch, mode, identity):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services.analysis_artifacts import resolve_upstream_input
    rows = []
    for batch in ["001", "002"]:
        for index in range(1, 9):
            sample = f"{index:03d}"
            label = "01" if index <= 4 else "02"
            rows.append({"sample": sample, "label": label, "subject": "person-" + sample,
                         "batch": batch, "signal": index + (100 if batch == "001" else 0), "noise": index % 3})
            if mode != "profile":
                path = tmp_path / "pep" / batch / "TRB" / f"{sample}__TRB.csv"
                path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame({"CDR3(pep)": ["CASSAAA", "CASSBBB"], "V": ["TRBV1", "TRBV2"],
                              "J": ["TRBJ1", "TRBJ2"], "copy": [index, 10-index]}).to_csv(path, index=False)
                register(mapping_project, "pep", path)
    profile = tmp_path / "profile.csv"
    pd.DataFrame(rows).to_csv(profile, index=False)
    original = profile.read_bytes()
    register(mapping_project, "profile", profile)
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kwargs: "isolated-result")
    monkeypatch.setattr("flask_app.services.mongo_service.get_cached_usage", lambda *args, **kwargs: [])
    monkeypatch.setattr("flask_app.services.mongo_service.save_cached_usage", lambda *args, **kwargs: "isolated-cache")
    client = profile_app.test_client()
    artifact = None
    if mode != "profile":
        upstream = client.post("/api/script-hub/jobs", json={"project_id": mapping_project.id, "asset_set": "Set2",
            "module": "pep-analysis", "group_fields": ["label"], "batch_field": "batch", "selected_chains": ["TRB"],
            "optional_steps": [], "force_rerun": True})
        assert upstream.status_code == 200, upstream.json
        upstream_task = shared._get_task_state(upstream.json["task_id"])
        assert upstream_task["status"] == "completed", upstream_task
        candidates = client.get("/api/script-hub/pep-cache-candidates", query_string={"project_id": mapping_project.id,
            "asset_set": "Set2", "cache_type": "ml-vj"})
        assert candidates.status_code == 200, candidates.json
        artifact = next(item for item in candidates.json["candidates"] if item["path"].endswith("df_VJ_all.csv"))
        assert artifact["status"] == "available", artifact
    choices = {label: [(f"002::{i:03d}" if identity == "batch_sample" else f"{i:03d}") for i in ids]
               for label, ids in [("01", range(1, 5)), ("02", range(5, 9))]}
    expected = {f"{batch}::{i:03d}" for batch in (["002"] if identity == "batch_sample" else ["001", "002"]) for i in range(1, 9)}
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "ml-analysis", "mode": mode, "output_name": "跨批次训练",
        "label_col": "label", "sample_col": "sample", "batch_field": "batch", "group_col": "subject",
        "custom_threshold": 0,
        "group_sample_identity": identity, "selected_group_values": {"label": ["01", "02"]},
        "selected_samples_by_group": {"label": choices}, "model_keys": ["gaussian_nb"], "cv_splits": 2,
        "use_stability_selection": False, "param_begin": "batch" if mode != "vj" else "",
        "param_over": "noise" if mode != "vj" else "", "force_rerun": True}
    if artifact:
        payload["upstream_artifact_id"] = artifact["artifact_id"]
    inspected = client.post("/api/script-hub/ml-analysis/inspect", json=payload)
    assert inspected.status_code == 200, inspected.json
    assert set(inspected.json["sample_ids"]) == expected
    assert "batch" not in inspected.json["profile_feature_candidates"]
    if artifact:
        assert inspected.json["usage_feature_candidates"]
        assert all(item["value"] for item in inspected.json["usage_feature_candidates"])
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    with profile_app.test_request_context(json=payload):
        resolved = dict(payload)
        resolve_upstream_input("ml-analysis", resolved)
        cached = shared._cache_context_from_script_request(resolved, "ml-analysis")
    assert cached["analysis_signature"] == task["analysis_signature"]
    metadata = task["result"]["metadata"]
    assert metadata["output_name"] == "跨批次训练"
    assert metadata["custom_threshold"] == 0
    assert metadata["samples"] == len(expected)
    assert metadata["batch_field"] == "batch"
    assert metadata["group_col"] == "subject"
    assert metadata["cv_strategy"] == "stratified_group_k_fold"
    assert metadata["selected_samples_by_group"] == {"label": choices}
    out = Path(task["result"]["output_base"])
    provenance = pd.read_csv(out / "sample_identity.csv", dtype=str, keep_default_na=False)
    assert set(provenance["sample"]) == expected
    assert set(provenance["original_sample_id"]) == {f"{i:03d}" for i in range(1, 9)}
    assert set(provenance["label"]) == {"01", "02"}
    predictions = pd.read_csv(next(out.rglob("out_of_fold_predictions.csv")), dtype={"sample": str})
    assert set(predictions["sample"]) == expected
    if mode in {"profile", "profile_vj"}:
        matrix = pd.read_csv(out / ("profile_feature_matrix.csv" if mode == "profile" else "profile_vj_feature_matrix.csv"), dtype={"sample": str, "label": str})
        signal = "signal" if mode == "profile" else "profile__signal"
        assert set(matrix["sample"]) == expected
        assert set(matrix[signal]) == ({*range(1, 9)} if identity == "batch_sample" else {*range(1, 9), *range(101, 109)})
        assert "batch" not in matrix.columns and "profile__batch" not in matrix.columns
    comparison = pd.read_csv(out / next(path.relative_to(out) for path in out.rglob("model_comparison.csv")))
    assert comparison["roc_auc"].notna().all()
    for url in task["result"]["csv_urls"] + task["result"]["png_urls"] + [task["result"]["viewer_url"], task["result"]["zip_url"]]:
        assert client.get(url).status_code == 200, url
    viewer = client.get(task["result"]["viewer_url"]).get_data(as_text=True)
    assert "机器学习分析结果" in viewer and "跨批次训练" in viewer
    assert profile.read_bytes() == original
    rejected = client.post("/api/script-hub/ml-analysis/run", json={**payload,
        "selected_samples_by_group": {"label": {"01": ["不存在::001"]}}, "group_sample_identity": "batch_sample"})
    assert rejected.status_code == 400, rejected.json


@pytest.mark.parametrize("changes,message", [
    ({"batch_field": "missing"}, "批次"), ({"batch_field": "sample"}, "批次"),
    ({"batch_field": None}, "重复样本"),
    ({"selected_samples_by_group": {"label": {"01": []}}}, "筛选后"),
    ({"selected_samples_by_group": {"label": {"01": ["missing::001"]}}}, "组内样本"),
    ({"selected_samples": ["missing"]}, "样本编号不存在"),
])
def test_invalid_ml_selection_is_rejected_before_training(tmp_path, changes, message):
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,label,batch,feature\n001,01,甲,2\n001,02,乙,8\n", encoding="utf-8")
    options = {"profile_path": str(profile), "sample_col": "sample", "label_col": "label", "batch_field": "batch", **changes}
    with pytest.raises(ValueError, match=message):
        MLAnalysisService.prepare_profile(**options)


def test_escaped_usage_identity_takes_precedence_over_filename_aliases(tmp_path):
    usage = tmp_path / "usage.csv"
    usage.write_text("sample,Category,feature\n甲%3A%3A乙::001__visit,01,0.75\n", encoding="utf-8")
    identity = "甲%3A%3A乙::001__visit"
    result = MLAnalysisService(output_parent=tmp_path)._build_usage_feature_matrix({identity}, usage, "sample")
    assert result["sample"].tolist() == [identity]
    assert result["usage__feature"].tolist() == [0.75]
    features = MLAnalysisService.collect_usage_feature_candidates(profile_samples={identity}, usage_path=str(usage), sample_col="sample")
    assert [item["value"] for item in features] == ["usage__feature"]


def test_missing_usage_sample_is_not_filled_as_a_training_row(tmp_path):
    usage = tmp_path / "usage.csv"
    usage.write_text("sample,Category,feature\n甲::001,01,0.75\n", encoding="utf-8")
    with pytest.raises(ValueError, match="乙::001"):
        MLAnalysisService(output_parent=tmp_path)._build_usage_feature_matrix({"甲::001", "乙::001"}, usage, "sample")


def test_excel_ml_identifiers_and_numeric_batch_values_remain_text(tmp_path):
    profile = tmp_path / "profile.xlsx"
    pd.DataFrame({"sample": ["001", "001"], "batch": ["001", "002"], "label": ["01", "02"],
                  "metric": [2, 8]}).to_excel(profile, index=False)
    selected, _, identity = MLAnalysisService.prepare_profile(profile_path=str(profile), sample_col="sample",
        label_col="label", batch_field="batch", group_sample_identity="batch_sample",
        selected_samples_by_group={"label": {"02": ["002::001"]}})
    assert selected["sample"].tolist() == ["002::001"]
    assert identity["original_sample_id"].tolist() == ["001"]
    assert identity["label"].tolist() == ["02"]


def test_ml_filters_labels_groups_and_raw_samples_together(tmp_path):
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,batch,label,site,feature\n001,甲,01,A,2\n001,乙,01,B,8\n002,乙,02,B,9\n", encoding="utf-8")
    selected, _, identity = MLAnalysisService.prepare_profile(profile_path=str(profile), sample_col="sample",
        label_col="label", batch_field="batch", filter_col="site", filter_value="B",
        selected_group_values={"label": ["01"]}, selected_samples=["001"])
    assert selected["sample"].tolist() == ["乙::001"]
    assert identity["original_sample_id"].tolist() == ["001"]


@pytest.mark.parametrize("error", [ValueError("synthetic invalid usage"), PermissionError("synthetic access denied")])
def test_ml_usage_inspection_failure_is_not_reported_as_success(profile_app, mapping_project, tmp_path, monkeypatch, error):
    from flask_app.models.database import AnalysisJob
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,label,feature\n001,01,2\n002,02,8\n", encoding="utf-8")
    register(mapping_project, "profile", profile)
    usage = tmp_path / "usage.csv"
    usage.write_text("sample,Category,V1\n001,01,0.75\n002,02,0.25\n", encoding="utf-8")
    from flask_app.models.database import ProjectAsset, db
    from flask_app.services.analysis_artifacts import capture_input_lineage, scoped_pep_candidates
    monkeypatch.setattr("flask_app.services.mongo_service.get_cached_usage", lambda *args, **kwargs: [])
    lineage = capture_input_lineage(mapping_project.id, [{"path": str(profile)}], "Set2")
    db.session.add(AnalysisJob(id="synthetic-source", job_type="script_hub", module="pep-analysis",
        project_id=mapping_project.id, status="completed", payload=lineage, result={"output_base": str(tmp_path)}))
    db.session.add(ProjectAsset(project_id=mapping_project.id, asset_type="cached_usage", original_name=usage.name,
        storage_path=str(usage), size=usage.stat().st_size, metadata_json={"asset_set": "Set2",
            "source_job_id": "synthetic-source", "source_module": "pep-analysis", "output_base": str(tmp_path),
            "umapin_data_path": str(usage), "profile_path": str(profile)}))
    db.session.commit()
    artifact = next(item for item in scoped_pep_candidates(mapping_project.id, "Set2", "ml-vj")
                    if item["path"] == str(usage))
    assert artifact["status"] == "available", artifact
    def fail(**kwargs):
        raise error
    monkeypatch.setattr(MLAnalysisService, "collect_usage_feature_candidates", fail)
    before = AnalysisJob.query.count()
    response = profile_app.test_client().post("/api/script-hub/ml-analysis/inspect", json={
        "project_id": mapping_project.id, "asset_set": "Set2", "mode": "vj",
        "label_col": "label", "sample_col": "sample", "upstream_artifact_id": artifact["artifact_id"],
    })
    assert response.status_code == 400, response.json
    assert response.json["success"] is False
    assert response.json["message"] == "无法读取 V/J 候选特征，请检查来源文件后重新检查。"
    assert AnalysisJob.query.count() == before
    assert profile.read_text(encoding="utf-8").startswith("sample,label,feature")


@pytest.mark.parametrize("mode", ["profile", "profile_vj"])
@pytest.mark.parametrize("missing", ["param_begin", "param_over"])
def test_missing_ml_ranges_are_rejected_without_creating_jobs(profile_app, mapping_project, tmp_path, monkeypatch, mode, missing):
    from flask_app.models.database import AnalysisJob, ProjectAsset, db
    from flask_app.services.analysis_artifacts import capture_input_lineage, scoped_pep_candidates
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,label,feature\n001,01,2\n002,02,8\n", encoding="utf-8")
    original = profile.read_bytes()
    register(mapping_project, "profile", profile)
    monkeypatch.setattr("flask_app.services.mongo_service.get_cached_usage", lambda *args, **kwargs: [])
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "mode": mode,
        "label_col": "label", "sample_col": "sample", "param_begin": "feature", "param_over": "feature", missing: ""}
    if mode == "profile_vj":
        usage = tmp_path / "usage.csv"
        usage.write_text("sample,Category,V1\n001,01,0.75\n002,02,0.25\n", encoding="utf-8")
        lineage = capture_input_lineage(mapping_project.id, [{"path": str(profile)}], "Set2")
        db.session.add(AnalysisJob(id="range-source", job_type="script_hub", module="pep-analysis",
            project_id=mapping_project.id, status="completed", payload=lineage, result={"output_base": str(tmp_path)}))
        db.session.add(ProjectAsset(project_id=mapping_project.id, asset_type="cached_usage", original_name=usage.name,
            storage_path=str(usage), size=usage.stat().st_size, metadata_json={"asset_set": "Set2",
                "source_job_id": "range-source", "source_module": "pep-analysis", "output_base": str(tmp_path),
                "umapin_data_path": str(usage), "profile_path": str(profile)}))
        db.session.commit()
        source = next(item for item in scoped_pep_candidates(mapping_project.id, "Set2", "ml-vj")
                      if item["path"] == str(usage))
        assert source["status"] == "available", source
        payload["upstream_artifact_id"] = source["artifact_id"]
    before = AnalysisJob.query.count()
    response = profile_app.test_client().post("/api/script-hub/ml-analysis/run", json=payload)
    assert response.status_code == 400, response.json
    assert response.json["success"] is False
    assert response.json["message"] == "请选择样本指标的起始列和结束列。"
    assert response.json["details"]["fields"] == ["param_begin", "param_over"]
    assert AnalysisJob.query.count() == before
    assert profile.read_bytes() == original
