"""Actual database matching with sample/batch selection and isolated references."""
from pathlib import Path

import pandas as pd
import pytest

from flask_app.tests.test_profile_workflow import profile_app
from flask_app.tests.test_sample_input_mapping import mapping_project, register
from flask_app.services.db_alignment_service import DBAlignmentService
from flask_app.exceptions import ValidationError


@pytest.fixture
def alignment_inputs(tmp_path, monkeypatch):
    refs = tmp_path / "references"
    refs.mkdir()
    vdj = refs / "VDJdb.csv"
    mcpas = refs / "McPAS.csv"
    pd.DataFrame({"CDR3": ["CASS"], "Species": ["HomoSapiens"], "Epitope": ["E1"],
                  "Epitope species": ["Viral"], "Reference": ["fixture-reference"]}).to_csv(vdj, index=False)
    pd.DataFrame({"CDR3.alpha.aa": ["CASS"], "CDR3.beta.aa": [""], "Species": ["Human"],
                  "Epitope.peptide": ["E1"], "Pathology": ["Viral"], "PubMed.ID": ["fixture"]}).to_csv(mcpas, index=False)
    original_init = DBAlignmentService.__init__
    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.vdjdb_path = vdj
        self.mcpas_path = mcpas
        self.iedb_path = refs / "not-present.csv"
    monkeypatch.setattr(DBAlignmentService, "__init__", initialize)
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,batch,group\n001,甲,01\n001,乙,01\n001,丙,02\n", encoding="utf-8")
    files = []
    for batch, copies in [("甲", [9, 1]), ("乙", [2, 8]), ("丙", [7, 3])]:
        path = tmp_path / "pep" / batch / "TRA" / "001__TRA.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"CDR3(pep)": ["ASS", "QQQQ"], "copy": copies}).to_csv(path, index=False)
        files.append(path)
    return profile, files


def test_database_batch_selection_reaches_actual_matching_api_and_download(profile_app, mapping_project, alignment_inputs, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.routes.api_script_hub._common import _cache_context_from_script_request
    profile, files = alignment_inputs
    original = profile.read_bytes()
    register(mapping_project, "profile", profile)
    for path in files:
        register(mapping_project, "pep", path)
    calls = []
    load = DBAlignmentService._load_input_frame
    def record(path, mapping):
        calls.append(Path(path))
        return load(path, mapping)
    monkeypatch.setattr(DBAlignmentService, "_load_input_frame", staticmethod(record))
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kwargs: "synthetic-result")
    payload = {"project_id": mapping_project.id, "asset_set": "Set2", "module": "db-alignment",
               "categories": ["group"], "batch_field": "batch", "contained_pathology": True,
               "pathology_values": ["Viral"], "selected_group_values": {"group": ["01"]},
               "selected_samples_by_group": {"group": {"01": ["乙::001"]}},
               "group_sample_identity": "batch_sample", "force_rerun": True,
               "field_mapping": {"cdr3_column": "CDR3(pep)", "copy_column": "copy"}}
    client = profile_app.test_client()
    response = client.post("/api/script-hub/jobs", json=payload)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    assert calls == [files[1]]
    assert task["config_json"]["group_sample_identity"] == "batch_sample"
    with profile_app.test_request_context(json=payload):
        cached = _cache_context_from_script_request(payload, "db-alignment")
    assert cached["analysis_signature"] == task["analysis_signature"]
    output = Path(task["result"]["output_base"])
    for name in ["specify_ratio_with_profile.csv", "specify_ratio/specify_ratio__Viral.csv"]:
        data = pd.read_csv(output / name, dtype={"sample": str, "group": str, "batch": str})
        assert data[["sample", "batch", "group"]].to_dict("records") == [{"sample": "001", "batch": "乙", "group": "01"}]
        assert data["TRA_copy_ratio_Combined"].iloc[0] == pytest.approx(.2)
        assert data["TRA_unique_ratio_Combined"].iloc[0] == pytest.approx(.5)
    detail = pd.read_csv(output / "alignment_summary.csv", dtype={"sample": str})
    assert detail[["sample", "batch"]].to_dict("records") == [{"sample": "001", "batch": "乙"}]
    assert task["result"]["sample_count"] == 1
    assert len(task["result"]["csv_urls"]) == 3
    for url in task["result"]["csv_urls"] + [task["result"]["zip_url"], task["result"]["viewer_url"]]:
        assert client.get(url).status_code == 200, url
    assert "<h1>数据库比对</h1>" in client.get(task["result"]["viewer_url"]).get_data(as_text=True)
    assert profile.read_bytes() == original
    invalid = {**payload, "selected_samples_by_group": {"group": {"01": ["丙::001"]}}}
    assert client.post("/api/script-hub/db-alignment/run", json=invalid).status_code == 400


def test_multiple_inputs_deduplicate_and_raw_selection_keeps_both_batches(profile_app, alignment_inputs, tmp_path):
    from flask_app.routes.api_script_hub.modules_config import _discover_db_alignment_inputs
    profile, files = alignment_inputs
    discovery = _discover_db_alignment_inputs(str(files[0]), str(profile), pep_paths=[str(file) for file in files] + [str(files[0].parent)], batch_field="batch")
    assert discovery["sample_count"] == 3
    assert discovery["pep_file_count"] == 3
    report = DBAlignmentService(output_parent=tmp_path / "results").generate_report(
        samples=discovery["samples"], selected_chains=["TRA"],
        field_mapping=discovery["resolved_field_mapping"], profile_path=str(profile), categories=["group"],
        batch_field="batch", selected_group_values={"group": ["01"]},
        selected_samples_by_group={"group": {"01": ["001"]}}, contained_pathology=True,
    )
    data = pd.read_csv(report.output_base / "specify_ratio_with_profile.csv", dtype={"sample": str, "group": str})
    assert data[["sample", "batch", "group"]].to_dict("records") == [
        {"sample": "001", "batch": "甲", "group": "01"}, {"sample": "001", "batch": "乙", "group": "01"}]
    assert data["TRA_copy_ratio_Combined"].tolist() == [.9, .2]
    assert report.metadata["sample_count"] == 2
    details = pd.read_csv(report.output_base / "alignment_summary.csv")
    assert details["vdjdb_file"].nunique() == 2
    for name in details["vdjdb_file"]:
        assert (report.output_base / "alignment" / name).is_file()
    pathology = pd.read_csv(report.output_base / "specify_ratio/specify_ratio__Viral.csv")
    assert len(pathology) == 2


