"""Tests for DB alignment service behavior migrated from DB_pathology."""

from pathlib import Path
import hashlib
import importlib.util
import os
import sys
import zipfile
from importlib import import_module

import pandas as pd
import pytest


ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parents[1]
for import_dir in (APP_DIR, ROOT_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))

try:
    from flask_app.services.db_alignment_service import DBAlignmentService
except ModuleNotFoundError:
    from services.db_alignment_service import DBAlignmentService


def _import_script_hub_module():
    try:
        return import_module("flask_app.routes.api_script_hub")
    except ModuleNotFoundError:
        return import_module("routes.api_script_hub")


def test_db_alignment_uses_cdr3_match_and_exports_pathology_outputs(tmp_path):
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir()
    vdj_path = refs_dir / "vdjdb.csv"
    mcpas_path = refs_dir / "McPAS-TCR.csv"

    pd.DataFrame([
        {
            "CDR3": "CASS",
            "Species": "HomoSapiens",
            "Epitope": "E1",
            "Epitope species": "Viral",
            "Reference": "ref-1",
        }
    ]).to_csv(vdj_path, index=False)
    pd.DataFrame([
        {
            "CDR3.alpha.aa": "CASS",
            "CDR3.beta.aa": "",
            "Species": "Human",
            "Epitope.peptide": "E1",
            "Pathology": "Viral",
            "PubMed.ID": "123",
        }
    ]).to_csv(mcpas_path, index=False)

    pep_path = tmp_path / "Sample1__TRA.csv"
    pd.DataFrame([
        {"CDR3(pep)": "ASS", "copy": 10},
        {"CDR3(pep)": "CQQQ", "copy": 5},
    ]).to_csv(pep_path, index=False)

    profile_path = tmp_path / "Profile.csv"
    pd.DataFrame([{"Sample": "Sample1", "group_type": "case"}]).to_csv(profile_path, index=False)

    service = DBAlignmentService(output_parent=tmp_path / "results")
    service.vdjdb_path = vdj_path
    service.mcpas_path = mcpas_path

    report = service.generate_report(
        samples=[{
            "original_name": "Sample1",
            "display_name": "Sample1",
            "data_files": [{"filename": pep_path.name, "filepath": str(pep_path)}],
        }],
        selected_chains=["TRA"],
        field_mapping={"cdr3_column": "CDR3(pep)", "copy_column": "copy"},
        profile_path=str(profile_path),
        categories=["group_type", "timepoint"],
        category_mode="cross",
        contained_pathology=True,
    )

    vdj_result = pd.read_csv(report.output_base / "alignment" / "Sample1__TRA__VDJdb.csv")
    assert vdj_result.loc[0, "CDR3(pep)"] == "ASS"
    assert vdj_result.loc[0, "copy"] == 10

    pathology_vdj = report.output_base / "alignment" / "Viral" / "Sample1__TRA__VDJdb.csv"
    pathology_ratio = report.output_base / "specify_ratio" / "specify_ratio__Viral.csv"
    assert pathology_vdj.exists()
    assert pathology_ratio.exists()

    ratio_df = pd.read_csv(pathology_ratio)
    assert ratio_df.loc[0, "group_type"] == "case"
    assert ratio_df.loc[0, "cross_category"] == "case"
    assert ratio_df.loc[0, "TRA_ratio_VDJdb"] == 10 / 15
    assert ratio_df.loc[0, "TRA_ratio_McPASTCR"] == 10 / 15
    assert ratio_df.loc[0, "TRA_copy_ratio_Combined"] == 10 / 15
    assert report.metadata["available_reference_sources"] == ["VDJdb", "McPAS-TCR"]
    versions = report.metadata["reference_versions"]
    assert versions["vdjdb"]["sha256"] == hashlib.sha256(vdj_path.read_bytes()).hexdigest()
    assert versions["mcpas_tcr"]["sha256"] == hashlib.sha256(mcpas_path.read_bytes()).hexdigest()


