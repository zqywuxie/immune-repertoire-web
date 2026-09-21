"""Synthetic PEP calculation -> registered artifact -> real UMAP -> download."""
from pathlib import Path
import numpy as np
import pandas as pd
from flask import Flask


def test_real_pep_output_reused_by_umapin_and_downloaded(tmp_path, monkeypatch):
    from flask_app.models.database import db, Project, ProjectAsset, AnalysisJob
    from flask_app.routes.api_script_hub import script_hub_bp
    from flask_app.services.pep_analysis_service import PepAnalysisService
    from flask_app.services.umapin_service import UmapinService
    from flask_app.services.analysis_artifacts import capture_input_lineage, scoped_pep_candidates, resolve_upstream_input, revalidate_job_upstream
    # No legacy Mongo records in this isolated synthetic project. SQL and manifest discovery remain real.
    monkeypatch.setattr("flask_app.services.mongo_service.get_cached_usage", lambda project: [])
    app = Flask(__name__)
    results = tmp_path / "results"
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False, RESULTS_FOLDER=str(results))
    db.init_app(app)
    app.register_blueprint(script_hub_bp)
    pep = tmp_path / "pep"
    pep.mkdir()
    samples = [f"{i:03d}" for i in range(8)]
    profile = tmp_path / "profile.csv"
    pd.DataFrame({"sample": samples, "group": ["A"]*4+["B"]*4}).to_csv(profile,index=False)
    for i, sample in enumerate(samples):
        pd.DataFrame({"CDR3(pep)": ["CASSA", "CASSB", "CASSC", "CASSD"], "V": ["TRBV1", "TRBV2", "TRBV3", "TRBV4"], "J": ["TRBJ1"]*4, "copy": [i+1, 10-i, (i+2)**2, 5]}).to_csv(pep/f"{sample}__TRB.csv",index=False)
    with app.app_context():
        db.create_all()
        try:
            db.session.add(Project(id="synthetic",name="合成上下游验收"))
            db.session.flush()
            for kind,path in [("profile",profile),("pep",pep)]:
                db.session.add(ProjectAsset(id=kind,project_id="synthetic",asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={"asset_set":"Set2"}))
            db.session.flush()
            lineage=capture_input_lineage("synthetic",[{"path":str(profile)},{"path":str(pep)}],"Set2")
            upstream=PepAnalysisService(output_parent=results/"shared"/"script_hub").generate_report(pep_data_dir=str(pep),profile_path=str(profile),group_fields=["group"],selected_chains=["TRB"],optional_steps=set(),project_id="synthetic")
            db.session.add(AnalysisJob(id="source-task",job_type="script_hub",module="pep-analysis",status="completed",project_id="synthetic",payload=lineage,result={"output_base":str(upstream.output_base)}))
            db.session.add(ProjectAsset(id="registered-output",project_id="synthetic",asset_type="cached_usage",storage_path=str(upstream.output_base),original_name="共享结果",size=0,metadata_json={"source_job_id":"source-task","pep_output_base":str(upstream.output_base),"profile_path":str(profile),"asset_set":"Set2"}))
            db.session.commit()
            candidates=scoped_pep_candidates("synthetic","Set2","umapin")
            assert any(Path(item["path"]).name=="df_VJ_all.csv" for item in candidates), {"candidates":candidates,"files":[str(p.relative_to(upstream.output_base)) for p in upstream.output_base.rglob("*.csv")]}
            raw_directory=next(item for item in candidates if Path(item["path"])==upstream.output_base/"usage"/"1VJusage")
            assert raw_directory["status"]=="unavailable" and "分组列" in raw_directory["reason"]
            candidate=next(item for item in candidates if Path(item["path"]).name=="df_VJ_all.csv")
            assert candidate["status"]=="available",candidate
            assert candidate["job_id"]=="source-task"
            assert not scoped_pep_candidates("synthetic","Set1","umapin")
            data={"project_id":"synthetic","asset_set":"Set2","upstream_artifact_id":candidate["artifact_id"]}
            ref=resolve_upstream_input("umapin",data)
            revalidate_job_upstream({"payload":{"upstream_input":ref}})
            inspection=app.test_client().post("/api/script-hub/umapin/inspect",json=data)
            assert inspection.status_code==200,inspection.json
            table=pd.read_csv(data["data_path"])
            assert set(table["Category"])=={"A","B"} and len(table)==8
            assert set(table["sample"]) == {f"{sample}__TRB.csv" for sample in samples}
            features=list(table.columns[2:])
            # Copy-weighted V/J frequencies retain their numerical definition.
            np.testing.assert_allclose(table[features].sum(axis=1),np.ones(8),atol=1e-8)
            downstream=UmapinService(output_parent=results/"shared"/"script_hub").generate_report(data_path=data["data_path"],param_begin=features[0],param_over=features[-1],n_neighbors=3,n_epochs=30)
            coords=pd.read_csv(downstream.csv_paths[0])
            assert len(coords)==8 and np.isfinite(coords[["UMAP1","UMAP2"]].to_numpy()).all()
            assert set(coords["Category"])=={"A","B"}
            assert all(Path(path).stat().st_size for path in downstream.png_paths+downstream.csv_paths)
            download=app.test_client().get(f"/api/script-hub/results/{downstream.job_id}/umapin_coordinates.csv")
            assert download.status_code==200
            assert download.data==Path(downstream.csv_paths[0]).read_bytes()
        finally:
            db.session.remove()
            db.drop_all()
