"""Isolated real Flask job APIs with a synthetic executor; no scientific inputs."""
import threading
import tempfile
from pathlib import Path
from flask import jsonify, request
from flask_app.app import create_app
from flask_app.models.database import db, AnalysisJob
from flask_app.routes import api_jobs
from flask_app.services.background_job_service import get_background_job_service

from flask_app.config import TestingConfig
fixture_root = Path(tempfile.mkdtemp(prefix="codex-job-progress-"))
TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(fixture_root / "jobs.sqlite")
app = create_app("testing")
app.config.update(REQUIRE_LOGIN=False)
service = get_background_job_service()
release = threading.Event()
created = []
reject_first = True
with app.app_context():
    original = service.create_job(job_type="api_request", module="statistical.analyze", job_id="job-original",
                                  payload={"file_id":"synthetic-only","_task_name":"合成失败任务"})
    def initial_computation(context):
        for step in range(1,36):
            context.update(step, "核对合成记录", "已处理第 %d 条合成记录" % step)
        raise ValueError("合成输入缺少对照组")
    service._run(original["job_id"], initial_computation, (), {})
    # Include explicit legacy metadata gaps to check the display contract.
    service.create_job(job_type="api_request", module="analysis.execute", job_id="job-missing-time")
    service.upsert_job("job-missing-time", {"status":"interrupted","progress":25})
    row = db.session.get(AnalysisJob, "job-missing-time")
    row.completed_at = None
    db.session.commit()
def synthetic_retry(context):
    context.update(40, "核对合成记录", "合成计算暂留在检查点，等待验收继续。")
    if not release.wait(90):
        raise TimeoutError("合成验收没有释放检查点")
    context.update(80, "整理合成结果", "已完成所有合成记录")
    return {"fixture":"synthetic-only"}
class FixtureQueue:
    def submit(self, job_id, runner, **kwargs):
        created.append(job_id)
        service.submit(job_id, synthetic_retry)
api_jobs.get_job_queue = lambda: FixtureQueue()
@app.before_request
def reject_first_retry():
    global reject_first
    if request.method == "POST" and request.path == "/api/jobs/job-original/retry" and reject_first:
        reject_first = False
        return jsonify(success=False,message="当前队列暂不可用，请稍后重试。"),503
@app.get("/__fixture/state")
def state():
    return jsonify(original=service.get_job("job-original"), created=[service.get_job(i) for i in created])
@app.post("/__fixture/release")
def continue_retry():
    release.set()
    return jsonify(success=True)
