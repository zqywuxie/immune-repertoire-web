"""Persist validation against immutable uploaded asset versions, never raw paths alone."""
import hashlib
import os
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from flask import has_app_context, current_app
from flask_app.models.database import ProjectAsset, Project, db
from flask_app.services.user_scope import assert_owned

VALIDATOR_VERSION = 6
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

def cached_validation(path, kind, inspect, options=None):
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
            from flask_app.services.input_quality import LABELS
            return {"inputs": [{"kind": kind, "label": LABELS.get(kind, kind), "status": "pending",
                                "sample_count": 0, "sample_column": "", "duplicate_samples": [],
                                "missing_sample_count": 0, "missing_fields": {}}],
                    "warnings": [], "errors": ["输入文件正在后台校验，请稍后重新检查。"], "alignments": []}
    before = snapshot(path)
    expected = metadata.get("upload_snapshot")
    if expected and expected != before:
        # Restore/chown changes ctime. Verify the existing upload digest only
        # when its filesystem snapshot changes, then refresh that snapshot.
        digest = hashlib.sha256()
        with Path(path).open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if snapshot(path) != before:
            from flask_app.exceptions import ValidationError
            raise ValidationError(message="校验期间文件发生变化，请重新上传。")
        if digest.hexdigest() != metadata["content_version"]:
            from flask_app.exceptions import ValidationError
            raise ValidationError(message="已上传文件在平台外发生变化，请重新上传新版本。")
        metadata["upload_snapshot"] = before
    key = {"version": metadata["content_version"], "kind": kind, "validator": VALIDATOR_VERSION,
           "options": options or {}, **before}
    cached = metadata.get("validation") or {}
    if cached.get("key") == key and cached.get("status") == "valid":
        return deepcopy(cached["summary"])
    result = inspect()
    if snapshot(path) != before:
        from flask_app.exceptions import ValidationError
        raise ValidationError(message="校验期间文件发生变化，请重新上传。")
    statuses = [item.get("status") for item in result.get("inputs", [])]
    status = "invalid" if result.get("errors") else "needs_mapping" if "needs_mapping" in statuses else "valid"
    asset.metadata_json = {**metadata, "validation": {"status": status, "key": key, "checked_at": datetime.now(timezone.utc).isoformat(), "summary": result}}
    db.session.commit()
    return result

def synchronize_validation_jobs(project_id):
    from flask_app.models.database import AnalysisJob
    from flask_app.services.background_job_service import TERMINAL_STATUSES
    pairs = db.session.query(ProjectAsset, AnalysisJob).join(AnalysisJob,
        ProjectAsset.metadata_json['validation_job_id'].as_string() == AnalysisJob.id).filter(
            ProjectAsset.project_id == project_id, ProjectAsset.asset_type.in_(KINDS),
            ProjectAsset.metadata_json['validation']['status'].as_string() == 'pending',
            AnalysisJob.status.in_(TERMINAL_STATUSES)).all()
    for asset, job in pairs:
        metadata = dict(asset.metadata_json or {})
        report = job.result or {}
        if job.status == 'completed' and report.get('inputs'):
            status = 'invalid' if report.get('errors') else 'needs_mapping' if any(item.get('status') == 'needs_mapping' for item in report['inputs']) else 'valid'
            metadata['validation'] = {'status': status, 'summary': report}
        else:
            metadata['validation'] = {'status': 'failed', 'message': job.error or '校验任务已结束但未生成有效报告，请重新校验。'}
        asset.metadata_json = metadata
    if pairs:
        db.session.commit()


def schedule_uploaded_validation(assets):
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.persistent_queue import enqueue
    for asset in assets:
        if asset.asset_type not in KINDS or (asset.metadata_json or {}).get('validation', {}).get('status') != 'pending':
            continue
        project = db.session.get(Project, asset.project_id)
        service = None
        job_id = None
        try:
            service = get_background_job_service()
            if os.environ.get('JOB_QUEUE', '').lower() == 'redis':
                job = service.create_job(job_type='input_validation', module='input-validation', user_id=project.user_id,
                                         project_id=project.id, payload={'asset_id': asset.id}, stage='等待数据校验')
                job_id = job['id']
                asset.metadata_json = {**(asset.metadata_json or {}), 'validation_job_id': job_id}
                db.session.commit()
                enqueue(validate_asset_job, job_id, job_id)
            else:
                validate_uploaded_asset(asset)
        except Exception as error:
            db.session.rollback()
            message = f'文件已保存，校验未完成：{error}'
            asset.metadata_json = {**(asset.metadata_json or {}), 'validation': {'status': 'failed', 'message': message}}
            db.session.commit()
            if job_id:
                service.upsert_job(job_id, {'status': 'failed', 'stage': '校验失败', 'error': message})

def validate_uploaded_asset(asset):
    if (asset.metadata_json or {}).get('input_preparation'):
        from flask_app.services.input_preparation import validate_prepared_source
        return validate_prepared_source(asset)
    from flask_app.services.input_quality import inspect_input_quality
    kind = {'datapoint': 'profile', 'cibersort': 'deconvolution'}.get(asset.asset_type, asset.asset_type)
    arguments = {'profile': '', 'transcriptome': '', 'deconvolution': ''}
    if kind != 'pep': arguments[kind] = asset.storage_path
    return inspect_input_quality([asset.storage_path] if kind == 'pep' else [], arguments['profile'], arguments['transcriptome'], arguments['deconvolution'])

def validate_asset_job(job_id):
    from flask_app.app import app
    from flask_app.models.database import User
    from flask_login import login_user
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services.persistent_queue import claim
    with app.app_context(), app.test_request_context('/api/validation/worker'):
        service = get_background_job_service()
        if not claim(job_id): return
        job = service.get_job(job_id)
        asset = None
        try:
            owner = db.session.get(User, job.get('user_id')) if job.get('user_id') else None
            if app.config.get('REQUIRE_LOGIN') and (owner is None or not owner.is_active):
                raise ValueError('任务账号不存在或已停用')
            if owner: login_user(owner)
            asset = db.session.get(ProjectAsset, job['payload']['asset_id'])
            if asset is None: raise ValueError('校验文件已删除')
            from flask import g
            g.validation_asset_id = asset.id
            summary = validate_uploaded_asset(asset)
            service.upsert_job(job_id, {'status': 'failed' if summary.get('errors') else 'completed', 'progress': 100,
                                        'stage': '校验未通过' if summary.get('errors') else '校验完成', 'result': summary})
        except Exception as error:
            db.session.rollback()
            message = f'数据校验失败：{error}'
            if asset is not None:
                asset.metadata_json = {**(asset.metadata_json or {}), 'validation': {'status': 'failed', 'message': message}}
                db.session.commit()
            service.upsert_job(job_id, {'status': 'failed', 'stage': '校验失败', 'error': message})
            raise
