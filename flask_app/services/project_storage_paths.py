"""Shared Linux-safe project directory and atomic result allocation."""
import re
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from flask import current_app, has_app_context
from flask_app.exceptions import ValidationError

def safe_segment(value):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff-]{0,100}", value):
        raise ValidationError(message="目录标识不合法")
    return value

def user_segment(user):
    # Existing unsafe names retain a deterministic isolated ID directory.
    try:
        return safe_segment(user.username)
    except ValidationError:
        return "user_" + str(user.id)

def bounded_path(root, *segments):
    root = Path(root).resolve()
    candidate = root.joinpath(*(safe_segment(value) for value in segments)).resolve()
    if root not in candidate.parents:
        raise ValidationError(message="目录超出项目存储范围")
    return candidate

def project_data_dir(project, fallback_root):
    root = Path(current_app.config.get("PROJECT_DATA_ROOT") or fallback_root)
    if project.user_id:
        from flask_app.models.database import User, db
        owner = db.session.get(User, project.user_id)
        if owner is None:
            raise ValidationError(message="项目所属账号不存在")
        segment = user_segment(owner)
    else:
        segment = "legacy"
    return bounded_path(root, segment, project.id)

def project_results_dir(project, fallback_root):
    from flask_app.models.database import User, db
    owner = db.session.get(User, project.user_id) if project.user_id else None
    root = current_app.config.get("RESULTS_FOLDER") or fallback_root
    return bounded_path(root, user_segment(owner) if owner else "legacy", project.id)

def allocate_result_dir(parent, analysis_type):
    parent = Path(parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    timezone = current_app.config.get("ANALYSIS_TIMEZONE", "Asia/Shanghai") if has_app_context() else "Asia/Shanghai"
    prefix = safe_segment(analysis_type) + "_" + datetime.now(ZoneInfo(timezone)).strftime("%Y%m%d_%H%M%S") + "__" + uuid.uuid4().hex[:8]
    while True:
        candidate = bounded_path(parent, prefix)
        try:
            candidate.mkdir()
            return candidate.name, candidate
        except FileExistsError:
            prefix = prefix.split("__", 1)[0] + "__" + uuid.uuid4().hex[:8]


def script_output_parent(task_id, fallback_root, app_context_app=None):
    from contextlib import nullcontext
    from flask_app.models.database import Project, db
    from flask_app.services.background_job_service import get_background_job_service
    context = nullcontext() if has_app_context() else app_context_app.app_context() if app_context_app else nullcontext()
    with context:
        if not has_app_context():
            return Path(fallback_root)
        from flask_app.services.script_hub_job_service import get_script_hub_job_service
        job = get_script_hub_job_service().get_job(task_id)
        if not job or not job.get("project_id"):
            return Path(fallback_root)
        project = db.session.get(Project, job["project_id"])
        if project is None or project.user_id != job.get("user_id"):
            raise ValidationError(message="任务与项目归属不一致")
        parent = project_results_dir(project, fallback_root)
        parent.mkdir(parents=True, exist_ok=True)
        get_background_job_service().upsert_job(task_id, {"output_parent": str(parent)})
        return parent


def request_project():
    from flask import g, request, has_request_context
    if not has_request_context(): return None
    data = request.get_json(silent=True) or {}
    project_id = getattr(g, "analysis_project_id", None) or data.get("project_id") or data.get("_project_id")
    if not project_id: return None
    from flask_app.models.database import Project, db
    from flask_app.services.user_scope import assert_owned
    project = db.session.get(Project, str(project_id))
    assert_owned(project, "项目")
    return project

def allocate_report_dir(fallback_parent, analysis_type):
    project = request_project()
    parent = project_results_dir(project, fallback_parent) if project else fallback_parent
    job_id, directory = allocate_result_dir(parent, analysis_type)
    if project:
        from flask import g
        roots = getattr(g, "analysis_result_roots", {})
        roots[job_id] = directory
        g.analysis_result_roots = roots
    return job_id, directory

def register_report(project, analysis_type, report, viewer_url, zip_url):
    if project is None: return None
    from flask_app.services.project_asset_service import get_project_asset_service
    return get_project_asset_service(Path(current_app.root_path) / "data" / "projects").register_analysis_result(
        project, analysis_type=analysis_type, job_id=report.job_id,
        output_base=str(report.output_base), viewer_url=viewer_url, zip_url=zip_url,
        metadata=report.metadata or {})


def register_reused_result(project_id, analysis_type, task_id, result):
    """Record each reuse independently without copying large scientific outputs."""
    import json
    from zipfile import ZipFile, ZIP_DEFLATED
    from flask_app.models.database import Project, db
    from flask_app.services.user_scope import assert_owned
    from flask_app.services.project_asset_service import get_project_asset_service
    project = db.session.get(Project, project_id)
    assert_owned(project, "项目")
    _, directory = allocate_result_dir(project_results_dir(project, current_app.config["RESULTS_FOLDER"]), analysis_type)
    (directory / "reference.json").write_text(json.dumps({"task_id": task_id, "source_result": result}, ensure_ascii=False, indent=2), encoding="utf-8")
    with ZipFile(directory / "results.zip", "w", ZIP_DEFLATED) as archive:
        archive.write(directory / "reference.json", "reference.json")
    asset = get_project_asset_service(Path(current_app.root_path) / "data" / "projects").register_analysis_result(
        project, analysis_type=analysis_type, job_id=task_id, output_base=str(directory),
        viewer_url=result.get("viewer_url", ""), zip_url=result.get("zip_url", ""),
        metadata={"reused_result": True, "source_result": result})
    return {**result, "source_result": dict(result), "output_base": str(directory),
            "result_files": (asset.metadata_json or {}).get("result_files", []), "reused_result": True}