def test_pep_category_alignment_groups_shared_categories_and_writes_ratios(tmp_path):
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir()
    vdj_path = refs_dir / "vdjdb.csv"
    mcpas_path = refs_dir / "McPAS-TCR.csv"
    pd.DataFrame([{
        "CDR3": "CASS", "Species": "HomoSapiens", "Epitope": "E1",
        "Epitope species": "Virus", "Reference": "ref-1",
    }]).to_csv(vdj_path, index=False)
    pd.DataFrame([{
        "CDR3.alpha.aa": "CASS", "CDR3.beta.aa": "", "Species": "Human",
        "Epitope.peptide": "E1", "Pathology": "Virus", "PubMed.ID": "123",
    }]).to_csv(mcpas_path, index=False)
    categorized = tmp_path / "TRA.csv"
    pd.DataFrame([
        {"CDR3(pep)": "CASS", "category": "('A__count', 'B__count')", "A__sum": 4, "B__sum": 6},
        {"CDR3(pep)": "CQQQ", "category": "('A__count', 'B__count')", "A__sum": 2, "B__sum": 0},
    ]).to_csv(categorized, index=False)

    service = DBAlignmentService(output_parent=tmp_path / "results")
    service.vdjdb_path = vdj_path
    service.mcpas_path = mcpas_path
    report = service.generate_pep_category_alignment(
        categorized_files={"TRA": str(categorized)},
        output_base=tmp_path / "results" / "category_alignment",
    )

    manifest = pd.read_csv(report["manifest_path"])
    assert manifest.loc[0, "status"] == "completed"
    overall = pd.read_csv(tmp_path / "results" / "category_alignment" / "TRA" / "A__B__shared" / "specify_ratio" / "overall.csv")
    assert overall.set_index("database").loc["VDJdb", "ratio"] == 10 / 12
    assert overall.set_index("database").loc["VDJdb", "unique_ratio"] == 1 / 2
    pathology = tmp_path / "results" / "category_alignment" / "TRA" / "A__B__shared" / "alignment" / "Virus" / "A__B__shared__TRA__McPASTCR.csv"
    assert pd.read_csv(pathology).loc[0, "copy"] == 10


def test_db_alignment_reads_selected_profile_xlsx_sheet(tmp_path):
    pytest.importorskip("openpyxl")

    refs_dir = tmp_path / "refs"
    refs_dir.mkdir()
    vdj_path = refs_dir / "vdjdb.csv"
    mcpas_path = refs_dir / "McPAS-TCR.csv"

    pd.DataFrame([{
        "CDR3": "CASS",
        "Species": "HomoSapiens",
        "Epitope": "E1",
        "Epitope species": "Viral",
        "Reference": "ref-1",
    }]).to_csv(vdj_path, index=False)
    pd.DataFrame([{
        "CDR3.alpha.aa": "CASS",
        "CDR3.beta.aa": "",
        "Species": "Human",
        "Epitope.peptide": "E1",
        "Pathology": "Viral",
        "PubMed.ID": "123",
    }]).to_csv(mcpas_path, index=False)

    pep_path = tmp_path / "Sample1__TRA.csv"
    pd.DataFrame([{"CDR3(pep)": "ASS", "copy": 10}]).to_csv(pep_path, index=False)

    profile_path = tmp_path / "SelectedProfile.xlsx"
    with pd.ExcelWriter(profile_path) as writer:
        pd.DataFrame([{"Sample": "Sample1", "wrong_group": "ignore"}]).to_excel(writer, sheet_name="Ignore", index=False)
        pd.DataFrame([{"Sample": "Sample1", "group_type": "case"}]).to_excel(writer, sheet_name="Meta", index=False)

    service = DBAlignmentService(output_parent=tmp_path / "results")
    service.vdjdb_path = vdj_path
    service.mcpas_path = mcpas_path

    report = service.generate_report(
        samples=[{
            "original_name": "Sample1",
            "display_name": "Sample1",
            "data_files": [{"filename": pep_path.name, "filepath": str(pep_path)}],
        }],
        selected_chains=["TRA"],
        field_mapping={"cdr3_column": "CDR3(pep)", "copy_column": "copy"},
        profile_path=str(profile_path),
        profile_sheet="Meta",
        categories=["group_type"],
    )

    merged = pd.read_csv(report.output_base / "specify_ratio_with_profile.csv")
    assert report.metadata["profile_path"] == str(profile_path.resolve())
    assert report.metadata["profile_sheet"] == "Meta"
    assert merged.loc[0, "group_type"] == "case"


