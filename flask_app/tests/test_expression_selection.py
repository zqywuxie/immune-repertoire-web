"""Actual expression columns flow through limma and immutable DEG reuse."""
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from flask_app.services.volcano_service import VolcanoService
from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register


def expression_table(path):
    random = np.random.default_rng(58)
    genes = ["TP53", "EGFR", "CD3D", "CD3E", "CD3G", "CD247", "CD4", "CD8A", "CD8B", "LCK", "ZAP70", "LAT", "LCP2", "ITK", "FYN", "PTPRC", "CD28", "CTLA4", "ICOS", "PDCD1", "IL2", "IL2RA", "IL2RB", "JAK1"]
    values = {"Gene": genes}
    for group in ["01", "02"]:
        for index in range(1, 5):
            values[f"tpm_{group}_{index:03d}"] = random.uniform(5, 100, len(genes)) + np.arange(len(genes)) * (3 if group == "01" else 1)
    data = pd.DataFrame(values); data.to_csv(path, index=False)
    return data


def test_real_expression_subset_and_differential_reuse(profile_app, mapping_project, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services import go_kegg_enrichment_service as enrichment
    from flask_app.services.differential_artifacts import resolve_differential_input
    path = tmp_path / "expression.csv"; frame = expression_table(path); register(mapping_project, "transcriptome", path)
    original_input = path.read_bytes()
    selected = [f"tpm_{group}_{index:03d}" for group in ["01", "02"] for index in range(1, 4)]
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kw: fn(task, **kw))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kw: "isolated-result")
    client = profile_app.test_client()
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "volcano", "input_mode": "expression",
        "selected_expression_groups": ["01", "02"], "selected_expression_samples": selected, "comparisons": ["02_vs_01"],
        "logfc_cutoff": 0, "output_name": "选定表达样本", "force_rerun": True,
        "selected_samples": ["unused-profile-id"], "selected_group_values": {"unused": ["unknown"]}}
    inspected = client.post("/api/script-hub/volcano/inspect", json=payload)
    assert inspected.status_code == 200, inspected.json
    assert inspected.json["sample_count"] == 8
    assert inspected.json["samples_by_value"]["01"] == [f"tpm_01_{i:03d}" for i in range(1, 5)]
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    result = task["result"]; output = Path(result["output_base"])
    assert result["metadata"]["selected_expression_samples"] == selected
    assert result["metadata"]["sample_count"] == 6 and result["metadata"]["logfc_cutoff"] == 0
    quality = pd.read_csv(output / "DEG" / "02_vs_01" / "QC" / "sample_quality_weights.csv")
    assert quality["sample"].tolist() == selected
    manual = tmp_path / "subset.csv"; frame[["Gene", *selected]].to_csv(manual, index=False)
    expected = VolcanoService(output_parent=tmp_path / "expected").generate_expression_report(expression_path=str(manual), comparisons=[["02", "01"]], logfc_cutoff=0)
    source_table = output / "DEG" / "02_vs_01" / "DEG_02_vs_01.csv"
    actual = pd.read_csv(source_table)
    pd.testing.assert_frame_equal(actual, pd.read_csv(Path(expected.output_base) / "DEG" / "02_vs_01" / "DEG_02_vs_01.csv"))
    with profile_app.test_request_context(json=payload):
        assert shared._cache_context_from_script_request(payload, "volcano")["analysis_signature"] == task["analysis_signature"]
        changed_scope = {**payload, "selected_expression_samples": selected[:-1]}
        assert shared._cache_context_from_script_request(changed_scope, "volcano")["analysis_signature"] != task["analysis_signature"]
    original_deg = source_table.read_bytes()
    candidates = client.get("/api/script-hub/go-kegg-enrichment/sources", query_string={"project_id": mapping_project.id, "asset_set": "Set2"}).json["candidates"]
    source = next(item for item in candidates if item["job_id"] == response.json["task_id"])
    assert source["metadata"]["selected_expression_samples"] == selected
    monkeypatch.setattr(enrichment.VolcanoService, "generate_expression_report", lambda *a, **kw: pytest.fail("reuse must not recalculate limma"))
    def fake_enrichment(command, **kwargs):
        assert (Path(command[2]) / "02_vs_01" / source_table.name).read_bytes() == original_deg
        table = Path(command[3]) / "ORA.csv"; table.write_text("ID,pvalue,p.adjust\nGO:0002250,0.8,0.9\n")
        return SimpleNamespace(returncode=0, stdout="isolated enrichment stage", stderr="")
    monkeypatch.setattr(enrichment.subprocess, "run", fake_enrichment)
    reuse = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "go-kegg-enrichment", "input_mode": "deg",
        "upstream_artifact_id": source["id"], "output_name": "复用表达样本富集", "force_rerun": True,
        "comparisons": [["ignored", "different"]], "selected_expression_samples": ["ignored"], "pvalue_threshold": 0.8, "logfc_cutoff": 99}
    enriched = client.post("/api/script-hub/jobs", json=reuse)
    assert enriched.status_code == 200, enriched.json
    downstream = shared._get_task_state(enriched.json["task_id"])
    assert downstream["status"] == "completed", downstream
    assert downstream["result"]["metadata"]["selected_expression_samples"] == selected
    assert downstream["result"]["metadata"]["logfc_cutoff"] == 0
    assert downstream["result"]["metadata"]["output_name"] == "复用表达样本富集"
    with profile_app.test_request_context(json=reuse):
        assert shared._cache_context_from_script_request(reuse, "go-kegg-enrichment")["analysis_signature"] == downstream["analysis_signature"]
        changed_hidden = {**reuse, "comparisons": [], "pvalue_threshold": 0.2, "selected_expression_samples": []}
        assert shared._cache_context_from_script_request(changed_hidden, "go-kegg-enrichment")["analysis_signature"] == downstream["analysis_signature"]
    assert source_table.read_bytes() == original_deg and path.read_bytes() == original_input
    for url in result["csv_urls"] + [result["viewer_url"], result["zip_url"]] + downstream["result"]["csv_urls"] + [downstream["result"]["viewer_url"], downstream["result"]["zip_url"]]:
        assert client.get(url).status_code == 200
    for changes in ({"selected_expression_samples": []}, {"selected_expression_samples": ["unknown"]}, {"selected_expression_groups": []},
                    {"selected_expression_samples": ["tpm_01_001", "tpm_02_001"]}):
        rejected = client.post("/api/script-hub/jobs", json={**payload, **changes})
        assert rejected.status_code == 400, (changes, rejected.json)


