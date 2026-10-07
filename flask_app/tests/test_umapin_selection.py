"""Actual UMAPin selections use upstream row identities, never Profile aliases."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from flask_app.services.umapin_service import UmapinService
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register


def test_real_pep_to_umapin_selected_batch_and_download(profile_app, mapping_project, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services.analysis_artifacts import resolve_upstream_input
    from flask_app.services.background_job_service import get_background_job_service
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
        "asset_set": "Set2", "cache_type": "umapin"}).json["candidates"]
    artifact = next(c for c in candidates if Path(c["path"]).name == "df_VJ_all.csv")
    original = Path(artifact["path"]).read_bytes()
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "umapin", "category_col": "Category",
        "upstream_artifact_id": artifact["artifact_id"], "sample_column": "sample", "selected_categories": ["01", "02"],
        "selected_samples": [f"002::{i:03d}" for i in range(1, 9)], "n_neighbors": 3, "n_epochs": 20,
        "min_dist": 0, "output_name": "批次特征投影", "force_rerun": True,
        "selected_group_values": {"group": ["01", "02"]}, "selected_samples_by_group": {"group": {"01": ["001"], "02": ["005"]}}}
    inspection = client.post("/api/script-hub/umapin/inspect", json=payload)
    assert inspection.status_code == 200, inspection.json
    inspected = inspection.json
    assert inspected["values"] == ["01", "02"]
    assert inspected["sample_count"] == 16
    assert "002::001" in inspected["samples_by_value"]["01"]
    assert "sample" not in inspected["feature_columns"] and "Category" not in inspected["feature_columns"]
    payload.update(param_begin=inspected["suggested_param_begin"], param_over=inspected["suggested_param_over"])
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    stored = get_background_job_service().get_job(response.json["task_id"])
    assert stored["payload"]["upstream_input"]["source_job_id"] == source.json["task_id"]
    with profile_app.test_request_context(json=payload):
        resolved = dict(payload); resolve_upstream_input("umapin", resolved)
        assert shared._cache_context_from_script_request(resolved, "umapin")["analysis_signature"] == task["analysis_signature"]
    meta = task["result"]["metadata"]
    assert meta["sample_count"] == 8 and meta["min_dist"] == 0 and meta["n_epochs"] == 20
    assert meta["output_name"] == "批次特征投影" and meta["unique_groups"] == ["01", "02"]
    out = Path(task["result"]["output_base"])
    assert out.parent.name == "umapin"
    coordinates = pd.read_csv(out / "umapin_coordinates.csv", dtype=str)
    assert set(coordinates["sample"]) == set(payload["selected_samples"])
    assert set(coordinates["Category"]) == {"01", "02"}
    assert np.isfinite(coordinates[["UMAP1", "UMAP2"]].astype(float)).all().all()
    for url in task["result"]["csv_urls"] + task["result"]["png_urls"] + [task["result"]["viewer_url"], task["result"]["zip_url"]]:
        assert client.get(url).status_code == 200
    assert Path(artifact["path"]).read_bytes() == original
    for changes in ({"selected_samples": []}, {"selected_categories": []}, {"selected_samples": ["不存在"]},
                    {"min_dist": -0.1}, {"n_epochs": 0}, {"asset_set": "Set1"}):
        rejected = client.post("/api/script-hub/jobs", json={**payload, **changes})
        assert rejected.status_code == 400, (changes, rejected.json)


def test_text_identity_and_actual_numeric_feature_validation(tmp_path):
    source = tmp_path / "features.csv"
    source.write_text("sample,Category,V1,V2\n001,01,1,2\n002,01,2,1\n003,02,3,5\n", encoding="utf-8")
    data = UmapinService.prepare_input(data_path=str(source), param_begin="sample", param_over="V2")
    assert data["samples"].tolist() == ["001", "002", "003"]
    assert data["data"]["Category"].tolist() == ["01", "01", "02"]
    assert data["features"] == ["V1", "V2"]
    with pytest.raises(ValueError, match="起始列"):
        UmapinService.prepare_input(data_path=str(source), param_begin="V2", param_over="V1")


@pytest.mark.parametrize("pvalues,corrected_values", [([0.01, 0.04, 0.2], [0.03, 0.06, 0.2]), ([1, 1, 1], [1, 1, 1])])
def test_fdr_does_not_use_sample_ids_as_probabilities(tmp_path, pvalues, corrected_values):
    source = tmp_path / "features.csv"
    pd.DataFrame({"sample": ["001", "002", "003"], "Category": ["A", "A", "B"], "V1": [1, 2, 3], "p_value": pvalues}).to_csv(source, index=False)
    report = UmapinService(output_parent=tmp_path / "results").generate_report(data_path=str(source),
        param_begin="V1", param_over="V1", n_epochs=20, do_fdr=True)
    corrected = pd.read_csv(report.output_base / "fdr_p_value.csv")
    np.testing.assert_allclose(corrected["p_value_fdr_corrected"], corrected_values)
    assert not (report.output_base / "fdr_sample.csv").exists()
    assert report.metadata["fdr_status"] == "completed"


def test_real_alias_group_at_end_projection_preserves_original_input_and_ids(tmp_path):
    source = tmp_path/'features.csv'
    ids = [f'{index:03d}' for index in range(8)]
    frame = pd.DataFrame({'Sample':ids, 'V1':[1,3,2,4,7,9,8,10],
        'V2':[2,1,4,3,5,8,6,7], 'group':['01']*4+['1']*4})
    frame.to_csv(source,index=False)
    original = source.read_bytes()
    report = UmapinService(output_parent=tmp_path/'results').generate_report(
        data_path=str(source),param_begin='V1',param_over='V2',n_neighbors=3,n_epochs=30)
    assert report.metadata['sample_count'] == 8
    assert report.metadata['category_col'] == 'group'
    assert report.metadata['unique_groups'] == ['01','1']
    coordinates = pd.read_csv(report.output_base/'umapin_coordinates.csv',dtype=str)
    assert coordinates['sample'].tolist() == ids
    assert coordinates['Category'].tolist() == ['01']*4+['1']*4
    assert np.isfinite(coordinates[['UMAP1','UMAP2']].astype(float)).all().all()
    assert all(Path(path).stat().st_size for path in report.png_paths+report.csv_paths)
    assert source.read_bytes() == original
