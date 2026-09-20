import importlib.util
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

spec = importlib.util.spec_from_file_location("active_jobs", Path(__file__).parents[1] / "app" / "check_active_jobs.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)

@pytest.mark.parametrize("status,blocked", [("queued", True), ("running", True), ("completed", False), ("cancelled", False)])
def test_deployment_checks_persisted_jobs(status, blocked):
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE analysis_jobs (status TEXT)"))
        connection.execute(text("INSERT INTO analysis_jobs VALUES (:status)"), {"status":status})
        if blocked:
            with pytest.raises(SystemExit, match="暂不更新"):
                preflight.ensure_idle(connection)
        else:
            preflight.ensure_idle(connection)
