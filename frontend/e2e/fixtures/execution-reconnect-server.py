"""Real Profile computation and task APIs for isolated reconnection acceptance."""
from pathlib import Path
from flask import jsonify
from flask_app.config import TestingConfig

root = Path("/evidence/server")
root.mkdir(exist_ok=True)
TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(root / "jobs.sqlite")
TestingConfig.INTERNAL_MODE = True
TestingConfig.ALLOWED_BASE_PATHS = [str(root)]
TestingConfig.RESULTS_FOLDER = root / "results"
TestingConfig.UPLOAD_FOLDER = root / "uploads"
TestingConfig.USER_DATA_ROOT = root / "users"
TestingConfig.PROJECT_DATA_ROOT = str(root / "inputs")
from flask_app.app import create_app
from flask_app.models.database import Project, ProjectAsset, db

app = create_app("testing")
project_id = "execution-reconnect-project"
source = root / "Profile.csv"
source.write_text("sample,group,TRA_Shannon,TRB_Shannon\n" + "\n".join(
    f"{i:03d},{'01' if i <= 6 else '02'},{i},{13-i}" for i in range(1, 13)
) + "\n", encoding="utf-8")
original = source.read_bytes()
with app.app_context():
    db.session.add(Project(id=project_id, name="断线恢复合成项目"))
    db.session.flush()
    db.session.add(ProjectAsset(id="reconnect-profile", project_id=project_id,
        asset_type="profile", original_name=source.name, storage_path=str(source),
        size=source.stat().st_size, metadata_json={"asset_set": "Set1"}))
    db.session.commit()

@app.get("/__fixture/evidence")
def evidence():
    from flask_app.models.database import AnalysisJob
    from flask_app.services.script_hub_job_service import get_script_hub_job_service
    service = get_script_hub_job_service()
    ids = [row.id for row in AnalysisJob.query.filter_by(project_id=project_id, job_type="script_hub").all()]
    return jsonify(source_unchanged=source.read_bytes() == original,
                   jobs=[service.get_job(identifier) for identifier in ids])

app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
