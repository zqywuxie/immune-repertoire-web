import pandas as pd


def _client():
    from flask import Flask
    from flask_app.routes.api_script_hub import script_hub_bp

    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False)
    app.register_blueprint(script_hub_bp)
    return app.test_client()


def test_unified_umap_inspect_reports_sample_group_and_vj_availability(tmp_path):
    profile = tmp_path / "profile.csv"
    pd.DataFrame({"sample": ["S1", "S2"], "batch": ["run1", "run2"], "group": ["A", "B"], "x": [1, 2]}).to_csv(profile, index=False)

    response = _client().post("/api/script-hub/umap/inspect", json={"profile_path": str(profile)})

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["suggested_sample_column"] == "sample"
    assert payload["suggested_group_column"] == "group"
    assert payload["batch_column_candidates"] == ["batch"]
    assert payload["vj_usage_available"] is False


def test_unified_umap_run_queues_selected_configuration(tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _script_executor

    profile = tmp_path / "profile.csv"
    pd.DataFrame({
        "sample": ["A1", "A2", "B1", "B2"],
        "batch": ["run1", "run1", "run2", "run2"],
        "group": ["A", "A", "B", "B"],
        "x": [1, 2, 8, 9],
        "y": [2, 1, 8, 10],
    }).to_csv(profile, index=False)
    submitted = {}

    def fake_submit(fn, *args, **kwargs):
        submitted["fn"] = fn
        submitted["kwargs"] = kwargs

    monkeypatch.setattr(_script_executor, "submit", fake_submit)
    response = _client().post("/api/script-hub/umap/run", json={
        "analysis_mode": "unified",
        "profile_path": str(profile),
        "sample_column": "sample",
        "batch_field": "batch",
        "label_column": "group",
        "group_field": "group",
        "classification_begin": "group",
        "configurations": ["profile"],
        "param_begin": "x",
        "param_over": "y",
        "selected_group_values": {"group": ["A", "B"]},
        "selected_samples_by_group": {"group": {"A": ["A1", "A2"], "B": ["B1", "B2"]}},
        "force_rerun": True,
    })

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert submitted["fn"].__name__ == "_run_unified_umap_task"
    assert submitted["kwargs"]["config"]["configurations"] == ["profile"]
    assert submitted["kwargs"]["config"]["batch_field"] == "batch"
    assert submitted["kwargs"]["config"]["selected_samples_by_group"]["group"]["A"] == ["A1", "A2"]
