"""Isolated real RQ batch verifies PEP-to-UMAPin artifact binding and batch selection.

Run the opt-in worker check in a fresh Docker process, before any synchronous UMAP
fit: GNU OpenMP cannot safely fork after it has been initialized in the parent.
"""
import importlib
import json
import os
import uuid
from pathlib import Path

import pandas as pd
import pytest
from redis import Redis
from rq import Queue, Worker


@pytest.mark.skipif(not os.environ.get("RUN_UMAPIN_RQ"), reason="需要隔离 Redis 队列")
def test_pep_to_umapin_batch_runs_in_real_worker(tmp_path, monkeypatch):
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
    from flask_app.models.database import db, Project, ProjectAsset
    from flask_app.services import persistent_queue
    from flask_app.services.background_job_service import get_background_job_service
    connection = Redis.from_url(os.environ["REDIS_URL"])
    queue = Queue("umapin-check-" + uuid.uuid4().hex, connection=connection)
    monkeypatch.setattr(persistent_queue, "redis_queue", lambda: queue)
    with app.app_context():
        project = Project(name="合成批次样本队列验收")
        db.session.add(project)
        db.session.flush()
        profile = tmp_path / "profile.csv"
        rows = []
        files = [("profile", profile)]
        for batch in ["001", "002"]:
            for index in range(1, 9):
                sample = f"{index:03d}"
                rows.append({"sample": sample, "batch": batch, "label": "01" if index <= 4 else "02",
                             "subject": "person-" + sample, "signal": index, "noise": index % 3})
                path = tmp_path / "pep" / batch / "TRB" / f"{sample}__TRB.csv"
                path.parent.mkdir(parents=True, exist_ok=True)
                pd.DataFrame({"CDR3(pep)": ["CASSAAA", "CASSBBB"], "V": ["TRBV1", "TRBV2"],
                              "J": ["TRBJ1", "TRBJ2"], "copy": [index, 10-index]}).to_csv(path, index=False)
                files.append(("pep", path))
        pd.DataFrame(rows).to_csv(profile, index=False)
        for kind, path in files:
            db.session.add(ProjectAsset(project_id=project.id, asset_type=kind, storage_path=str(path), original_name=path.name,
                size=path.stat().st_size, metadata_json={"asset_set": "Set1"}))
        db.session.commit()
        project_id = project.id
        response = app.test_client().post("/api/script-hub/batches", json={"project_id": project.id, "asset_set": "Set1", "items": [
            {"module": "pep-analysis", "payload": {"group_fields": ["label"], "batch_field": "batch", "selected_chains": ["TRB"], "optional_steps": [], "force_rerun": True}},
            {"module": "umapin", "upstream_from": 0, "depends_on": [0], "payload": {
                "category_col": "Category", "sample_column": "sample", "selected_categories": ["01", "02"],
                "selected_samples": [f"002::{i:03d}" for i in range(1, 9)], "n_neighbors": 3, "n_epochs": 20,
                "min_dist": 0, "output_name": "队列特征投影", "force_rerun": True}},
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
            assert parent["status"] == "completed", json.dumps({"items": [{key: item.get(key) for key in ("module", "status", "error", "detail")} for item in parent["payload"]["items"]], "available_paths": [c["path"] for c in scoped_pep_candidates(project_id, "Set1", "umapin") if c["status"] == "available"]}, ensure_ascii=False)
            items = parent["payload"]["items"]
            assert [item["status"] for item in items] == ["completed", "completed"], items
            child = get_background_job_service().get_job(items[1]["job_id"])
            assert child["payload"]["upstream_input"]["source_job_id"] == items[0]["job_id"]
            assert Path(child["payload"]["upstream_input"]["path"]).name == "df_VJ_all.csv"
            assert child["payload"]["config_json"]["selected_samples"] == [f"002::{i:03d}" for i in range(1, 9)]
            assert child["result"]["metadata"]["output_name"] == "队列特征投影"
            output = Path(child["result"]["output_base"])
            coordinates = pd.read_csv(output / "umapin_coordinates.csv", dtype=str)
            assert set(coordinates["sample"]) == {f"002::{i:03d}" for i in range(1, 9)}
            assert len(coordinates) == 8
            assert set(coordinates["Category"]) == {"01", "02"}
            assert child["result"]["metadata"]["min_dist"] == 0
            assert child["result"]["metadata"]["sample_count"] == 8
            for url in child["result"]["csv_urls"] + [child["result"]["zip_url"], child["result"]["viewer_url"]]:
                assert app.test_client().get(url).status_code == 200
        finally:
            queue.delete(delete_jobs=True)
            db.session.remove()
            db.drop_all()