def test_direct_enrichment_cache_and_parameter_preflight(profile_app, mapping_project, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    path = tmp_path / "expression.csv"; expression_table(path); register(mapping_project, "transcriptome", path)
    submitted = {}; monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kw: submitted.update(kw))
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "input_mode": "expression", "logfc_cutoff": 0,
        "comparisons": [["tpm_01_001", "tpm_02_001"]], "selected_expression_samples": [f"tpm_{group}_{i:03d}" for group in ["01", "02"] for i in range(1, 4)], "force_rerun": True}
    response = profile_app.test_client().post("/api/script-hub/go-kegg-enrichment/run", json=payload)
    assert response.status_code == 200, response.json
    assert submitted["logfc_cutoff"] == 0 and submitted["comparisons"] == [["01", "02"]]
    assert submitted["selected_expression_samples"] == payload["selected_expression_samples"]
    task = shared._get_task_state(response.json["task_id"])
    with profile_app.test_request_context(json=payload):
        assert shared._cache_context_from_script_request(payload, "go-kegg-enrichment")["analysis_signature"] == task["analysis_signature"]
    for changes in ({"show_category": 0}, {"show_category": 1.5}, {"enrich_pvalue_cutoff": 0}, {"p_adjust_method": "bad"}, {"comparisons": []}):
        rejected = profile_app.test_client().post("/api/script-hub/go-kegg-enrichment/run", json={**payload, **changes})
        assert rejected.status_code == 400, (changes, rejected.json)


