"""Exercise TopClone selection through actual calculations and result retrieval."""
from pathlib import Path

import pandas as pd
import pytest

from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register
from flask_app.services.topclone_service import TopCloneService


def write_inputs(tmp_path):
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,batch,group\n001,甲,01\n001,乙,01\n001,丙,02\n", encoding="utf-8")
    files = []
    for batch in ["甲", "乙", "丙"]:
        file = tmp_path / "pep" / batch / "TRA" / "001__TRA.csv"
        file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"CDR3(pep)": [f"CASS{batch}{i}" for i in range(12)],
                      "copy": list(range(12, 0, -1)), "joinedSeq": "ATGC",
                      "V": "TRAV1", "D": "", "J": "TRAJ1", "C": "TRAC"}).to_csv(file, index=False)
        files.append(file)
    return profile, files


@pytest.mark.parametrize("mode,minimal", [("trace", False), ("trace", True), ("per_sample", False)])
def test_batch_choice_reaches_topclone_outputs_and_download(profile_app, mapping_project, tmp_path, monkeypatch, mode, minimal):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.routes.api_script_hub._common import _cache_context_from_script_request
    import flask_app.services.topclone_service as implementation
    profile, files = write_inputs(tmp_path)
    if minimal:
        for file in files:
            pd.read_csv(file)[["CDR3(pep)", "copy"]].to_csv(file, index=False)
    original = profile.read_bytes()
    register(mapping_project, "profile", profile)
    for file in files:
        register(mapping_project, "pep", file)
    calls = []
    read = implementation._try_read_csv
    def record(path, **kwargs):
        if Path(path) in files:
            calls.append(Path(path))
        return read(path, **kwargs)
    monkeypatch.setattr(implementation, "_try_read_csv", record)
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kwargs: "synthetic-result")
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "topclone",
               "mode": mode, "top_n": 3, "group_field": "group", "batch_field": "batch",
               "selected_chains": ["TRA"], "selected_group_values": {"group": ["01"]},
               "selected_samples_by_group": {"group": {"01": ["乙::001"]}},
               "group_sample_identity": "batch_sample", "force_rerun": True}
    client = profile_app.test_client()
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    assert calls == [files[1]], "Unselected clone data must never enter computation"
    assert task["config_json"]["group_sample_identity"] == "batch_sample"
    with profile_app.test_request_context(json=payload):
        cached = _cache_context_from_script_request(payload, "topclone")
    assert cached["analysis_signature"] == task["analysis_signature"]
    output = Path(task["result"]["output_base"])
    if mode == "trace":
        data = pd.read_csv(output / "topclone.csv", dtype=str)
        assert data[["sample", "batch", "group"]].to_dict("records") == [{"sample": "001", "batch": "乙", "group": "01"}]
        assert float(data["top10TRA"].iloc[0]) == pytest.approx(75 / 78)
        assert float(data["top20TRA"].iloc[0]) == 1
        cdr3 = pd.read_csv(output / "top_cdr3_sequences/TRA/top10_cdr3s.csv", dtype=str)
        assert cdr3["batch"].tolist() == ["乙"]
    else:
        summary = pd.read_csv(output / "top_clones/summary.csv", dtype=str)
        assert summary[["sample", "batch", "chain"]].to_dict("records") == [{"sample": "001", "batch": "乙", "chain": "TRA"}]
        result = pd.read_csv(summary["file"].iloc[0])
        assert result["CDR3(pep)"].tolist() == ["CASS乙0", "CASS乙1", "CASS乙2"]
    assert client.get(task["result"]["zip_url"]).status_code == 200
    assert task["result"]["cdr3_urls"]
    for url in task["result"]["cdr3_urls"] + task["result"]["csv_urls"]:
        assert client.get(url).status_code == 200, url
    assert task["result"]["metadata"]["sample_count"] == 1
    assert profile.read_bytes() == original
    invalid = {**payload, "selected_samples_by_group": {"group": {"01": ["丙::001"]}}}
    rejected = client.post("/api/script-hub/topclone/run", json=invalid)
    assert rejected.status_code == 400, rejected.json


