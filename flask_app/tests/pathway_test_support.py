import pandas as pd

from flask_app.models.database import AnalysisJob, Project, ProjectAsset, db
from flask_app.services.pathway_artifacts import GO_BP_TERMS


def source_fixture(application, tmp_path):
    application.config["REQUIRE_LOGIN"] = False
    db.session.add(Project(id="pathway-project", name="pathway test"))
    db.session.flush()
    expression = tmp_path / "expression.csv"
    expression.write_text("Gene,A1,A2,B1,B2\nTP53,1,2,3,4\n")
    asset = ProjectAsset(
        project_id="pathway-project",
        asset_type="transcriptome",
        storage_path=str(expression),
        original_name=expression.name,
        size=expression.stat().st_size,
        metadata_json={"asset_set": "Set1"},
    )
    db.session.add(asset)
    db.session.flush()
    relative = "enrichment_results/GO/BP/A_vs_B/GSEA/GSEA_GO_BP_full.csv"
    output = tmp_path / "results"
    table = output / relative
    table.parent.mkdir(parents=True)
    frame = pd.DataFrame({
        "ID": GO_BP_TERMS,
        "Description": ["pathway"] * 10,
        "setSize": [20] * 10,
        "NES": [1.2] * 10,
        "pvalue": [0.8] * 10,
        "p.adjust": [0.9] * 10,
        "qvalue": [float("nan")] * 10,
    })
    frame.to_csv(table, index=False)
    stat = expression.stat()
    job = AnalysisJob(
        id="go-source",
        job_type="script_hub",
        module="go-kegg-enrichment",
        project_id="pathway-project",
        status="completed",
        payload={
            "asset_set": "Set1",
            "source_assets": [{
                "asset_id": asset.id,
                "path": str(expression),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }],
        },
        result={
            "output_base": str(output),
            "metadata": {
                "comparisons": [{"group1": "A", "group2": "B"}],
                "full_go_gsea_tables": [relative],
            },
        },
    )
    db.session.add(job)
    db.session.commit()
    data = {
        "project_id": "pathway-project",
        "asset_set": "Set1",
        "upstream_artifact_id": "go-source:go-bp:0",
        "comparison": ["A", "B"],
    }
    return data, job, table, frame, expression
