"""Actual grouped unified UMAP must use the selected batch identities and upstream."""
from pathlib import Path

import pandas as pd
import pytest

from flask_app.services.unified_umap_service import UnifiedUmapService
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register


@pytest.mark.parametrize("mode,identity", [("profile", "batch_sample"), ("vj+profile", "batch_sample"), ("vj", "sample")])
def test_real_pep_to_unified_umap_batch_selection_and_downloads(profile_app, mapping_project, tmp_path, monkeypatch, mode, identity):
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
            "asset_set": "Set2", "cache_type": "umapin"})
        assert candidates.status_code == 200, candidates.json
        artifact = next(item for item in candidates.json["candidates"] if item["path"].endswith("df_VJ_all.csv"))
        assert artifact["status"] == "available", artifact
    choices = {label: [(f"002::{i:03d}" if identity == "batch_sample" else f"{i:03d}") for i in ids]
               for label, ids in [("01", range(1, 5)), ("02", range(5, 9))]}
    expected = {f"{batch}::{i:03d}" for batch in (["002"] if identity == "batch_sample" else ["001", "002"]) for i in range(1, 9)}
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "umap", "analysis_mode": "unified",
        "configurations": [mode], "group_field": "label", "sample_column": "sample", "batch_field": "batch",
        "group_sample_identity": identity, "selected_group_values": {"label": ["01", "02"]},
        "selected_samples_by_group": {"label": choices}, "param_begin": "signal", "param_over": "noise",
        "raw_p_threshold": 0.05, "n_epochs": 20, "n_neighbors": 3, "min_dist": 0, "random_state": 0,
        "permanova_random_state": 0, "permanova_permutations": 9, "output_name": "批次联合投影", "force_rerun": True}
    if artifact:
        payload["upstream_artifact_id"] = artifact["artifact_id"]
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    with profile_app.test_request_context(json=payload):
        resolved = dict(payload)
        resolve_upstream_input("umap", resolved)
        cached = shared._cache_context_from_script_request(resolved, "umap")
    assert cached["analysis_signature"] == task["analysis_signature"]
    metadata = task["result"]["metadata"]
    assert metadata["selected_sample_count"] == len(expected)
    assert metadata["output_name"] == "批次联合投影"
    assert metadata["batch_field"] == "batch"
    assert metadata["group_sample_identity"] == identity
    assert metadata["selected_samples_by_group"] == {"label": choices}
    assert metadata["min_dist"] == 0 and metadata["random_state"] == 0
    out = Path(task["result"]["output_base"])
    assert out.parent.name == "umap"
    provenance = pd.read_csv(out / "sample_identity.csv", dtype=str, keep_default_na=False)
    assert set(provenance["sample"]) == expected
    assert set(provenance["source_sample"]) == {f"{i:03d}" for i in range(1, 9)}
    assert set(provenance["label"]) == {"01", "02"}
    coordinates = pd.read_csv(next(out.rglob("umap_coordinates.csv")), dtype={"sample": str, "label": str, "source_sample": str})
    assert set(coordinates["sample"]) == expected
    assert set(coordinates["label"]) == {"01", "02"}
    summary = pd.read_csv(out / "permanova_summary.csv")
    assert summary["n_samples"].tolist() == [len(expected)]
    assert summary["status"].tolist() == ["ok"]
    assert summary["pseudo_F"].notna().all()
    if artifact:
        from flask_app.services.background_job_service import get_background_job_service
        stored = get_background_job_service().get_job(response.json["task_id"])
        assert stored["payload"]["upstream_input"]["source_job_id"] == artifact["job_id"]
        from flask_app.services.analysis_artifacts import revalidate_job_upstream
        revalidate_job_upstream(stored)
        rejected = client.post("/api/script-hub/jobs", json={**payload, "asset_set": "Set1"})
        assert rejected.status_code == 400, rejected.json
    for url in task["result"]["csv_urls"] + task["result"]["png_urls"] + [task["result"]["viewer_url"], task["result"]["zip_url"]]:
        assert client.get(url).status_code == 200, url
    assert "统一多模态 UMAP 结果" in client.get(task["result"]["viewer_url"]).get_data(as_text=True)
    assert profile.read_bytes() == original
    rejected = client.post("/api/script-hub/umap/run", json={**payload,
        "selected_samples_by_group": {"label": {"01": ["不存在::001"]}}, "group_sample_identity": "batch_sample"})
    assert rejected.status_code == 400, rejected.json
    rejected = client.post("/api/script-hub/jobs", json={**payload,
        "selected_group_values": {"label": []}, "selected_samples_by_group": {"label": {}}})
    assert rejected.status_code == 400, rejected.json
    if artifact:
        from flask_app.exceptions import ValidationError
        profile.write_text(profile.read_text() + "009,03,person-009,003,9,0\n")
        with pytest.raises(ValidationError, match="来源输入已修改"):
            revalidate_job_upstream(stored)


@pytest.mark.parametrize("identity,selection,expected", [
    ("batch_sample", ["甲%3A%3A%25::001"], {"甲%3A%3A%25::001", "乙::002"}),
    ("sample", ["001"], {"甲%3A%3A%25::001", "乙::001", "乙::002"}),
])
def test_umap_escaped_batch_choices_preserve_labels(tmp_path, identity, selection, expected):
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,batch,group,metric\n001,甲::%,01,1\n001,乙,01,2\n002,乙,02,9\n", encoding="utf-8")
    _, metadata = UnifiedUmapService.prepare_profile(profile_path=str(profile), sample_column="sample", label_column="group",
        batch_field="batch", group_sample_identity=identity, selected_samples_by_group={"group": {"01": selection,
            "02": ["乙::002"] if identity == "batch_sample" else ["002"]}})
    assert set(metadata["sample"]) == expected
    assert set(metadata["label"]) == {"01", "02"}


def test_empty_umap_group_sample_choice_does_not_mean_all_samples(tmp_path):
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,group,metric\n001,A,1\n002,B,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="少于两个类别"):
        UnifiedUmapService.prepare_profile(profile_path=str(profile), sample_column="sample", label_column="group",
            selected_samples_by_group={"group": {"A": [], "B": []}})
