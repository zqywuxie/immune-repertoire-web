from flask import Flask
import pytest
from flask_app.services.deployment_maintenance import register_maintenance, set_maintenance

def test_maintenance_blocks_writes_but_preserves_reads(tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, MAINTENANCE_DIRECTORY=str(tmp_path))
    register_maintenance(app)
    writes = []
    @app.route("/work", methods=["GET", "POST"])
    def work():
        from flask import request
        if request.method == "POST": writes.append(1)
        return {"ok":True}
    client = app.test_client()
    assert client.post("/work").status_code == 200
    set_maintenance(tmp_path, "one", True)
    assert client.get("/work").status_code == 200
    response = client.post("/work")
    assert response.status_code == 503 and response.headers["Retry-After"] == "30"
    assert len(writes) == 1
    from flask_app.services.analysis_batch_service import batch_child_context
    token = batch_child_context.set(("already-admitted", 0))
    try:
        assert client.post("/work").status_code == 200
    finally:
        batch_child_context.reset(token)
    assert client.post("/work", headers={"X-Maintenance-Bypass":"true"}).status_code == 503
    set_maintenance(tmp_path, "one", False)
    assert client.post("/work").status_code == 200 and len(writes) == 3

def test_another_deployment_cannot_clear_maintenance(tmp_path):
    set_maintenance(tmp_path, "one", True)
    for enabled in [True, False]:
        with pytest.raises(RuntimeError): set_maintenance(tmp_path, "two", enabled)
    assert (tmp_path / ".deployment-maintenance").read_text() == "one"

def test_enable_waits_for_admitted_write(tmp_path):
    import fcntl, subprocess, sys
    from flask_app.services.deployment_maintenance import open_lock
    with open_lock(tmp_path) as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        process = subprocess.Popen([sys.executable, "-m", "flask_app.services.deployment_maintenance", "enable", "--token", "wait", "--directory", str(tmp_path)])
        try:
            with pytest.raises(subprocess.TimeoutExpired): process.wait(timeout=0.3)
            assert not (tmp_path / ".deployment-maintenance").exists()
            fcntl.flock(lock, fcntl.LOCK_UN)
            assert process.wait(timeout=10) == 0
            assert (tmp_path / ".deployment-maintenance").read_text() == "wait"
        finally:
            if process.poll() is None: process.kill(); process.wait()
