"""Isolated real source/task APIs with synthetic saved artifacts; no computation."""
import tempfile
from pathlib import Path
from flask_app.config import TestingConfig
from flask_app.app import create_app
from flask_app.models.database import db, Project, ProjectAsset, AnalysisJob
from flask_app.services.pathway_artifacts import GO_BP_TERMS

root = Path(tempfile.mkdtemp(prefix="codex-source-selection-"))
TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(root / "jobs.sqlite")
TestingConfig.ALLOWED_BASE_PATHS = [str(root)]
TestingConfig.RESULTS_FOLDER = root / "results"
TestingConfig.PROJECT_DATA_ROOT = str(root / "inputs")
TestingConfig.INTERNAL_MODE = True
app = create_app("testing")
app.config["ALLOWED_BASE_PATHS"] = [str(root)]
project_id = "source-selection-project"
ids = [f"tpm_{group}_{i:03d}" for group in ("01", "02") for i in range(1, 4)]
with app.app_context():
    db.session.add(Project(id=project_id, name="来源选择合成项目"))
    db.session.flush()
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    def asset(identifier, kind, name, content):
        path = inputs / name
        path.write_text(content, encoding="utf-8")
        row = ProjectAsset(id=identifier, project_id=project_id, asset_type=kind, original_name=name,
            storage_path=str(path), size=path.stat().st_size, metadata_json={"asset_set":"Set1"})
        db.session.add(row)
        return path
    profile = asset("profile-input", "profile", "profile.csv", "sample,group,IGHA1\n" + "\n".join(f"{sample},{'01' if i < 3 else '02'},{i+1}" for i,sample in enumerate(ids)) + "\n")
    expression = asset("expression-input", "transcriptome", "expression.csv", "gene_symbol," + ",".join(ids) + "\n" + "\n".join(gene+","+",".join(str(10+i+g) for i in range(6)) for g,gene in enumerate(["TP53","EGFR","CD3D","CD3E","CD4","CD8A","CD8B","LCK","ZAP70","LAT"])) + "\n")
    deconv = asset("deconv-input", "deconvolution", "deconv.csv", "Mixture,T cells,B cells\n" + "\n".join(f"{sample},{0.2+i*.02},{0.8-i*.02}" for i,sample in enumerate(ids)) + "\n")
    for i,sample in enumerate(ids):
        asset("pep-input-"+str(i), "pep", sample+"__TRB.csv", "CDR3(pep),V,J,copy\nCASSLGQETQYF,TRBV1,TRBJ1-1,3\nCASSIRSSYEQYF,TRBV2,TRBJ2-1,2\n")
    stat = expression.stat()
    lineage = [{"asset_id":"expression-input","path":str(expression),"size":stat.st_size,"mtime_ns":stat.st_mtime_ns}]
    def job(identifier, module, result, refs=None, status="completed", dataset="Set1"):
        row = AnalysisJob(id=identifier, job_type="script_hub", module=module, project_id=project_id,
            status=status, progress=100 if status=="completed" else 35, stage="已完成" if status=="completed" else "失败",
            payload={"asset_set":dataset,"_task_name":identifier,"source_assets":refs or lineage},
            result=result)
        db.session.add(row)
        return row
    for index,status in enumerate(["completed","completed","failed"],1):
        identifier="差异来源-"+str(index)
        output=root/"results"/identifier
        (output/"DEG").mkdir(parents=True)
        (output/"DEG"/"DEG_02_vs_01.csv").write_text("gene_symbol,logFC,P.Value,adj.P.Val\nTP53,0,0.05,0.08\n",encoding="utf-8")
        job(identifier,"volcano",{"output_base":str(output),"metadata":{"input_mode":"expression","output_name":"同名组间比较","comparisons":[{"group1":"02","group2":"01"}],"sample_count":6,"selected_expression_samples":ids,"significance_column":"significant_fdr","pvalue_threshold":0.05,"logfc_cutoff":0}},status=status)
    for index,status in enumerate(["completed","completed","failed"],1):
        identifier="通路来源-"+str(index)
        output=root/"results"/identifier
        relative="enrichment_results/GO/BP/02_vs_01/GSEA/GSEA_GO_BP_full.csv"
        table=output/relative
        table.parent.mkdir(parents=True)
        table.write_text("ID,Description,setSize,NES,pvalue,p.adjust,qvalue\n"+"\n".join(f"{term},synthetic,20,1.2,0.8,0.9,0.9" for term in GO_BP_TERMS)+"\n",encoding="utf-8")
        job(identifier,"go-kegg-enrichment",{"output_base":str(output),"metadata":{"comparisons":[{"group1":"02","group2":"01"}],"full_go_gsea_tables":[relative]}},status=status)
    for index in (1,2):
        identifier="共享来源-"+str(index)
        output=root/"results"/identifier
        output.mkdir(parents=True)
        table=output/"df_1VJusage_all.csv"
        table.write_text("sample,Category,V1,V2\n"+"\n".join(f"{sample},{'01' if i<3 else '02'},0.4,0.6" for i,sample in enumerate(ids))+"\n",encoding="utf-8")
        job(identifier,"pep-analysis",{"output_base":str(output)})
        db.session.add(ProjectAsset(id="cache-"+str(index),project_id=project_id,asset_type="cached_usage",
            original_name=table.name,storage_path=str(table),size=table.stat().st_size,
            metadata_json={"source_module":"pep-analysis","source_job_id":identifier,"asset_set":"Set1","output_base":str(output),"umapin_data_path":str(table),"profile_path":str(profile),"chains":["TRB"],"group_fields":["group"]}))
    db.session.commit()
