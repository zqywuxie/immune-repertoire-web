"""Actual read-only Flask task endpoints; synthetic snapshots for navigation checks."""
import tempfile
from pathlib import Path
from flask_app.config import TestingConfig
from flask_app.app import create_app
from flask_app.models.database import db, Project
from flask_app.services.background_job_service import get_background_job_service

fixture_root = Path(tempfile.mkdtemp(prefix="codex-job-navigation-"))
TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(fixture_root / "jobs.sqlite")
app = create_app("testing")
service = get_background_job_service()
with app.app_context():
    db.session.add(Project(id="project-navigation", name="合成导航项目"))
    db.session.commit()
    for index in range(55):
        identifier = "job-navigation-" + str(index).zfill(3)
        payload = {
            "_task_name": "手机导航任务 " + str(index).zfill(3),
            "project_name": "合成导航项目", "asset_set": "导航数据集",
            "group_field": "诊断", "selected_group_values": ["病例组", "对照组"],
            "profile_path": "/storage/合成数据/指标分组表.csv",
            "selected_samples": ["样本-" + str(i).zfill(3) for i in range(12)],
        }
        service.create_job(job_type="api_request", module="profile", job_id=identifier, project_id="project-navigation", payload=payload)
        service.upsert_job(identifier, {"status": "completed", "progress": 100, "stage": "已完成"})