def test_per_sample_keeps_batch_files_and_legacy_raw_selection(tmp_path):
    profile, files = write_inputs(tmp_path)
    report = TopCloneService(output_parent=tmp_path / "results").generate_report(
        pep_data_path=str(files[0]), pep_paths=[str(file) for file in files] + [str(files[0].parent)],
        datapoint_path=str(profile), batch_field="batch", mode="per_sample", top_n=2,
        selected_group_values={"group": ["01"]}, selected_samples_by_group={"group": {"01": ["001"]}},
    )
    assert len(report.per_sample_files) == 2
    assert len(set(report.per_sample_files)) == 2
    summary = pd.read_csv(report.output_base / "top_clones/summary.csv", dtype=str)
    assert summary[["sample", "batch"]].to_dict("records") == [{"sample": "001", "batch": "甲"}, {"sample": "001", "batch": "乙"}]
    for file, batch in zip(report.per_sample_files, ["甲", "乙"]):
        assert pd.read_csv(file)["CDR3(pep)"].tolist() == [f"CASS{batch}0", f"CASS{batch}1"]


def test_empty_selection_is_reported(tmp_path):
    profile, files = write_inputs(tmp_path)
    with pytest.raises(ValueError, match="筛选后没有可分析的样本"):
        TopCloneService(output_parent=tmp_path / "results").generate_report(
            pep_data_path=str(files[0]), datapoint_path=str(profile), batch_field="batch",
            selected_samples_by_group={"group": {"01": []}},
        )


def test_raw_sample_filter_and_profile_free_per_sample(tmp_path):
    profile, files = write_inputs(tmp_path)
    profile.write_text("sample,group\n001,A\n002,B\n", encoding="utf-8")
    second = files[0].with_name("002__TRA.csv")
    second.write_bytes(files[0].read_bytes())
    service = TopCloneService(output_parent=tmp_path / "results")
    filtered = service.generate_report(pep_data_path=str(files[0].parent), datapoint_path=str(profile),
                                       mode="per_sample", selected_samples=["002"])
    assert len(filtered.per_sample_files) == 1
    summary = pd.read_csv(filtered.output_base / "top_clones/summary.csv", dtype=str)
    assert summary["sample"].tolist() == ["002"]
    plain = service.generate_report(pep_data_path=str(second), datapoint_path="", mode="per_sample")
    assert len(plain.per_sample_files) == 1


@pytest.mark.parametrize("bad_data", ["CDR3(pep),copy\n,1\n", "CDR3(pep),copy\nCASSA,-1\n", "CDR3(pep),copy\nCASSA,inf\n", "CDR3(pep)\nCASSA\n"])
def test_trace_validation_rejects_invalid_required_content(profile_app, tmp_path, bad_data):
    from flask_app.services.input_quality import validate_analysis_inputs
    from flask_app.exceptions import ValidationError
    file = tmp_path / "001__TRA.csv"
    file.write_text(bad_data, encoding="utf-8")
    with pytest.raises(ValidationError, match="输入数据检查未通过"):
        validate_analysis_inputs([{"asset_type": "pep", "path": str(file)}], {"mode": "trace"}, module_name="topclone")


def test_trace_schema_does_not_relax_pep_or_per_sample_requirements(profile_app, tmp_path):
    from flask_app.services.input_quality import validate_analysis_inputs
    from flask_app.exceptions import ValidationError
    file = tmp_path / "001__TRA.csv"
    file.write_text("CDR3(pep),copy\nCASSA,2\n", encoding="utf-8")
    assets = [{"asset_type": "pep", "path": str(file)}]
    assert validate_analysis_inputs(assets, {"mode": "trace"}, module_name="topclone")["errors"] == []
    for module, config in [("pep-analysis", {}), ("topclone", {"mode": "per_sample"})]:
        with pytest.raises(ValidationError, match="所需字段"):
            validate_analysis_inputs(assets, config, module_name=module)
