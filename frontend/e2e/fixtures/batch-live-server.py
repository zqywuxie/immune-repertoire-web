"""Native RQ batch acceptance with synthetic Profile and expression assets."""
from pathlib import Path
from flask import jsonify
from flask_app.app import create_app
from flask_app.models.database import db, Project, ProjectAsset, AnalysisJob
from flask_app.services.background_job_service import get_background_job_service

root = Path("/evidence/server")
root.mkdir(exist_ok=True)
app = create_app("internal")
project_id = "batch-live-project"
ids = [f"tpm_{group}_{i:03d}" for group in ("01", "02") for i in range(1, 7)]
originals = {}
with app.app_context():
    db.session.add(Project(id=project_id, name="组合进度合成项目"))
    db.session.flush()
    def asset(identifier, kind, name, content):
        path = root / name
        path.write_text(content, encoding="utf-8")
        originals[str(path)] = path.read_bytes()
        db.session.add(ProjectAsset(id=identifier, project_id=project_id, asset_type=kind,
            original_name=name, storage_path=str(path), size=path.stat().st_size,
            metadata_json={"asset_set": "Set1"}))
    asset("batch-profile", "profile", "Profile.csv", "sample,group,TRA_Shannon,TRB_Shannon\n" +
          "\n".join(f"{sample},{'01' if i<6 else '02'},{i+1},{12-i}" for i,sample in enumerate(ids))+"\n")
    genes = ["TP53","EGFR","CD3D","CD3E","CD4","CD8A","CD8B","LCK","ZAP70","LAT"] + [f"GENE{i}" for i in range(30)]
    asset("batch-expression", "transcriptome", "expression.csv", "gene_symbol,"+",".join(ids)+"\n"+
          "\n".join(gene+","+",".join(str(10+g+i*2+(g%3)*i) for i in range(12)) for g,gene in enumerate(genes))+"\n")
    db.session.commit()

@app.get("/__fixture/evidence")
def evidence():
    service = get_background_job_service()
    rows = AnalysisJob.query.filter_by(project_id=project_id).all()
    return jsonify(source_unchanged=all(Path(path).read_bytes()==content for path,content in originals.items()),
        jobs=[service.get_job(row.id) for row in rows])
app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
