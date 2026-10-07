"""Generate database reports with the real service and synthetic references only."""
import json
import tempfile
from pathlib import Path
import pandas as pd
from flask_app.services.db_alignment_service import DBAlignmentService

out = Path("/evidence")
root = Path(tempfile.mkdtemp(prefix="codex-db-report-"))
refs = root / "refs"
refs.mkdir()
pd.DataFrame([
    {"CDR3": "CASS", "Species": "HomoSapiens", "Epitope": "E1", "Epitope species": "病毒分类", "Reference": "fixture-1"},
    {"CDR3": "CTTT", "Species": "HomoSapiens", "Epitope": "E2", "Epitope species": "肿瘤分类", "Reference": "fixture-2"},
]).to_csv(refs / "vdjdb.csv", index=False)
pd.DataFrame([
    {"CDR3.alpha.aa": "CASS", "CDR3.beta.aa": "", "Species": "Human", "Epitope.peptide": "E1", "Pathology": "病毒分类", "PubMed.ID": "fixture-1"},
    {"CDR3.alpha.aa": "", "CDR3.beta.aa": "CTTT", "Species": "Human", "Epitope.peptide": "E2", "Pathology": "肿瘤分类", "PubMed.ID": "fixture-2"},
]).to_csv(refs / "McPAS-TCR.csv", index=False)
samples, rows = [], []
for n in range(1, 11):
    sample = f"{n:03d}"
    rows.append({"Sample": sample, "类别": "01" if n <= 5 else "02"})
    files = []
    for chain, cdr3 in (("TRA", "CASS" if n <= 5 else "CQQQ"), ("TRB", "CTTT")):
        file = root / f"{sample}__{chain}.csv"
        pd.DataFrame([{"CDR3(pep)": cdr3, "copy": 10}]).to_csv(file, index=False)
        files.append({"filename": file.name, "filepath": str(file)})
    samples.append({"original_name": sample, "display_name": sample, "data_files": files})
profile = root / "合成样本指标.csv"
pd.DataFrame(rows).to_csv(profile, index=False)
service = DBAlignmentService(output_parent=out / "db-generated")
service.vdjdb_path = refs / "vdjdb.csv"
service.mcpas_path = refs / "McPAS-TCR.csv"
service.iedb_path = refs / "no-iedb.csv"
report = service.generate_report(
    samples=samples, selected_chains=["TRA", "TRB"],
    field_mapping={"cdr3_column": "CDR3(pep)", "copy_column": "copy"},
    profile_path=str(profile), categories=["类别"], category_mode="single",
    contained_pathology=True, output_name="数据库比对合成验收",
)
assert report.metadata["sample_count"] == 10
assert report.metadata["pathologies"] == ["病毒分类", "肿瘤分类"]
assert report.metadata["significant_boxplot_count"] > 0
assert report.metadata["non_significant_boxplot_count"] > 0
assert all(p["chain"] == "TRA" for p in report.metadata["significant_boxplots"])
# A second real run with no raw CDR3 matches verifies empty results separately.
file = root / "011__TRA.csv"
pd.DataFrame([{"CDR3(pep)": "CXXX", "copy": 10}]).to_csv(file, index=False)
empty = service.generate_report(
    samples=[{"original_name": "011", "display_name": "011", "data_files": [{"filename": file.name, "filepath": str(file)}]}],
    selected_chains=["TRA"], field_mapping={"cdr3_column": "CDR3(pep)", "copy_column": "copy"},
    output_name="无匹配结果合成验收",
)
assert empty.metadata["boxplot_count"] == 0
(out / "artifact-context.json").write_text(json.dumps({
    "viewer": str(report.viewer_path), "emptyViewer": str(empty.viewer_path),
    "metadata": str(report.metadata_path), "zip": str(report.zip_path),
    "pvalueTexts": [str(r["pvalue"]) for r in report.metadata["significant_pvalues"][:200]],
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"job": report.job_id, "output": str(report.output_base), "samples": 10,
    "plots": report.metadata["boxplot_count"], "significant": report.metadata["significant_boxplot_count"],
    "emptyJob": empty.job_id}, ensure_ascii=False))