def test_profile_category_preview_uses_selected_sheet(tmp_path):
    pytest.importorskip("openpyxl")
    api_script_hub = _import_script_hub_module()

    profile_path = tmp_path / "SelectedProfile.xlsx"
    with pd.ExcelWriter(profile_path) as writer:
        pd.DataFrame([{"Sample": "Sample1", "group_type": "ignore"}]).to_excel(writer, sheet_name="Ignore", index=False)
        pd.DataFrame([
            {"Sample": "Sample1", "group_type": "case", "timepoint": "D0"},
            {"Sample": "Sample2", "group_type": "control", "timepoint": "D7"},
            {"Sample": "Sample3", "group_type": "case", "timepoint": "D7"},
        ]).to_excel(writer, sheet_name="Meta", index=False)

    preview = api_script_hub._build_profile_category_preview(
        profile_path=str(profile_path),
        profile_sheet="Meta",
        categories=["group_type", "timepoint"],
    )

    fields = {item["field"]: item for item in preview["fields"]}
    assert fields["group_type"]["values"] == ["case", "control"]
    assert fields["timepoint"]["values"] == ["D0", "D7"]


def test_db_alignment_generates_all_and_significant_boxplot_directories(tmp_path):
    refs_dir = tmp_path / "refs"
    refs_dir.mkdir()
    vdj_path = refs_dir / "vdjdb.csv"
    mcpas_path = refs_dir / "McPAS-TCR.csv"

    pd.DataFrame([{
        "CDR3": "CASS",
        "Species": "HomoSapiens",
        "Epitope": "E1",
        "Epitope species": "Viral",
        "Reference": "ref-1",
    }]).to_csv(vdj_path, index=False)
    pd.DataFrame([{
        "CDR3.alpha.aa": "CASS",
        "CDR3.beta.aa": "",
        "Species": "Human",
        "Epitope.peptide": "E1",
        "Pathology": "Viral",
        "PubMed.ID": "123",
    }]).to_csv(mcpas_path, index=False)

    samples = []
    profile_rows = []
    for index in range(5):
        sample = f"Case{index + 1}"
        pep_path = tmp_path / f"{sample}__TRA.csv"
        trb_path = tmp_path / f"{sample}__TRB.csv"
        pd.DataFrame([{"CDR3(pep)": "ASS", "copy": 10}]).to_csv(pep_path, index=False)
        pd.DataFrame([{"CDR3(pep)": "CZZZ", "copy": 10}]).to_csv(trb_path, index=False)
        samples.append({
            "original_name": sample,
            "display_name": sample,
            "data_files": [
                {"filename": pep_path.name, "filepath": str(pep_path)},
                {"filename": trb_path.name, "filepath": str(trb_path)},
            ],
        })
        profile_rows.append({"Sample": sample, "group_type": "case"})

    for index in range(5):
        sample = f"Control{index + 1}"
        pep_path = tmp_path / f"{sample}__TRA.csv"
        trb_path = tmp_path / f"{sample}__TRB.csv"
        pd.DataFrame([{"CDR3(pep)": "CQQQ", "copy": 10}]).to_csv(pep_path, index=False)
        pd.DataFrame([{"CDR3(pep)": "CZZZ", "copy": 10}]).to_csv(trb_path, index=False)
        samples.append({
            "original_name": sample,
            "display_name": sample,
            "data_files": [
                {"filename": pep_path.name, "filepath": str(pep_path)},
                {"filename": trb_path.name, "filepath": str(trb_path)},
            ],
        })
        profile_rows.append({"Sample": sample, "group_type": "control"})

    profile_path = tmp_path / "Profile.csv"
    pd.DataFrame(profile_rows).to_csv(profile_path, index=False)

    service = DBAlignmentService(output_parent=tmp_path / "results")
    service.vdjdb_path = vdj_path
    service.mcpas_path = mcpas_path

    report = service.generate_report(
        samples=samples,
        selected_chains=["TRA", "TRB"],
        field_mapping={"cdr3_column": "CDR3(pep)", "copy_column": "copy"},
        profile_path=str(profile_path),
        categories=["group_type"],
        category_mode="single",
    )

    assert report.metadata["boxplot_count"] >= report.metadata["significant_boxplot_count"]
    assert report.metadata["significant_boxplot_count"] >= 1
    assert all("TRA" == item["chain"] for item in report.metadata["significant_boxplots"])
    assert report.metadata["non_significant_boxplot_count"] >= 1
    assert any("TRB" == item["chain"] for item in report.metadata["non_significant_boxplots"])

    summary_path = report.output_base / "boxplot" / "significant_pvalue_all.csv"
    assert summary_path.exists()
    sig_df = pd.read_csv(summary_path)
    assert (sig_df["pvalue"] <= 0.05).all()

    png_paths = [report.output_base / item["png"] for item in report.metadata["significant_boxplots"]]
    assert png_paths
    assert all(path.exists() for path in png_paths)
    assert (report.output_base / "boxplot" / "significant").exists()
    assert (report.output_base / "boxplot" / "non_significant").exists()
    with zipfile.ZipFile(report.zip_path) as archive:
        names = archive.namelist()
    assert any(name.startswith("boxplot/significant/") and name.endswith(".png") for name in names)
    assert any(name.startswith("boxplot/non_significant/") and name.endswith(".png") for name in names)
    assert "data-tab=\"boxplots\"" in report.viewer_path.read_text(encoding="utf-8")
    assert "data-tab=\"significant-boxplots\"" in report.viewer_path.read_text(encoding="utf-8")
    assert "data-chain-filter=\"TRA\"" in report.viewer_path.read_text(encoding="utf-8")


