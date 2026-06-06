"""Tests for DB alignment service behavior migrated from DB_pathology."""

from pathlib import Path
import sys
import zipfile
from importlib import import_module
from types import SimpleNamespace

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
    sys.modules.setdefault("umap", SimpleNamespace(UMAP=object))
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
