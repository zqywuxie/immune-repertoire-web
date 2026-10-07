"""Native Script Hub failure + real Flask job APIs, on synthetic input only."""
from pathlib import Path

from flask import jsonify
from flask_app.config import TestingConfig

root = Path("/evidence/server")
root.mkdir(exist_ok=True)
TestingConfig.SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(root / "jobs.sqlite")
from flask_app.app import create_app
from flask_app.models.database import db
from flask_app.routes.api_script_hub import _common
from flask_app.routes.api_script_hub.boxplot import _run_boxplot_task

app = create_app("testing")
app.config.update(REQUIRE_LOGIN=False, RESULTS_FOLDER=str(root / "results"))
source = root / "Profile.csv"
source.write_text("sample,group,metric\n001,01,1\n002,01,2\n003,02,8\n004,02,9\n", encoding="utf-8")
original = source.read_bytes()
with app.app_context():
    _common._set_task_state("script-native-failure", status="queued", progress=0, module="profile",
        payload={"_task_name": "指标分析实际失败", "selected_samples": ["missing"]})
    _run_boxplot_task("script-native-failure", results_root=root / "results",
        datapoint_path=str(source), classification_begin="group", classification_over="group",
        grouptype_fields=["group"], param_begin="metric", param_over="metric",
        selected_samples=["missing"], module_name="profile")
    assert _common._get_task_state("script-native-failure")["progress"] == 10
    _common._set_task_state("script-submit-failure", status="failed", progress=100, module="profile",
        stage="提交失败", error="合成输入未进入计算",
        payload={"_task_name": "提交阶段合成失败"})
    assert _common._get_task_state("script-submit-failure")["progress"] == 0
    assert source.read_bytes() == original

@app.get("/__fixture/evidence")
def evidence():
    from flask_app.services.script_hub_job_service import get_script_hub_job_service
    service = get_script_hub_job_service()
    return jsonify(native=service.get_job("script-native-failure"),
                   submitted=service.get_job("script-submit-failure"),
                   source_unchanged=source.read_bytes() == original)

app.run(host="0.0.0.0", port=5000, threaded=True, use_reloader=False)