def test_expression_preparation_rejects_explicit_empty_comparisons(tmp_path):
    path = tmp_path / "expression.csv"; expression_table(path)
    with pytest.raises(ValueError, match="至少选择一个表达组间比较"):
        VolcanoService.prepare_expression_input(str(path), comparisons=[], validate=True)


@pytest.mark.parametrize("suffix", [".csv", ".csv.gz", ".tsv.gz", ".xlsx"])
def test_expression_inspection_reads_only_headers_and_gene_identifiers(tmp_path, monkeypatch, suffix):
    path = tmp_path / ("expression" + suffix)
    frame = expression_table(tmp_path / "seed.csv")
    frame = pd.concat([frame, frame.iloc[:2]], ignore_index=True)
    if suffix == ".xlsx":
        frame.to_excel(path, index=False)
    else:
        frame.to_csv(path, index=False, sep="\t" if suffix.startswith(".tsv") else ",")
    expected = VolcanoService.prepare_expression_input(str(path))
    reader = pd.read_excel if suffix == ".xlsx" else pd.read_csv
    calls = []
    def bounded_read(*args, **kwargs):
        calls.append(kwargs)
        assert kwargs.get("nrows") == 0 or kwargs.get("usecols") == [0]
        return reader(*args, **kwargs)
    monkeypatch.setattr(pd, "read_excel" if suffix == ".xlsx" else "read_csv", bounded_read)
    inspected = VolcanoService.inspect_expression_matrix(str(path))
    assert len(calls) == 2
    assert inspected["gene_count"] == len(expected["data"])
    assert inspected["sample_count"] == 8
    assert inspected["samples_by_value"] == expected["samples_by_value"]


def test_expression_inspection_retries_encoding_after_ascii_rows(tmp_path):
    path = tmp_path / "gbk.csv"
    # The non-ASCII identifier appears after pandas' initial parser buffer.
    prefix = "Gene,tpm_01_001,tpm_02_001\n" + "G,1,2\n" * 60000
    path.write_bytes((prefix + "中文基因,1,2\n").encode("gbk"))
    inspected = VolcanoService.inspect_expression_matrix(str(path))
    assert inspected["gene_count"] == 2
    assert inspected["samples_by_value"] == {"01": ["tpm_01_001"], "02": ["tpm_02_001"]}


@pytest.mark.parametrize("module", ["volcano", "go-kegg-enrichment"])
@pytest.mark.parametrize("comparisons", [["02_vs_01"], [["02", "01"]], [{"group1": "02", "group2": "01"}]])
def test_expression_ui_comparison_formats_share_direction_and_cache(profile_app, mapping_project, tmp_path, monkeypatch, module, comparisons):
    from flask_app.routes.api_script_hub import _common as shared
    path = tmp_path / "expression.csv"
    expression_table(path)
    register(mapping_project, "transcriptome", path)
    submitted = {}
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kw: submitted.update(kw))
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": module,
        "input_mode": "expression", "comparisons": comparisons, "force_rerun": True,
        "selected_expression_samples": [f"tpm_{group}_{i:03d}" for group in ["01", "02"] for i in range(1, 4)]}
    response = profile_app.test_client().post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    assert submitted["comparisons"] == [["02", "01"]]
    with profile_app.test_request_context(json=payload):
        expected = shared._cache_context_from_script_request({**payload, "comparisons": [["02", "01"]]}, module)
        actual = shared._cache_context_from_script_request(payload, module)
        assert expected["analysis_signature"] == actual["analysis_signature"]
    rejected = profile_app.test_client().post("/api/script-hub/jobs", json={**payload, "comparisons": ["missing-comparison"]})
    assert rejected.status_code == 400
    assert rejected.json["details"]["field"] == "comparisons"
