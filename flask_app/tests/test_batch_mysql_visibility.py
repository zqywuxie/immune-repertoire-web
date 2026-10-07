"""MySQL regression: an inline child completes in a separate Flask DB session."""
import os
from urllib.parse import quote_plus

import pytest
from flask import Flask, jsonify

from flask_app.models.database import db, Project
from flask_app.services import analysis_batch_service as batch
from flask_app.services.background_job_service import get_background_job_service


@pytest.mark.skipif(not os.environ.get("BATCH_MYSQL_TEST_DATABASE"), reason="Requires an isolated MySQL test database")
def test_inline_child_completion_is_visible_to_parent(tmp_path):
    database = os.environ["BATCH_MYSQL_TEST_DATABASE"]
    if not database.startswith("codex_batch_test_"):
        pytest.fail("Use a dedicated codex_batch_test_ database; existing application databases are not allowed")
    user = quote_plus(os.environ["MYSQL_USER"])
    password = quote_plus(os.environ["MYSQL_PASSWORD"])
    host = os.environ["MYSQL_HOST"]
    port = os.environ.get("MYSQL_PORT", "3306")
    app = Flask(__name__)
    app.config.update(
        TESTING=True, REQUIRE_LOGIN=False,
        SQLALCHEMY_DATABASE_URI=f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RESULTS_FOLDER=tmp_path / "results",
    )
    db.init_app(app)
    service = get_background_job_service()

    @app.post("/api/script-hub/jobs")
    def inline_child():
        child = service.create_job(job_type="script_hub", module="profile", project_id="mysql-batch")
        batch.attach_batch_child(child["job_id"])
        # The inline executor enters its own app context and commits independently.
        with app.app_context():
            service.complete_job(child["job_id"], {})
        return jsonify(success=True, job_id=child["job_id"])

    with app.app_context():
        assert db.engine.dialect.name == "mysql"
        assert db.session.execute(db.text("SELECT @@transaction_isolation")).scalar() == "REPEATABLE-READ"
        assert not db.inspect(db.engine).get_table_names(), "The test database must be empty"
        db.create_all()
        try:
            db.session.add(Project(id="mysql-batch", name="MySQL 批次事务回归"))
            db.session.commit()
            plan = batch.validate_batch({"items": [{"module": "profile", "payload": {}}]})
            parent = service.create_job(
                job_type="analysis_batch", module="analysis-batch",
                project_id="mysql-batch", payload={"items": plan, "asset_set": "Set1"},
            )
            batch.run_batch_plan(parent["job_id"])
            db.session.remove()
            final = service.get_job(parent["job_id"])
            assert final["status"] == "completed", final
            assert final["result"]["completed_count"] == 1
            child = service.get_job(final["payload"]["items"][0]["job_id"])
            assert child["status"] == "completed"
            assert child["parent_job_id"] == parent["job_id"]
        finally:
            db.session.remove()
            db.drop_all()
