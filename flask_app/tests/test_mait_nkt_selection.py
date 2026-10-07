"""Real PEP output must feed batch-aware MAIT/NKT selection and downloads."""
from pathlib import Path
import zipfile

import pandas as pd
import pytest

from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register
from flask_app.services.mait_nkt_service import MaitNktService
from flask_app.exceptions import ValidationError


@pytest.mark.parametrize("identity,choices,expected", [
    ("batch_sample", ["乙::001"], ["乙::001"]),
    ("sample", ["001"], ["甲::001", "乙::001"]),
])
def test_real_pep_to_mait_batch_selection_and_downloads(profile_app, mapping_project, tmp_path, monkeypatch, identity, choices, expected):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services.analysis_artifacts import resolve_upstream_input, revalidate_job_upstream
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,batch,group\n001,甲,01\n001,乙,01\n002,乙,02\n", encoding="utf-8")
    register(mapping_project, "profile", profile)
    for batch, sample, first in [("甲", "001", 2), ("乙", "001", 8), ("乙", "002", 5)]:
        path = tmp_path / "pep" / batch / "TRA" / f"{sample}__TRA.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"CDR3(pep)": ["CASSAAA", "CASSBBB"], "V": "TRAV1", "J": "TRAJ1", "copy": [first, 10-first]}).to_csv(path, index=False)
        register(mapping_project, "pep", path)
    original = profile.read_bytes()
    reference = tmp_path / "Alpha_Restrict.csv"
    reference.write_text("CDR3,Type\nCASSAAA,MAIT\nCASSBBB,iNKT\n", encoding="utf-8")
    original_init = MaitNktService.__init__
    def initialize(self, **kwargs):
        original_init(self, **kwargs)
        self._reference_path = reference
    monkeypatch.setattr(MaitNktService, "__init__", initialize)
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kwargs: "isolated-result")
    monkeypatch.setattr("flask_app.services.mongo_service.get_cached_usage", lambda *args, **kwargs: [])
    monkeypatch.setattr("flask_app.services.mongo_service.save_cached_usage", lambda *args, **kwargs: "isolated-cache")
    client = profile_app.test_client()
    upstream = client.post("/api/script-hub/jobs", json={"project_id": mapping_project.id, "asset_set": "Set2",
        "module": "pep-analysis", "group_fields": ["group"], "batch_field": "batch", "selected_chains": ["TRA"],
        "optional_steps": [], "force_rerun": True})
    assert upstream.status_code == 200, upstream.json
    upstream_task = shared._get_task_state(upstream.json["task_id"])
    assert upstream_task["status"] == "completed", upstream_task
    candidates = client.get("/api/script-hub/pep-cache-candidates", query_string={"project_id": mapping_project.id,
        "asset_set": "Set2", "cache_type": "mait-nkt"})
    assert candidates.status_code == 200, candidates.json
    candidate = next(item for item in candidates.json["candidates"] if Path(item["path"]).parent.name == "Pep_shared")
    assert candidate["status"] == "available", candidate
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "mait-nkt", "tra_source": "pep_analysis",
        "upstream_artifact_id": candidate["artifact_id"], "group_field": "group", "batch_field": "batch",
        "group_sample_identity": identity, "selected_group_values": {"group": ["01"]},
        "selected_samples_by_group": {"group": {"01": choices}}, "force_rerun": True}
    inspected = client.post("/api/script-hub/mait-nkt/inspect", json=payload)
    assert inspected.status_code == 200, inspected.json
    assert set(inspected.json["sample_columns"]) == set(expected)
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    assert task["config_json"]["group_sample_identity"] == identity
    assert task["config_json"]["tra_sample_count"] == len(expected)
    with profile_app.test_request_context(json=payload):
        resolved = dict(payload)
        resolve_upstream_input("mait-nkt", resolved)
        cache = shared._cache_context_from_script_request(resolved, "mait-nkt")
    assert cache["analysis_signature"] == task["analysis_signature"]
    data = pd.read_csv(Path(task["result"]["output_base"]) / "MAIT_iNKT_profile.csv", dtype={"sample": str, "sample_id": str, "batch": str, "category": str})
    assert set(data["sample"]) == set(expected)
    assert data["sample_id"].tolist() == ["001"] * len(expected)
    assert data["category"].tolist() == ["01"] * len(expected)
    assert data.set_index("sample")["MAIT_fraction"].to_dict() == {sample: {"甲::001": 0.2, "乙::001": 0.8}[sample] for sample in expected}
    assert data.set_index("sample")["iNKT_fraction"].to_dict() == {sample: {"甲::001": 0.8, "乙::001": 0.2}[sample] for sample in expected}
    assert task["result"]["metadata"]["sample_count"] == len(expected)
    assert task["result"]["metadata"]["batch_field"] == "batch"
    assert all(event["stage"] not in {"Loading", "Queued"} for event in task["history"])
    for url in task["result"]["csv_urls"] + task["result"]["png_urls"] + [task["result"]["viewer_url"], task["result"]["zip_url"], task["result"]["metadata_url"]]:
        assert client.get(url).status_code == 200, url
    assert profile.read_bytes() == original
    rejected = client.post("/api/script-hub/mait-nkt/run", json={**payload, "selected_samples_by_group": {"group": {"01": ["乙::002"]}}, "group_sample_identity": "batch_sample"})
    assert rejected.status_code == 400, rejected.json
    cross = client.post("/api/script-hub/mait-nkt/inspect", json={**payload, "asset_set": "Set1"})
    assert cross.status_code == 400, cross.json
    # Execution-time provenance must reject a modified source, not keep using its old result.
    ref = task.get("upstream_input") or (task.get("payload") or {}).get("upstream_input")
    assert ref
    profile.write_text(profile.read_text(encoding="utf-8") + "003,乙,03\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="来源输入已修改"):
        revalidate_job_upstream({"payload": {"upstream_input": ref}})


def test_numeric_categories_escaped_batches_and_zero_totals(tmp_path):
    reference = tmp_path / "Alpha_Restrict.csv"
    reference.write_text("CDR3,Type\nCASSAAA,MAIT\n", encoding="utf-8")
    service = MaitNktService(output_parent=tmp_path / "results")
    service._reference_path = reference
    # Numeric category labels must never become an extra clone row.
    report = service.generate_report(tra_df=pd.DataFrame([["group", "01"], ["CASSAAA", 0]], columns=["CDR3", "批次%3A%3A甲%25::001"]),
        profile_df=pd.DataFrame({"sample": ["001"], "batch": ["批次::甲%"], "group": ["01"]}), group_field="group", batch_field="batch")
    result = pd.read_csv(report.csv_paths[0], dtype={"sample": str, "sample_id": str, "category": str})
    assert result["category"].tolist() == ["01"]
    assert result["batch"].tolist() == ["批次::甲%"]
    assert result["MAIT_sum"].tolist() == [0]
    assert result["MAIT_fraction"].isna().all()
    assert report.png_paths == []
    assert report.metadata["notes"]
    with zipfile.ZipFile(report.zip_path) as archive:
        assert "MAIT_iNKT_profile.csv" in archive.namelist()
        assert "metadata.json" in archive.namelist()
    viewer = report.viewer_path.read_text(encoding="utf-8")
    assert "没有可绘制的有效比例" in viewer
    assert "下载样本指标表" in viewer


@pytest.mark.parametrize("counts", [[-1], [float("inf")], ["bad"], [None]])
def test_invalid_matrix_counts_rejected(tmp_path, counts):
    with pytest.raises(ValueError):
        MaitNktService.prepare_inputs(tra_df=pd.DataFrame({"CDR3": ["CASSAAA"], "001": counts}),
            profile_df=pd.DataFrame(), group_field="__all_samples__")


def test_long_table_batch_identity_and_count_validation(profile_app, tmp_path):
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,batch,group\n001,甲,01\n001,乙,01\n", encoding="utf-8")
    tra = tmp_path / "TRA.csv"
    tra.write_text("sample,batch,junction_aa,count\n001,甲,CASSAAA,2\n001,乙,CASSAAA,8\n", encoding="utf-8")
    client = profile_app.test_client()
    payload = {"tra_source": "upload", "tra_path": str(tra), "profile_path": str(profile), "group_field": "group", "batch_field": "batch"}
    inspected = client.post("/api/script-hub/mait-nkt/inspect", json=payload)
    assert inspected.status_code == 200, inspected.json
    assert inspected.json["sample_columns"] == ["乙::001", "甲::001"]  # pandas pivot column order
    for count in ["-1", "inf", "bad", ""]:
        tra.write_text(f"sample,batch,junction_aa,count\n001,甲,CASSAAA,{count}\n", encoding="utf-8")
        rejected = client.post("/api/script-hub/mait-nkt/run", json=payload)
        assert rejected.status_code == 400, rejected.json


@pytest.mark.parametrize("batch_field", ["category", "sample_id", "MAIT_fraction"])
def test_metadata_columns_do_not_overwrite_computed_values(tmp_path, batch_field):
    reference = tmp_path / "Alpha_Restrict.csv"
    reference.write_text("CDR3,Type\nCASSAAA,MAIT\n", encoding="utf-8")
    service = MaitNktService(output_parent=tmp_path / "results")
    service._reference_path = reference
    report = service.generate_report(tra_df=pd.DataFrame({"CDR3": ["CASSAAA", "OTHER"], "甲::001": [2, 8]}),
        profile_df=pd.DataFrame({"sample": ["001"], batch_field: ["甲"], "group": ["01"]}),
        group_field="group", batch_field=batch_field)
    result = pd.read_csv(report.csv_paths[0], dtype={"sample": str, "sample_id": str, "original_sample_id": str, "category": str})
    assert result["MAIT_fraction"].tolist() == [0.2]
    assert result["category"].tolist() == ["01"]
    assert result["sample"].tolist() == ["甲::001"]
    assert result[report.metadata["sample_id_column"]].tolist() == ["001"]
    assert result[report.metadata["batch_column"]].tolist() == ["甲"]
