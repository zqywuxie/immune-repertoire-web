"""Persist validation against immutable uploaded asset versions, never raw paths alone."""
import hashlib
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from flask import has_app_context, current_app
from flask_app.models.database import ProjectAsset, Project, db
from flask_app.services.user_scope import assert_owned

VALIDATOR_VERSION = 2
KINDS = {"pep", "profile", "datapoint", "transcriptome", "deconvolution", "cibersort"}

def snapshot(path):
    info = Path(path).stat()
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}

def managed_asset(path):
    if not has_app_context() or "sqlalchemy" not in current_app.extensions:
        return None
    asset = ProjectAsset.query.filter_by(storage_path=str(Path(path).resolve())).first()
    if asset is None or not (asset.metadata_json or {}).get("content_version"):
        return None
    assert_owned(db.session.get(Project, asset.project_id), "项目")
    return asset

def cached_validation(path, kind, inspect):
    asset = managed_asset(path)
    if asset is None:
        return inspect()
    metadata = dict(asset.metadata_json or {})
    from flask import g, has_request_context
    validation_job = metadata.get("validation_job_id")
    if validation_job and not (has_request_context() and getattr(g, "validation_asset_id", None) == asset.id):
        from flask_app.models.database import AnalysisJob
        queued = db.session.get(AnalysisJob, validation_job)
        if queued and queued.status in {"queued", "running"}:
            return {"inputs": [{"kind": kind, "status": "pending", "sample_count": 0}],
                    "warnings": [], "errors": ["输入文件正在后台校验，请稍后重新检查。"], "alignments": []}
    before = snapshot(path)
    key = {"version": metadata["content_version"], "kind": kind, "validator": VALIDATOR_VERSION, **before}
    cached = metadata.get("validation") or {}
    if cached.get("key") == key and cached.get("status") == "valid":
        return deepcopy(cached["summary"])
    result = inspect()
    if snapshot(path) != before:
        from flask_app.exceptions import ValidationError
        raise ValidationError(message="校验期间文件发生变化，请重新上传。")
    # A changed immutable upload is never silently trusted as the same version.
    expected = metadata.get("upload_snapshot")
    if expected and expected != before:
        from flask_app.exceptions import ValidationError
        raise ValidationError(message="已上传文件在平台外发生变化，请重新上传新版本。")
    statuses = [item.get("status") for item in result.get("inputs", [])]
    status = "invalid" if result.get("errors") else "needs_mapping" if "needs_mapping" in statuses else "valid"
    asset.metadata_json = {**metadata, "validation": {"status": status, "key": key, "checked_at": datetime.now(timezone.utc).isoformat(), "summary": result}}
    db.session.commit()
    return result

def schedule_uploaded_validation(assets):
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.persistent_queue import enqueue
    for asset in assets:
        if asset.asset_type not in KINDS:
            continue
        project = db.session.get(Project, asset.project_id)
        if os.environ.get("JOB_QUEUE", "").lower() == "redis":
            service = get_background_job_service()
            job = service.create_job(job_type="input_validation", module="input-validation", user_id=project.user_id,
                                     project_id=project.id, payload={"asset_id": asset.id}, stage="等待数据校验")
            asset.metadata_json = {**(asset.metadata_json or {}), "validation_job_id": job["id"]}
            db.session.commit()
            try:
                enqueue(validate_asset_job, job["id"], job["id"])
            except Exception:
                asset.metadata_json = {**(asset.metadata_json or {}), "validation": {"status": "pending", "message": "校验入队失败，选择数据时将重新校验。"}}
                db.session.commit()
        else:
            validate_uploaded_asset(asset)

def validate_uploaded_asset(asset):
    from flask_app.services.input_quality import inspect_input_quality
    kind = {"datapoint": "profile", "cibersort": "deconvolution"}.get(asset.asset_type, asset.asset_type)
    arguments = {"profile": "", "transcriptome": "", "deconvolution": ""}
    if kind != "pep": arguments[kind] = asset.storage_path
    return inspect_input_quality([asset.storage_path] if kind == "pep" else [], arguments["profile"], arguments["transcriptome"], arguments["deconvolution"])

def validate_asset_job(job_id):
    from flask_app.app import app
    from flask_app.models.database import User
    from flask_login import login_user
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.persistent_queue import claim
    with app.app_context(), app.test_request_context("/api/validation/worker"):
        service = get_background_job_service()
        if not claim(job_id): return
        job = service.get_job(job_id)
        owner = db.session.get(User, job.get("user_id")) if job.get("user_id") else None
        if app.config.get("REQUIRE_LOGIN") and (owner is None or not owner.is_active):
            raise ValueError("任务账号不存在或已停用")
        if owner: login_user(owner)
        asset = db.session.get(ProjectAsset, job["payload"]["asset_id"])
        if asset is None: raise ValueError("校验文件已删除")
        from flask import g
        g.validation_asset_id = asset.id
        summary = validate_uploaded_asset(asset)
        service.upsert_job(job_id, {"status": "failed" if summary.get("errors") else "completed", "progress": 100,
                                   "stage": "校验未通过" if summary.get("errors") else "校验完成", "result": summary})
