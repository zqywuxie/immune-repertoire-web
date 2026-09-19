"""Persist legacy JSON/chart analyses as project result assets before completion."""
import base64
import csv
import html
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from flask import current_app
from flask_login import login_user
from flask_app.models.database import Project, User, ProjectAsset, db
from flask_app.services.project_storage_paths import allocate_result_dir, project_results_dir

def persist_generic_result(job, result):
    if not job.project_id or job.module not in {"analysis.execute-unified", "charts.combined"}:
        return result
    project = db.session.get(Project, job.project_id)
    if project is None or project.user_id != job.user_id:
        raise ValueError("任务与项目归属不一致")
    owner = db.session.get(User, job.user_id) if job.user_id else None
    if current_app.config.get("REQUIRE_LOGIN") and (owner is None or not owner.is_active):
        raise ValueError("任务账号不存在或已停用")
    existing = ProjectAsset.query.filter_by(project_id=project.id, asset_type="processed_result").all()
    asset = next((item for item in existing if (item.metadata_json or {}).get("job_id") == job.id), None)
    result = dict(result or {})
    if asset is None:
        kind = "sequencing_reads" if job.module == "analysis.execute-unified" else "combined_charts"
        _, directory = allocate_result_dir(project_results_dir(project, current_app.config["RESULTS_FOLDER"]), kind)
        # Save the actual directory while still running, so failures remain traceable.
        job.payload = {**(job.payload or {}), "output_dir": str(directory)}
        db.session.commit()
        (directory / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        response = result.get("data", result)
        content = response.get("results", {})
        previews = []
        for index, chart in enumerate(content.get("charts", []), 1):
            encoded = chart.get("image") or chart.get("base64")
            if not isinstance(encoded, str): continue
            encoded = encoded.split(",", 1)[1] if encoded.startswith("data:image/") else encoded
            data = base64.b64decode(encoded, validate=True)
            name = f"chart_{index}.png"
            (directory / name).write_bytes(data)
            previews.append('<figure><figcaption>' + html.escape(str(chart.get("title", "分析图表"))) + '</figcaption><img style="max-width:100%" src="data:image/png;base64,' + encoded + '"></figure>')
        for index, table in enumerate(content.get("tables", []), 1):
            rows = table.get("data", [])
            headers = table.get("headers") or list(dict.fromkeys(key for row in rows for key in row))
            with (directory / f"table_{index}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.writer(stream); writer.writerow(headers)
                writer.writerows([row.get(key, "") for key in headers] for row in rows)
        if not previews:
            previews = ["<pre>" + html.escape(json.dumps(result, ensure_ascii=False, indent=2)) + "</pre>"]
        (directory / "index.html").write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>分析结果</title><body><h1>分析结果</h1>' + "".join(previews) + '</body></html>', encoding="utf-8")
        with ZipFile(directory / "results.zip", "w", ZIP_DEFLATED) as archive:
            for file in sorted(directory.iterdir()):
                if file.name != "results.zip": archive.write(file, file.name)
        from flask_app.services.project_asset_service import get_project_asset_service
        with current_app.test_request_context("/api/jobs/worker"):
            if owner: login_user(owner)
            asset = get_project_asset_service(Path(current_app.root_path) / "data" / "projects").register_analysis_result(
                project, analysis_type=kind, job_id=job.id, output_base=str(directory), metadata={"module": job.module})
    result.update(output_base=asset.storage_path, result_files=(asset.metadata_json or {}).get("result_files", []),
                  viewer_url=f"/api/assets/{asset.id}/preview", zip_url=f"/api/assets/{asset.id}/download")
    return result
