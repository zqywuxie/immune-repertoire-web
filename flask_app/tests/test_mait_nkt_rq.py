"""Isolated real RQ batch verifies PEP-to-MAIT artifact binding and batch selection."""
import importlib
import json
import os
import uuid
from pathlib import Path

import pandas as pd
import pytest
from redis import Redis
from rq import Queue, Worker


@pytest.mark.skipif(not os.environ.get("RUN_MAIT_RQ"), reason="需要隔离 Redis 队列")
def test_pep_to_mait_batch_runs_in_real_worker(tmp_path, monkeypatch):
    from flask_app.config import TestingConfig
    monkeypatch.setattr(TestingConfig, "SQLALCHEMY_DATABASE_URI", f"sqlite:///{tmp_path / 'rq.db'}")
    monkeypatch.setattr(TestingConfig, "REQUIRE_LOGIN", False)
    monkeypatch.setattr(TestingConfig, "RESULTS_FOLDER", tmp_path / "results")
    monkeypatch.setenv("FLASK_CONFIG", "testing")
    monkeypatch.setenv("JOB_QUEUE", "redis")
    module = importlib.import_module("flask_app.app")
    app = module.create_app("testing")
    monkeypatch.setattr(module, "app", app)
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kwargs: "isolated-result")
    monkeypatch.setattr("flask_app.services.mongo_service.save_cached_usage", lambda *args, **kwargs: "isolated-cache")
    monkeypatch.setattr("flask_app.services.mongo_service.get_cached_usage", lambda *args, **kwargs: [])
    from flask_app.services.mait_nkt_service import MaitNktService
    reference = tmp_path / "Alpha_Restrict.csv"
    reference.write_text("CDR3,Type\nCASSAAA,MAIT\n", encoding="utf-8")
    original_init = MaitNktService.__init__
    def initialize(self, **kwargs):
        original_init(self, **kwargs)
        self._reference_path = reference
    monkeypatch.setattr(MaitNktService, "__init__", initialize)
    from flask_app.models.database import db, Project, ProjectAsset
    from flask_app.services import persistent_queue
    from flask_app.services.background_job_service import get_background_job_service
    connection = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue("mait-check-" + uuid.uuid4().hex, connection=connection)
    monkeypatch.setattr(persistent_queue, "redis_queue", lambda: queue)
    with app.app_context():
        project = Project(name="合成批次样本队列验收")
        db.session.add(project)
        db.session.flush()
        profile = tmp_path / "profile.csv"
        profile.write_text("sample,batch,group\n001,甲,01\n001,乙,01\n", encoding="utf-8")
        files = [("profile", profile)]
        for batch, first in [("甲", 2), ("乙", 8)]:
            path = tmp_path / "pep" / batch / "TRA" / "001__TRA.csv"
            path.parent.mkdir(parents=True)
            pd.DataFrame({"CDR3(pep)": ["CASSAAA", "CASSBBB"], "V": "TRAV1", "J": "TRAJ1", "copy": [first, 10-first]}).to_csv(path, index=False)
            files.append(("pep", path))
        for kind, path in files:
            db.session.add(ProjectAsset(project_id=project.id, asset_type=kind, storage_path=str(path), original_name=path.name,
                size=path.stat().st_size, metadata_json={"asset_set": "Set1"}))
        db.session.commit()
        project_id = project.id
        response = app.test_client().post("/api/script-hub/batches", json={"project_id": project.id, "asset_set": "Set1", "items": [
            {"module": "pep-analysis", "payload": {"group_fields": ["group"], "batch_field": "batch", "selected_chains": ["TRA"], "optional_steps": [], "force_rerun": True}},
            {"module": "mait-nkt", "upstream_from": 0, "depends_on": [0], "payload": {"tra_source": "pep_analysis", "group_field": "group",
                "batch_field": "batch", "group_sample_identity": "batch_sample", "selected_group_values": {"group": ["01"]},
                "selected_samples_by_group": {"group": {"01": ["乙::001"]}}, "force_rerun": True}},
        ]})
        assert response.status_code == 202, response.json
        parent_id = response.json["job_id"]
        db.session.remove()
        db.engine.dispose()
        try:
            Worker([queue], connection=connection).work(burst=True, with_scheduler=False, logging_level="WARNING")
            db.session.remove()
            parent = get_background_job_service().get_job(parent_id)
            from flask_app.services.analysis_artifacts import scoped_pep_candidates
            assert parent["status"] == "completed", json.dumps({"items": parent["payload"]["items"], "candidates": scoped_pep_candidates(project_id, "Set1", "mait-nkt")}, ensure_ascii=False)
            items = parent["payload"]["items"]
            assert [item["status"] for item in items] == ["completed", "completed"], items
            child = get_background_job_service().get_job(items[1]["job_id"])
            assert child["payload"]["upstream_input"]["source_job_id"] == items[0]["job_id"]
            source = get_background_job_service().get_job(items[0]["job_id"])
            assert Path(child["payload"]["upstream_input"]["path"]) == Path(source["result"]["output_base"]) / "Pep_shared" / "TRA.csv"
            assert child["payload"]["config_json"]["group_sample_identity"] == "batch_sample"
            result = pd.read_csv(Path(child["result"]["output_base"]) / "MAIT_iNKT_profile.csv", dtype={"sample": str, "sample_id": str, "category": str})
            assert result[["sample", "sample_id", "batch", "category"]].to_dict("records") == [{"sample": "乙::001", "sample_id": "001", "batch": "乙", "category": "01"}]
            assert result["MAIT_fraction"].tolist() == [0.8]
            for url in child["result"]["csv_urls"] + [child["result"]["zip_url"], child["result"]["viewer_url"]]:
                assert app.test_client().get(url).status_code == 200
        finally:
            queue.delete(delete_jobs=True)
            db.session.remove()
            db.drop_all()