def test_duplicate_files_cannot_be_silently_combined_without_batch(profile_app, alignment_inputs):
    profile, files = alignment_inputs
    client = profile_app.test_client()
    response = client.post("/api/script-hub/db-alignment/inspect", json={"pep_paths": [str(file) for file in files], "profile_path": str(profile)})
    assert response.status_code == 400
    assert "批次字段" in response.json["message"]
    checked = client.post("/api/script-hub/db-alignment/inspect", json={"pep_paths": [str(file) for file in files], "profile_path": str(profile), "batch_field": "batch"})
    assert checked.status_code == 200, checked.json
    assert checked.json["sample_count"] == 3
    assert {item["name"]: item["available"] for item in checked.json["reference_sources"]} == {"VDJdb": True, "McPAS-TCR": True, "IEDB": False}


def test_empty_and_invalid_batch_selection_are_rejected(alignment_inputs, tmp_path):
    profile, files = alignment_inputs
    service = DBAlignmentService(output_parent=tmp_path / "results")
    with pytest.raises(ValidationError, match="筛选后没有可分析的样本"):
        service.generate_report(samples=[], selected_chains=["TRA"], field_mapping={}, profile_path=str(profile),
                                batch_field="batch", selected_samples_by_group={"group": {"01": []}})
    with pytest.raises(ValidationError, match="批次样本选择"):
        service.generate_report(samples=[], selected_chains=["TRA"], field_mapping={}, group_sample_identity="batch_sample")


def test_numeric_looking_groups_remain_distinct_in_comparison(tmp_path):
    from flask_app.services.boxplot_service import BoxPlotService
    source = tmp_path / "source.csv"
    source.write_text("sample,group,TRA_copy_ratio_Combined\n001,01,0.1\n002,01,0.2\n003,1,0.8\n004,1,0.9\n", encoding="utf-8")
    result = BoxPlotService(output_parent=tmp_path / "results").generate_significance_boxplots(
        output_base=tmp_path / "results", sources=[{"label": "整体", "source": "overall", "path": source}],
        category_columns=["group"], metric_columns=["TRA_copy_ratio_Combined"],
    )
    assert len(result["all_plots"]) == 1


def test_two_column_and_custom_mappings_are_checked_by_their_actual_contract(profile_app, tmp_path):
    from flask_app.services.input_quality import validate_analysis_inputs, inspect_input_quality
    file = tmp_path / "001__TRA.csv"
    profile = tmp_path / "profile.csv"
    profile.write_text("sample,group\n001,A\n", encoding="utf-8")
    file.write_text("sequence,abundance\nASS,2\nQQQQ,8\n", encoding="utf-8")
    config = {"field_mapping": {"cdr3_column": "sequence", "copy_column": "abundance"}}
    inputs = [{"asset_type": "pep", "path": str(file)}, {"asset_type": "profile", "path": str(profile)}]
    checked = validate_analysis_inputs(inputs, config)
    assert checked["errors"] == []
    assert checked["alignments"][0]["matched_count"] == 1
    assert checked["inputs"][0]["status"] == "checked"
    assert inspect_input_quality([str(file)], "", "", "", pep_field_mapping={"cdr3_column": "sequence", "copy_column": "missing"})["errors"]
    # A mapping with different columns must not reuse the previous valid cache.
    assert validate_analysis_inputs(inputs, config)["errors"] == []
    file.write_text("sequence,abundance\nASS,-2\nQQQQ,8\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="无效拷贝数"):
        validate_analysis_inputs(inputs, config)


def test_custom_field_check_cannot_reuse_a_different_valid_upload_cache(profile_app, mapping_project, tmp_path):
    from flask_app.models.database import db
    from flask_app.services.input_quality import inspect_input_quality
    source = tmp_path / "001__TRA.csv"
    source.write_text("CDR3(pep),V,J,copy,sequence,abundance\nASS,TRAV1,TRAJ1,2,,8\nQQQQ,TRAV1,TRAJ1,8,CQQQ,2\n", encoding="utf-8")
    asset = register(mapping_project, "pep", source)
    asset.metadata_json = {**asset.metadata_json, "content_version": "synthetic-immutable-version"}
    db.session.commit()
    default = inspect_input_quality([str(source)], "", "", "")
    assert default["errors"] == []
    assert asset.metadata_json["validation"]["key"]["options"] == {}
    mapping = {"cdr3_column": "sequence", "copy_column": "abundance"}
    mapped = inspect_input_quality([str(source)], "", "", "", pep_field_mapping=mapping)
    assert mapped["errors"] and "空必需字段" in mapped["errors"][0]
    assert asset.metadata_json["validation"]["key"]["options"] == {"field_mapping": mapping}
    assert asset.metadata_json["validation"]["status"] == "invalid"
    restored = inspect_input_quality([str(source)], "", "", "")
    assert restored["errors"] == []
    assert asset.metadata_json["validation"]["key"]["options"] == {}