@pytest.mark.skipif(not os.environ.get("REFERENCE_PIPELINE"), reason="Reference pipeline is not mounted")
def test_db_alignment_iedb_and_combined_ratios_match_original_script(tmp_path):
    reference_root = Path(os.environ["REFERENCE_PIPELINE"]).resolve()
    sys.path.insert(0, str(reference_root))
    script_path = reference_root / "04.DB" / "01.Alignment.py"
    spec = importlib.util.spec_from_file_location("reference_db_alignment", script_path)
    reference = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(reference)

    refs = tmp_path / "refs"
    refs.mkdir()
    pd.DataFrame([
        {"CDR3": "CASS", "Species": "HomoSapiens", "Epitope": "E1", "Epitope species": "Viral", "Reference": "vdj-1"},
        {"CDR3": "CASS", "Species": "Mus musculus", "Epitope": "E1", "Epitope species": "Viral", "Reference": "vdj-mouse"},
    ]).to_csv(refs / "vdjdb.csv", index=False)
    pd.DataFrame([
        {"CDR3.alpha.aa": "CQQQ", "CDR3.beta.aa": "", "Species": "Human", "Epitope.peptide": "E2", "Pathology": "Tumor", "PubMed.ID": "mc-1"},
        {"CDR3.alpha.aa": "CQQQ", "CDR3.beta.aa": "", "Species": "Mouse", "Epitope.peptide": "E2", "Pathology": "Tumor", "PubMed.ID": "mc-mouse"},
    ]).to_csv(refs / "McPAS-TCR.csv", index=False)
    pd.DataFrame([
        {"CDR3(pep)": "CASS", "chain": "TRA", "Pathology": "Viral", "Epitope.peptide": "E3", "Reference": "iedb-1", "Species": "Human", "source_db": "IEDB"},
        {"CDR3(pep)": "CASS", "chain": "TRA", "Pathology": "Other", "Epitope.peptide": "E4", "Reference": "other-db", "Species": "Human", "source_db": "Other"},
        {"CDR3(pep)": "CASS", "chain": "TRA", "Pathology": "Mouse", "Epitope.peptide": "E5", "Reference": "iedb-mouse", "Species": "Mouse", "source_db": "IEDB"},
        {"CDR3(pep)": "CASS", "chain": "TRB", "Pathology": "Other chain", "Epitope.peptide": "E6", "Reference": "iedb-trb", "Species": "Human", "source_db": "IEDB"},
    ]).to_csv(refs / "IEDB.csv", index=False)

    pep_path = tmp_path / "S1__TRA.csv"
    pd.DataFrame([
        {"CDR3(pep)": "CASS", "copy": 10},
        {"CDR3(pep)": "ASS", "copy": 5},
        {"CDR3(pep)": "CQQQ", "copy": 5},
    ]).to_csv(pep_path, index=False)

    reference.initialize_worker(refs, tmp_path / "reference-output")
    reference.CLASSIFY_BY_PATHOLOGY = True
    reference.use_Pathology = []
    expected = reference.alignment(pep_path)["overall_ratios"]

    service = DBAlignmentService(output_parent=tmp_path / "platform-results")
    service.vdjdb_path = refs / "vdjdb.csv"
    service.mcpas_path = refs / "McPAS-TCR.csv"
    service.iedb_path = refs / "IEDB.csv"
    report = service.generate_report(
        samples=[{
            "original_name": "S1", "display_name": "S1",
            "data_files": [{"filename": pep_path.name, "filepath": str(pep_path)}],
        }],
        selected_chains=["TRA"],
        field_mapping={"cdr3_column": "CDR3(pep)", "copy_column": "copy"},
    )

    actual = pd.read_csv(report.summary_path).iloc[0]
    for source, ratios in expected.items():
        assert actual[f"TRA_copy_ratio_{source}"] == pytest.approx(ratios["copy"], abs=1e-12)
        assert actual[f"TRA_unique_ratio_{source}"] == pytest.approx(ratios["unique"], abs=1e-12)
    assert report.metadata["available_reference_sources"] == ["VDJdb", "McPAS-TCR", "IEDB"]
    assert (report.output_base / "alignment" / "S1__TRA__IEDB.csv").is_file()


