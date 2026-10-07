"""Isolated synthetic table fixture served through the real jobs table API."""
import csv
import json
import tempfile
from pathlib import Path
from flask import Flask, send_file
from flask_app.models.database import db
from flask_app.routes.api_jobs import jobs_bp
from flask_app.services.background_job_service import get_background_job_service

root = Path(tempfile.mkdtemp(prefix="immune-table-fixture-"))
path = root / "科学数值.csv"
with path.open("w", encoding="utf-8-sig", newline="") as stream:
    writer = csv.writer(stream)
    writer.writerow(["样本", "组别", "p值", "计数"])
    for index in range(1, 4097):
        writer.writerow([f"{index:05}", "研究组" if index % 2 else "对照组",
                         "1e-1000" if index == 4096 else f"{index}e-9",
                         str(1790983155444449151 + index)])
app = Flask(__name__)
app.config.update(TESTING=True, REQUIRE_LOGIN=False, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
                  SQLALCHEMY_TRACK_MODIFICATIONS=False)
db.init_app(app)
app.register_blueprint(jobs_bp)

@app.get("/api/script-hub/results/table-live/科学数值.csv")
def result_file():
    return send_file(path, as_attachment=True, download_name=path.name)

with app.app_context():
    db.create_all()
    service = get_background_job_service()
    job = service.create_job(job_type="script_hub", module="profile", user_id=7)
    service.complete_job(job["job_id"], {"csv_urls": ["/api/script-hub/results/table-live/科学数值.csv"]})
    Path("/evidence/server-ready.json").write_text(json.dumps({"job_id":job["job_id"],"url":"/api/script-hub/results/table-live/科学数值.csv","rows":4096}),encoding="utf-8")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