def test_db_report_preserves_saved_pvalues_and_raw_labels(tmp_path):
    import copy
    from html import unescape
    import re

    values = [0, 0.000000000000123456789, "0.01234567890123456789", None]
    metadata = {"significant_pvalues": [
        {"chain": "TRA", "source_label": "病毒 <分类>", "class_col": "类别",
         "group1": "01", "group2": "02", "param": "TRA_ratio_VDJdb", "pvalue": value}
        for value in values
    ]}
    saved = copy.deepcopy(metadata)
    report = DBAlignmentService(output_parent=tmp_path)._build_viewer_html(
        metadata=metadata,
        processed_preview=pd.DataFrame([{"sample": "001", "chain": "TRA"}]),
        ratio_preview=pd.DataFrame([{"sample": "001", "TRA_ratio_VDJdb": 0}]),
    )
    rows = re.findall(r'<tr data-chain="TRA" data-pathology="[^"]*">(.*?)</tr>', report, re.S)
    assert [unescape(re.findall(r"<td>(.*?)</td>", row, re.S)[-1]) for row in rows] == [
        str(value) if value is not None else "未记录" for value in values
    ]
    assert "01 与 02" in report
    assert ">001<" in report
    assert "病毒 &lt;分类&gt;" in report
    assert metadata == saved
