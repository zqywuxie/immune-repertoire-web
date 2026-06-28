"""Tests for Script Hub API routes and helpers — encoding, inspect, and profile flow."""

import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest
from flask import Flask
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Query

ROOT_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parents[1]
for import_dir in (APP_DIR, ROOT_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))


@pytest.fixture(scope="module")
def api_module():
    sys.modules.setdefault("umap", SimpleNamespace(UMAP=object))
    try:
        return import_module("flask_app.routes.api_script_hub")
    except ModuleNotFoundError:
        return import_module("routes.api_script_hub")


# ── _robust_read_csv encoding fallback tests ──

def test_robust_read_csv_utf8(api_module):
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", encoding="utf-8", delete=False
    ) as f:
        f.write("col1,col2\nhello,world\n")
        fp = f.name
    try:
        df = api_module._robust_read_csv(Path(fp), nrows=5)
        assert list(df.columns) == ["col1", "col2"]
        assert len(df) == 1
    finally:
        os.unlink(fp)


def test_robust_read_csv_gbk(api_module):
    charset = "gbk" if hasattr(api_module, "_CSV_ENCODINGS") else "gb18030"
    content = "列1,列2\n你好,世界\n".encode(charset)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        fp = f.name
    try:
        df = api_module._robust_read_csv(Path(fp), nrows=5)
        assert len(df.columns) == 2
    finally:
        os.unlink(fp)


def test_robust_read_csv_xlsx(api_module):
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        fp = f.name
    try:
        pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(fp, index=False)
        df = api_module._robust_read_csv(Path(fp), nrows=5)
        assert list(df.columns) == ["a", "b"]
        assert len(df) == 2
    finally:
        os.unlink(fp)


def test_robust_read_csv_latin1_fallback(api_module):
    content = b"col1\n\xfcber\n"
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(content)
        fp = f.name
    try:
        df = api_module._robust_read_csv(Path(fp), nrows=5)
        assert list(df.columns) == ["col1"]
        assert len(df) == 1
    finally:
        os.unlink(fp)


# ── _discover_boxplot_inputs ──

def test_discover_boxplot_inputs_direct_file(api_module):
    csv = Path(__file__).parent / ".." / ".." / "test_data" / "all_data_points-beads.csv"
    if not csv.exists():
        pytest.skip("test data file not found")
    result = api_module._discover_boxplot_inputs(str(csv.parent), str(csv))
    assert "columns" in result
    assert result["column_count"] > 50


def test_discover_boxplot_inputs_no_datapoint_file(api_module):
    from flask_app.exceptions import ValidationError
    # Create nested empty dir so parent search doesn't find CSVs in tmp root
    outer = tempfile.mkdtemp()
    inner = os.path.join(outer, "sub")
    os.makedirs(inner, exist_ok=True)
    try:
        nonexistent = os.path.join(inner, "nonexistent.xyz")
        with pytest.raises((Exception, ValidationError)):
            api_module._discover_boxplot_inputs(inner, nonexistent)
    finally:
        import shutil
        shutil.rmtree(outer, ignore_errors=True)


# ── _suggest_profile_ranges ──

def test_suggest_profile_ranges(api_module):
    cols = ["sample", "therapy", "disease", "TRA_percent_reads_all", "TRA_reads", "IGHD_SHM1"]
    result = api_module._suggest_profile_ranges(cols)
    assert "suggested_grouping_begin" in result
    assert "suggested_param_begin" in result
    assert result["suggested_param_begin"] == "TRA_percent_reads_all"
    assert result["suggested_param_over"] == "IGHD_SHM1"


# ── _inspect_data_selection_payload ──

def test_inspect_data_selection_payload_empty(api_module):
    result = api_module._inspect_data_selection_payload([], None)
    assert result["sample_count"] == 0
    assert result["pep_file_count"] == 0
    assert result["chains"] == []


def test_inspect_data_selection_payload_requires_explicit_profile(api_module):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pep_dir = root / "pep_data" / "TRA"
        pep_dir.mkdir(parents=True)
        pd.DataFrame({
            "CDR3(pep)": ["AAA", "BBB"],
            "V": ["TRAV1", "TRAV2"],
            "J": ["TRAJ1", "TRAJ2"],
            "copy": [10, 20],
        }).to_csv(pep_dir / "sampleA.csv", index=False)
        dp_dir = root / "Datapoint"
        dp_dir.mkdir()
        profile = dp_dir / "Profile_All.csv"
        pd.DataFrame({"sample": ["sampleA"], "therapy": ["before"], "disease": ["healthy"]}).to_csv(profile, index=False)

        result = api_module._inspect_data_selection_payload([str(root / "pep_data")], None)

        assert result["chains"] == ["TRA"]
        assert result["sample_count"] == 1
        assert result["pep_file_count"] == 1
        assert result["profile_path"] == ""
        assert result["group_fields"] == []

        result_with_profile = api_module._inspect_data_selection_payload([str(root / "pep_data")], str(profile))
        assert result_with_profile["profile_path"] == str(profile)
        assert result_with_profile["group_fields"] == ["therapy", "disease"]


def test_inspect_data_selection_payload_does_not_scan_sibling_profile(api_module):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pep_dir = root / "artificial_peps" / "TRA"
        pep_dir.mkdir(parents=True)
        pd.DataFrame({
            "CDR3(pep)": ["AAA"],
            "V": ["TRAV1"],
            "J": ["TRAJ1"],
            "copy": [10],
        }).to_csv(pep_dir / "sampleA.csv", index=False)
        profile_dir = root / "Disease"
        profile_dir.mkdir()
        profile = profile_dir / "Profile_All.csv"
        pd.DataFrame({"sample": ["sampleA"], "disease": ["healthy"]}).to_csv(profile, index=False)

        result = api_module._inspect_data_selection_payload([str(root / "artificial_peps")], None)

        assert result["profile_path"] == ""
        assert result["group_fields"] == []


def test_inspect_data_selection_payload_uses_explicit_sibling_profile(api_module):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pep_dir = root / "artificial_peps" / "TRA"
        pep_dir.mkdir(parents=True)
        pd.DataFrame({
            "CDR3(pep)": ["AAA"],
            "V": ["TRAV1"],
            "J": ["TRAJ1"],
            "copy": [10],
        }).to_csv(pep_dir / "sampleA.csv", index=False)
        profile_dir = root / "Disease"
        profile_dir.mkdir()
        profile = profile_dir / "Profile_All.csv"
        pd.DataFrame({"sample": ["sampleA"], "disease": ["healthy"]}).to_csv(profile, index=False)

        result = api_module._inspect_data_selection_payload([str(root / "artificial_peps")], str(profile))

        assert result["profile_path"] == str(profile.resolve())
        assert result["group_fields"] == ["disease"]


def test_project_profile_asset_detection(api_module):
    profile_asset = SimpleNamespace(
        asset_type="profile",
        original_name="PatientProfile.csv",
        storage_path=r"E:\data\PatientProfile.csv",
        metadata_json={},
    )
    legacy_role_asset = SimpleNamespace(
        asset_type="datapoint",
        original_name="data.csv",
        storage_path=r"E:\data\data.csv",
        metadata_json={"role": "profile"},
    )
    datapoint_asset = SimpleNamespace(
        asset_type="datapoint",
        original_name="usage.csv",
        storage_path=r"E:\data\usage.csv",
        metadata_json={},
    )

    assert api_module._is_project_profile_asset(profile_asset)
    assert not api_module._is_project_profile_asset(legacy_role_asset)
    assert not api_module._is_project_profile_asset(datapoint_asset)


def test_project_primary_pep_path_uses_registered_asset(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    registered_pep = tmp_path / "registered_pep"
    registered_pep.mkdir()
    stale_pep = tmp_path / "stale_pep"
    stale_pep.mkdir()

    with app.app_context():
        db.create_all()
        project = Project(name="Registered PEP Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="pep",
            original_name="registered_pep",
            storage_path=str(registered_pep),
            size=0,
        ))
        db.session.commit()

        resolved = api_module._primary_pep_path_from_request(
            {"project_id": project.id, "base_path": str(stale_pep)},
            "base_path",
        )
        db.session.remove()
        db.drop_all()

    assert resolved == str(registered_pep)


def test_collect_project_assets_uses_sort_buffer_fallback(api_module, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    pep_dir = tmp_path / "pep"
    pep_dir.mkdir()
    profile_path = tmp_path / "profile.csv"
    profile_path.write_text("sample,group\ns1,A\n", encoding="utf-8")

    with app.app_context():
        db.create_all()
        project = Project(id="project-sort-fallback", name="Sort Fallback", status="active")
        old_asset = ProjectAsset(
            id="asset-old",
            project_id=project.id,
            asset_type="pep",
            original_name="pep",
            storage_path=str(pep_dir),
            size=0,
            uploaded_at=datetime.utcnow() - timedelta(days=1),
        )
        new_asset = ProjectAsset(
            id="asset-new",
            project_id=project.id,
            asset_type="profile",
            original_name="profile.csv",
            storage_path=str(profile_path),
            size=profile_path.stat().st_size,
            uploaded_at=datetime.utcnow(),
        )
        db.session.add_all([project, old_asset, new_asset])
        db.session.commit()

        original_all = Query.all

        class SortBufferError(Exception):
            def __init__(self):
                super().__init__(1038, "Out of sort memory, consider increasing server sort buffer size")

        def flaky_all(self):
            if getattr(self, "_order_by_clauses", ()):
                raise OperationalError("SELECT project_assets", {}, SortBufferError())
            return original_all(self)

        monkeypatch.setattr(Query, "all", flaky_all)

        result = api_module._collect_project_script_hub_assets(project.id)

        db.session.remove()
        db.drop_all()

    assert result["pep_paths"] == [str(pep_dir)]
    assert result["profile_path"] == str(profile_path)


def test_normalize_script_result_generates_viewer_and_zip(api_module, tmp_path):
    output_base = tmp_path / "script_job"
    output_base.mkdir()
    (output_base / "alpha_one.png").write_bytes(b"fake-png")
    (output_base / "beta_two.png").write_bytes(b"fake-png")
    (output_base / "values.csv").write_text("sample,value\ns1,1\n", encoding="utf-8")

    result = {
        "module": "unit-test",
        "job_id": output_base.name,
        "output_base": str(output_base),
        "png_urls": [
            f"/api/script-hub/results/{output_base.name}/alpha_one.png",
            f"/api/script-hub/results/{output_base.name}/beta_two.png",
        ],
        "csv_urls": [f"/api/script-hub/results/{output_base.name}/values.csv"],
    }

    normalized = api_module._normalize_script_result(
        result,
        output_base,
        {"sample_count": 1},
        title="Unit Test Results",
        subtitle="Generated by test",
        dl_extras=[("csv_urls", None, "CSV")],
        zip_name="unit_results.zip",
    )

    assert normalized["viewer_url"].endswith("/viewer.html")
    assert normalized["zip_url"].endswith("/unit_results.zip")
    assert (output_base / "viewer.html").exists()
    assert (output_base / "unit_results.zip").exists()
    assert (output_base / "metadata.json").exists()
    html = (output_base / "viewer.html").read_text(encoding="utf-8")
    assert 'id="categorySelect"' in html
    assert '<option value="alpha" selected>alpha</option>' in html
    assert '<option value="beta">beta</option>' in html
    assert 'class="plot-card is-hidden" data-category="beta"' in html
    assert "__all__" not in html
    with zipfile.ZipFile(output_base / "unit_results.zip") as archive:
        names = set(archive.namelist())
    assert "figures/alpha_one.png" in names
    assert "figures/beta_two.png" in names
    assert "tables/values.csv" in names
    assert "metadata/metadata.json" in names
    assert "viewer/viewer.html" in names


def test_pep_viewer_switches_by_chain_and_collapses_csv(api_module, tmp_path):
    output_base = tmp_path / "pep_job"
    output_base.mkdir()
    result = {
        "job_id": output_base.name,
        "heatmap_image_urls": [
            f"/api/script-hub/results/{output_base.name}/therapy/heatmap/1VJusage/TRA/A.png",
            f"/api/script-hub/results/{output_base.name}/therapy/heatmap/1VJusage/TRB/A.png",
        ],
        "arrange_heatmap_urls": [f"/api/script-hub/results/{output_base.name}/therapy/CDR3_arrage_heatmap/TRA.png"],
        "plot_heatmap_urls": [f"/api/script-hub/results/{output_base.name}/therapy/plot_heatmap/TRA_unique_heatmap.png"],
        "shared_matrix_urls": [f"/api/script-hub/results/{output_base.name}/Pep_shared/TRA.csv"],
        "usage_urls": [f"/api/script-hub/results/{output_base.name}/usage/1VJusage/TRA.csv"],
        "heatmap_csv_urls": [f"/api/script-hub/results/{output_base.name}/therapy/heatmap/1VJusage/TRA/csv_file/A.csv"],
        "classification_urls": [],
        "proportion_urls": [],
    }
    metadata = {
        "selected_chains": ["TRA", "TRB"],
        "group_fields": ["therapy"],
        "output_counts": {"shared_matrix": 1},
    }

    api_module._write_pep_analysis_viewer(output_base, result, metadata)

    html = (output_base / "viewer.html").read_text(encoding="utf-8")
    assert result["viewer_url"].endswith("/viewer.html")
    assert "Differential heatmaps" in html
    assert "CDR3 arrangement heatmaps" in html
    assert "Unique CDR3 heatmaps" in html
    assert 'id="pepImageCategorySelect"' in html
    assert '<option value="Differential heatmaps" selected>Differential heatmaps (2)</option>' in html
    assert '<option value="CDR3 arrangement heatmaps">CDR3 arrangement heatmaps (1)</option>' in html
    assert "therapy/CDR3_arrage_heatmap/TRA.png" in html
    assert "chain-tab" not in html
    assert "<details><summary>2.Pep_shared.py / Pep_shared</summary>" in html
    assert "<details><summary>2.Pep_shared.py / usage</summary>" in html
    assert "<details><summary>5.Heat_map_Thread.py / heatmap/csv_file</summary>" in html
    assert "Pep_shared/TRA.csv" in html
    assert "usage/1VJusage/TRA.csv" in html
    assert "plot-card" in html


def test_pep_viewer_displays_arrange_heatmap_category_when_only_step7_images(api_module, tmp_path):
    output_base = tmp_path / "pep_job_step7"
    output_base.mkdir()
    result = {
        "job_id": output_base.name,
        "heatmap_image_urls": [],
        "proportion_plot_urls": [],
        "arrange_heatmap_urls": [
            f"/api/script-hub/results/{output_base.name}/group_type/CDR3_arrage_heatmap/TRA.png"
        ],
        "plot_heatmap_urls": [],
        "shared_matrix_urls": [],
        "usage_urls": [],
        "heatmap_csv_urls": [],
        "classification_urls": [],
        "proportion_urls": [],
    }

    api_module._write_pep_analysis_viewer(output_base, result, {
        "selected_chains": ["TRA"],
        "group_fields": ["group_type"],
    })

    html = (output_base / "viewer.html").read_text(encoding="utf-8")
    assert '<option value="CDR3 arrangement heatmaps" selected>CDR3 arrangement heatmaps (1)</option>' in html
    assert "group_type/CDR3_arrage_heatmap/TRA.png" in html
    assert "No images generated" not in html


def test_pep_viewer_does_not_render_csv_previews_as_main_images(api_module, tmp_path):
    output_base = tmp_path / "pep_job"
    matrix_dir = output_base / "Pep_shared"
    matrix_dir.mkdir(parents=True)
    csv_path = matrix_dir / "TRA.csv"
    pd.DataFrame({
        "CDR3(pep)": ["AAA", "BBB", "CCC"],
        "sampleA__TRA.csv": [1, 0, 2],
        "sampleB__TRA.csv": [0, 3, 1],
    }).to_csv(csv_path, index=False)

    preview_urls = api_module._generate_pep_csv_preview_images(output_base, [str(csv_path)])
    result = {
        "job_id": output_base.name,
        "heatmap_image_urls": [],
        "arrange_heatmap_urls": [],
        "plot_heatmap_urls": [],
        "preview_heatmap_urls": preview_urls,
        "shared_matrix_urls": [f"/api/script-hub/results/{output_base.name}/Pep_shared/TRA.csv"],
        "usage_urls": [],
        "heatmap_csv_urls": [],
        "classification_urls": [],
        "proportion_urls": [],
    }

    api_module._write_pep_analysis_viewer(output_base, result, {
        "selected_chains": ["TRA"],
        "group_fields": ["therapy"],
    })

    assert len(preview_urls) == 1
    assert (output_base / "viewer_previews").exists()
    assert list((output_base / "viewer_previews").glob("*.png"))
    html = (output_base / "viewer.html").read_text(encoding="utf-8")
    assert "CSV matrix previews" not in html
    assert "No images generated" in html
    assert "<details><summary>2.Pep_shared.py / Pep_shared</summary>" in html


def test_pep_analysis_runs_dependent_steps_after_step6(tmp_path, monkeypatch):
    from flask_app.services.pep_analysis_service import PepAnalysisService

    pep_dir = tmp_path / "pep"
    pep_dir.mkdir()
    pd.DataFrame({
        "CDR3(pep)": ["AAA"],
        "V": ["TRAV1"],
        "J": ["TRAJ1"],
        "copy": [1],
    }).to_csv(pep_dir / "sampleA__TRA.csv", index=False)
    profile = tmp_path / "Profile_All.csv"
    pd.DataFrame({"sample": ["sampleA"], "therapy": ["A"]}).to_csv(profile, index=False)

    order = []

    def fake_run_cdr3(self, chain, file_paths, output_base, progress_callback=None):
        shared = output_base / "Pep_shared" / f"{chain}.csv"
        usage = output_base / "usage" / "1VJusage" / f"{chain}.csv"
        shared.parent.mkdir(parents=True, exist_ok=True)
        usage.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text("CDR3(pep),sampleA__TRA.csv\nAAA,1\n", encoding="utf-8")
        usage.write_text("sample,TRAV1;TRAJ1\nsampleA,1\n", encoding="utf-8")
        return [str(shared)], [str(usage)]

    def fake_add(src, dst, profile_df, group_field):
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text("sample,Category,TRAV1;TRAJ1\nsampleA,A,1\n", encoding="utf-8")

    def fake_step6(self, chains, pep_shared_cate_dir, field_dir, min_sample_threshold):
        order.append(6)
        out = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared" / "TRA.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("CDR3(pep),A__sum\nAAA,1\n", encoding="utf-8")
        return [str(out)], [], []

    def fake_step7(self, chains, field_dir):
        assert 6 in order
        order.append(7)
        out = field_dir / "CDR3_arrage_heatmap" / "TRA.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"png")
        return [str(out)]

    def fake_step8(self, chains, field_dir):
        assert 6 in order
        order.append(8)
        out = field_dir / "plot_heatmap" / "TRA_unique_heatmap.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"png")
        return [str(out)]

    monkeypatch.setattr(PepAnalysisService, "_run_cdr3_sharing", fake_run_cdr3)
    monkeypatch.setattr(PepAnalysisService, "_add_cate_shared", staticmethod(fake_add))
    monkeypatch.setattr(PepAnalysisService, "_add_cate_usage", staticmethod(fake_add))
    monkeypatch.setattr(PepAnalysisService, "_run_step6_for_group", fake_step6)
    monkeypatch.setattr(PepAnalysisService, "_run_step7_for_group", fake_step7)
    monkeypatch.setattr(PepAnalysisService, "_run_step8_for_group", fake_step8)

    report = PepAnalysisService(output_parent=tmp_path / "results").generate_report(
        pep_data_dir=str(pep_dir),
        profile_path=str(profile),
        group_fields=["therapy"],
        selected_chains=["TRA"],
        optional_steps={7, 8},
    )

    assert order[0] == 6
    assert 7 in order
    assert 8 in order
    assert len(report.arrange_heatmap_paths) == 1
    assert len(report.plot_heatmap_paths) == 1
    assert report.metadata["optional_steps_requested"] == [7, 8]
    assert report.metadata["optional_steps_run"] == [6, 7, 8]


def test_pep_step2_fast_writer_matches_reference_outputs(tmp_path):
    from flask_app.services.pep_analysis_service import PepAnalysisService

    pep_a = tmp_path / "sampleA__TRA.csv"
    pep_b = tmp_path / "sampleB__TRA.csv"
    pd.DataFrame({
        "CDR3(pep)": ["AAA", "AAA", "BBB"],
        "V": ["TRAV1", "TRAV1", "TRAV2"],
        "J": ["TRAJ1", "TRAJ1", "TRAJ2"],
        "copy": [2, 3, 5],
    }).to_csv(pep_a, index=False)
    pd.DataFrame({
        "CDR3(pep)": ["AAA", "CCC"],
        "V": ["TRAV1", "TRAV3"],
        "J": ["TRAJ1", "TRAJ3"],
        "copy": [1, 9],
    }).to_csv(pep_b, index=False)

    output_base = tmp_path / "out"
    seen_progress = []
    service = PepAnalysisService(output_parent=tmp_path / "results")
    service._run_cdr3_sharing(
        "TRA",
        [str(pep_a), str(pep_b)],
        output_base,
        progress_callback=lambda done, total, name, **meta: seen_progress.append((done, total, name, meta.get("phase", "reading"))),
    )

    shared = pd.read_csv(output_base / "Pep_shared" / "TRA.csv")
    assert shared["CDR3(pep)"].tolist() == ["AAA", "BBB", "CCC"]
    assert shared["sampleA__TRA.csv"].iloc[:2].tolist() == [5.0, 5.0]
    assert pd.isna(shared["sampleA__TRA.csv"].iloc[2])
    assert shared["sampleB__TRA.csv"].iloc[0] == 1.0
    assert pd.isna(shared["sampleB__TRA.csv"].iloc[1])
    assert shared["sampleB__TRA.csv"].iloc[2] == 9.0

    one_v = pd.read_csv(output_base / "usage" / "1Vusage" / "TRA.csv", index_col=0)
    assert one_v.loc["sampleA__TRA.csv", "TRAV1"] == 0.5
    assert one_v.loc["sampleA__TRA.csv", "TRAV2"] == 0.5
    assert one_v.loc["sampleB__TRA.csv", "TRAV3"] == 0.9

    zero_vj = pd.read_csv(output_base / "usage" / "0VJusage" / "TRA.csv", index_col=0)
    assert zero_vj.loc["sampleA__TRA.csv", "TRAV1;TRAJ1"] == 2 / 3
    assert zero_vj.loc["sampleA__TRA.csv", "TRAV2;TRAJ2"] == 1 / 3
    assert seen_progress[-1][0:2] == (2, 2)
    phases = [item[3] for item in seen_progress if len(item) > 3]
    assert "writing_shared" in phases
    assert phases.count("writing_usage") == 6


def test_pep_step3_add_cate_shared_streams_without_local_dataframe(tmp_path):
    from flask_app.services.pep_analysis_service import PepAnalysisService

    src = tmp_path / "TRA.csv"
    dst = tmp_path / "out" / "TRA.csv"
    pd.DataFrame({
        "CDR3(pep)": ["AAA", "BBB"],
        "sampleA__TRA.csv": [5, 0],
        "sampleB__TRA.csv": [0, 3],
    }).to_csv(src, index=False)
    profile = pd.DataFrame({
        "sample": ["sampleA", "sampleB"],
        "group_type": ["after", "before"],
    })

    PepAnalysisService._add_cate_shared(src, dst, profile, "group_type")

    out_df = pd.read_csv(dst)
    assert out_df.iloc[0]["CDR3(pep)"] == "category"
    assert set(out_df.columns) == {"CDR3(pep)", "sampleA__TRA.csv", "sampleB__TRA.csv"}
    assert out_df.iloc[0]["sampleA__TRA.csv"] == "after"
    assert out_df.iloc[1]["CDR3(pep)"] == "AAA"


def test_pep_plot_heatmap_reads_single_unique_categories(tmp_path):
    from flask_app.services.pep_analysis_service import PepAnalysisService

    csv_path = tmp_path / "TRA.csv"
    pd.DataFrame([
            {
                "CDR3(pep)": " ",
                "sampleA__TRA.csv": "T1DM",
                "sampleB__TRA.csv": "CT",
                "T1DM__sum": " ",
                "T1DM__count": " ",
                "CT__sum": " ",
                "CT__count": " ",
                "all_num": " ",
                "category": " ",
            },
        {
                "CDR3(pep)": "AAA",
                "sampleA__TRA.csv": 2,
                "sampleB__TRA.csv": 0,
                "T1DM__sum": 2,
                "T1DM__count": 1,
                "CT__sum": 0,
                "CT__count": 0,
                "all_num": 1,
                "category": "T1DM__count",
            },
            {
                "CDR3(pep)": "BBB",
                "sampleA__TRA.csv": 1,
                "sampleB__TRA.csv": 1,
                "T1DM__sum": 1,
                "T1DM__count": 1,
                "CT__sum": 1,
                "CT__count": 1,
                "all_num": 2,
                "category": "('T1DM__count', 'CT__count')",
            },
    ]).to_csv(csv_path, index=False)

    payload = PepAnalysisService._read_plot_heatmap_data(csv_path, "TRA")

    assert [section["category"] for section in payload["sections"]] == ["T1DM__count"]
    assert payload["sections"][0]["records"][0]["chain"] == "TRA"
    assert payload["sections"][0]["records"][0]["cdr3"] == "AAA"


def test_pep_step8_falls_back_to_available_count_categories(tmp_path):
    from flask_app.services.pep_analysis_service import PepAnalysisService

    csv_path = tmp_path / "TRA.csv"
    pd.DataFrame([
        {
            "CDR3(pep)": " ",
            "sampleA__TRA.csv": "A",
            "sampleB__TRA.csv": "B",
            "A__sum": " ",
            "A__count": " ",
            "B__sum": " ",
            "B__count": " ",
            "all_num": " ",
            "category": " ",
        },
        {
            "CDR3(pep)": "AAA",
            "sampleA__TRA.csv": 2,
            "sampleB__TRA.csv": 0,
            "A__sum": 2,
            "A__count": 1,
            "B__sum": 0,
            "B__count": 0,
            "all_num": 1,
            "category": "A__count",
        },
    ]).to_csv(csv_path, index=False)

    payload = PepAnalysisService._read_plot_heatmap_data(csv_path, "TRA")

    assert [section["category"] for section in payload["sections"]] == ["A__count"]
    assert payload["sections"][0]["records"][0]["cdr3"] == "AAA"


def test_pep_step5_empty_heatmap_matrix_writes_csv_without_warning(tmp_path):
    from flask_app.services.pep_analysis_service import PepAnalysisService

    src = tmp_path / "usage.csv"
    pd.DataFrame({
        "sample": ["sampleA", "sampleB"],
        "Category": ["A", "A"],
        "TRAV1;TRAJ1": [1, 2],
    }).to_csv(src, index=False)

    image_paths, csv_paths = PepAnalysisService._run_heatmap(src, tmp_path / "heatmap", 0.05)

    assert image_paths == []
    assert len(csv_paths) == 1
    assert Path(csv_paths[0]).exists()


def test_pep_step6_outputs_only_reference_csv_tables(tmp_path):
    from flask_app.services.pep_analysis_service import PepAnalysisService

    pep_shared = tmp_path / "Pep_shared_cate" / "Pep_shared"
    pep_shared.mkdir(parents=True)
    pd.DataFrame([
        {"CDR3(pep)": "category", "sampleA__TRA.csv": "T1DM", "sampleB__TRA.csv": "CT"},
        {"CDR3(pep)": "AAA", "sampleA__TRA.csv": 1, "sampleB__TRA.csv": 0},
        {"CDR3(pep)": "BBB", "sampleA__TRA.csv": 0, "sampleB__TRA.csv": 1},
    ]).to_csv(pep_shared / "TRA.csv", index=False)

    service = PepAnalysisService(output_parent=tmp_path / "results")
    arr_paths, prp_paths, plot_paths = service._run_step6_for_group(["TRA"], pep_shared, tmp_path / "field", 0)

    assert len(arr_paths) == 1
    assert len(prp_paths) == 1
    assert plot_paths == []
    assert Path(arr_paths[0]).exists()
    assert Path(prp_paths[0]).exists()


def test_pep_step5_plot_uses_matplotlib_lock_and_step6_keeps_csv_only(tmp_path, monkeypatch):
    from flask_app.services import pep_analysis_service
    from flask_app.services.pep_analysis_service import PepAnalysisService

    lock_events = []
    original_lock = pep_analysis_service._PLOT_LOCK

    class TrackingLock:
        def __enter__(self):
            lock_events.append("enter")
            return original_lock.__enter__()

        def __exit__(self, exc_type, exc, tb):
            lock_events.append("exit")
            return original_lock.__exit__(exc_type, exc, tb)

    monkeypatch.setattr(pep_analysis_service, "_PLOT_LOCK", TrackingLock())

    usage_base = tmp_path / "usage_cate" / "usage"
    src_usage = usage_base / "1VJusage" / "TRA.csv"
    src_usage.parent.mkdir(parents=True)
    pd.DataFrame({
        "sample": ["sampleA", "sampleB"],
        "Category": ["A", "B"],
        "TRAV1;TRAJ1": [10, 1],
    }).to_csv(src_usage, index=False)

    pep_shared = tmp_path / "Pep_shared_cate" / "Pep_shared"
    src_shared = pep_shared / "TRA.csv"
    src_shared.parent.mkdir(parents=True)
    pd.DataFrame([
        {"CDR3(pep)": "category", "sampleA__TRA.csv": "A", "sampleB__TRA.csv": "B"},
        {"CDR3(pep)": "AAA", "sampleA__TRA.csv": 1, "sampleB__TRA.csv": 0},
        {"CDR3(pep)": "BBB", "sampleA__TRA.csv": 0, "sampleB__TRA.csv": 1},
    ]).to_csv(src_shared, index=False)

    service = PepAnalysisService(output_parent=tmp_path / "results")
    step5_imgs, _ = service._run_step5_for_group(["TRA"], usage_base, tmp_path / "field", 1.0)
    arr_paths, prp_paths, step6_imgs = service._run_step6_for_group(["TRA"], pep_shared, tmp_path / "field", 0)

    assert step5_imgs
    assert arr_paths
    assert prp_paths
    assert step6_imgs == []
    assert lock_events.count("enter") >= 1
    assert lock_events.count("enter") == lock_events.count("exit")


def test_inspect_data_selection_uses_project_profile_asset(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    pep_dir = tmp_path / "pep" / "TRA"
    pep_dir.mkdir(parents=True)
    pd.DataFrame({
        "CDR3(pep)": ["AAA"],
        "V": ["TRAV1"],
        "J": ["TRAJ1"],
        "copy": [10],
    }).to_csv(pep_dir / "sampleA.csv", index=False)
    profile = tmp_path / "Profile_All.csv"
    pd.DataFrame({"sample": ["sampleA"], "disease": ["healthy"]}).to_csv(profile, index=False)

    with app.app_context():
        db.create_all()
        project = Project(name="Script Hub Profile Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="pep",
            original_name="pep",
            storage_path=str(tmp_path / "pep"),
            size=0,
        ))
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="profile",
            original_name=profile.name,
            storage_path=str(profile),
            size=profile.stat().st_size,
            metadata_json={"role": "profile"},
        ))
        db.session.commit()

        client = app.test_client()
        response = client.post(
            "/api/script-hub/data-selection/inspect",
            json={"project_id": project.id, "pep_paths": [], "profile_path": None},
        )
        payload = response.get_json()
        profile_response = client.post(
            "/api/script-hub/profile/inspect",
            json={"project_id": project.id, "datapoint_path": str(tmp_path / "wrong_profile.csv")},
        )
        profile_payload = profile_response.get_json()
        umap_response = client.post(
            "/api/script-hub/umap/inspect",
            json={"project_id": project.id, "datapoint_path": str(tmp_path / "wrong_profile.csv")},
        )
        umap_payload = umap_response.get_json()
        pep_response = client.post(
            "/api/script-hub/pep-analysis/inspect",
            json={"project_id": project.id, "base_path": str(tmp_path / "wrong_pep_dir")},
        )
        pep_payload = pep_response.get_json()
        topclone_response = client.post(
            "/api/script-hub/topclone/inspect",
            json={"project_id": project.id, "pep_data_path": str(tmp_path / "wrong_pep_dir")},
        )
        topclone_payload = topclone_response.get_json()
        db.session.remove()
        db.drop_all()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["profile_path"] == str(profile)
    assert payload["pep_file_count"] == 1
    assert payload["group_fields"] == ["disease"]
    assert profile_response.status_code == 200
    assert profile_payload["datapoint_path"] == str(profile.resolve())
    assert profile_payload["suggested_param_begin"]
    assert umap_response.status_code == 200
    assert umap_payload["datapoint_path"] == str(profile.resolve())
    assert pep_response.status_code == 200
    assert pep_payload["profile_path"] == str(profile)
    assert topclone_response.status_code == 200
    assert topclone_payload["category_cols"] == ["disease"]


def test_project_datapoint_asset_is_not_used_as_profile(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    legacy_datapoint = tmp_path / "legacy_datapoint.csv"
    profile = tmp_path / "Profile_All.csv"
    legacy_datapoint.write_text("", encoding="utf-8")
    pd.DataFrame({"sample": ["sampleA"], "disease": ["healthy"]}).to_csv(profile, index=False)

    with app.app_context():
        db.create_all()
        project = Project(name="Profile Asset Only Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="datapoint",
            original_name=legacy_datapoint.name,
            storage_path=str(legacy_datapoint),
            size=0,
            metadata_json={"role": "profile"},
        ))
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="profile",
            original_name=profile.name,
            storage_path=str(profile),
            size=profile.stat().st_size,
            metadata_json={"role": "profile"},
        ))
        db.session.commit()

        response = app.test_client().post("/api/script-hub/data-selection/inspect", json={"project_id": project.id})
        payload = response.get_json()
        db.session.remove()
        db.drop_all()

    assert response.status_code == 200
    assert payload["profile_path"] == str(profile)
    assert payload["registered_profile_paths"] == [str(profile)]
    assert "invalid_profile_paths" not in payload


def test_project_asset_path_is_rebased_after_workspace_move(api_module, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    current_projects_root = tmp_path / "current_projects"
    project_id = "project-after-move"
    profile = current_projects_root / project_id / "assets" / "profile" / "Profile_All.csv"
    profile.parent.mkdir(parents=True)
    pd.DataFrame({"sample": ["sampleA"], "disease": ["healthy"]}).to_csv(profile, index=False)
    old_storage_path = rf"E:\old-workspace\flask_app\data\projects\{project_id}\assets\profile\Profile_All.csv"
    monkeypatch.setattr(api_module, "_project_assets_root", lambda: current_projects_root)

    with app.app_context():
        db.create_all()
        project = Project(id=project_id, name="Moved Workspace Project")
        db.session.add(project)
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="profile",
            original_name=profile.name,
            storage_path=old_storage_path,
            size=profile.stat().st_size,
        ))
        db.session.commit()

        response = app.test_client().post("/api/script-hub/profile/inspect", json={"project_id": project.id})
        payload = response.get_json()
        db.session.remove()
        db.drop_all()

    assert response.status_code == 200
    assert payload["datapoint_path"] == str(profile.resolve())
    assert payload["columns"] == ["sample", "disease"]


def test_project_profile_asset_skips_empty_registered_file(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    valid_profile = tmp_path / "Profile_All.csv"
    empty_profile = tmp_path / "EmptyProfile.csv"
    pd.DataFrame({"sample": ["sampleA"], "disease": ["healthy"]}).to_csv(valid_profile, index=False)
    empty_profile.write_text("", encoding="utf-8")

    with app.app_context():
        db.create_all()
        project = Project(name="Skip Empty Profile Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="profile",
            original_name=valid_profile.name,
            storage_path=str(valid_profile),
            size=valid_profile.stat().st_size,
            metadata_json={"role": "profile"},
        ))
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="profile",
            original_name=empty_profile.name,
            storage_path=str(empty_profile),
            size=0,
            metadata_json={"role": "profile"},
        ))
        db.session.commit()

        response = app.test_client().post("/api/script-hub/profile/inspect", json={"project_id": project.id})
        payload = response.get_json()
        db.session.remove()
        db.drop_all()

    assert response.status_code == 200
    assert payload["datapoint_path"] == str(valid_profile.resolve())
    assert payload["columns"] == ["sample", "disease"]


def test_project_profile_asset_rejects_only_empty_registered_file(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    empty_profile = tmp_path / "EmptyProfile.csv"
    empty_profile.write_text("", encoding="utf-8")

    with app.app_context():
        db.create_all()
        project = Project(name="Only Empty Profile Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="profile",
            original_name=empty_profile.name,
            storage_path=str(empty_profile),
            size=0,
            metadata_json={"role": "profile"},
        ))
        db.session.commit()

        client = app.test_client()
        summary_response = client.post("/api/script-hub/data-selection/inspect", json={"project_id": project.id})
        summary_payload = summary_response.get_json()
        response = client.post("/api/script-hub/profile/inspect", json={"project_id": project.id})
        payload = response.get_json()
        db.session.remove()
        db.drop_all()

    assert summary_response.status_code == 200
    assert summary_payload["success"] is True
    assert summary_payload["profile_path"] == ""
    assert summary_payload["registered_profile_paths"] == [str(empty_profile)]
    assert summary_payload["invalid_profile_paths"] == [str(empty_profile)]
    assert summary_payload["warnings"]
    assert response.status_code == 400
    assert payload["success"] is False
    assert "empty or has no columns" in payload["message"]


def test_project_transcriptome_asset_drives_go_kegg_and_deg_inspect(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    aligned = ROOT_DIR / "test_data" / "aligned.csv"
    assert aligned.exists()

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    with app.app_context():
        db.create_all()
        project = Project(name="Transcriptome Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="transcriptome",
            original_name=aligned.name,
            storage_path=str(aligned),
            size=aligned.stat().st_size,
            metadata_json={"role": "transcriptome", "reference": "test_data/aligned.csv"},
        ))
        db.session.commit()

        client = app.test_client()
        summary_response = client.post("/api/script-hub/data-selection/inspect", json={"project_id": project.id})
        summary_payload = summary_response.get_json()
        enrichment_response = client.post(
            "/api/script-hub/go-kegg-enrichment/inspect",
            json={"project_id": project.id, "expression_path": str(tmp_path / "wrong.csv")},
        )
        enrichment_payload = enrichment_response.get_json()
        volcano_response = client.post(
            "/api/script-hub/volcano/inspect",
            json={"project_id": project.id, "input_mode": "expression"},
        )
        volcano_payload = volcano_response.get_json()
        db.session.remove()
        db.drop_all()

    resolved_aligned = str(aligned.resolve())
    assert summary_response.status_code == 200
    assert summary_payload["registered_transcriptome_paths"] == [str(aligned)]
    assert summary_payload["transcriptome_path"] == str(aligned)
    assert enrichment_response.status_code == 200
    assert enrichment_payload["expression_path"] == resolved_aligned
    assert {"ICI_T1DM", "T1DM", "T_CT"}.issubset(set(enrichment_payload["groups"]))
    assert enrichment_payload["gene_count"] > 0
    assert volcano_response.status_code == 200
    assert volcano_payload["expression_path"] == resolved_aligned
    assert volcano_payload["input_mode"] == "expression"
    assert volcano_payload["sample_count"] > 0


def test_cached_usage_resolver_prefers_usage_cate_asset(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    plain_usage = tmp_path / "plain" / "usage"
    cate_usage = tmp_path / "therapy" / "usage_cate" / "usage"
    (plain_usage / "1VJusage").mkdir(parents=True)
    (cate_usage / "1VJusage").mkdir(parents=True)
    pd.DataFrame({
        "sample": ["s1", "s2"],
        "Category": ["A", "B"],
        "TRAV1;TRAJ1": [1, 2],
    }).to_csv(cate_usage / "1VJusage" / "TRA.csv", index=False)

    with app.app_context():
        db.create_all()
        project = Project(name="Cached Usage Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="cached_usage",
            original_name="plain_usage",
            storage_path=str(plain_usage),
            size=0,
            metadata_json={"usage_scope": "usage", "volcano_data_dir": str(plain_usage / "1VJusage")},
        ))
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="cached_usage",
            original_name="therapy_usage_cate",
            storage_path=str(cate_usage),
            size=0,
            metadata_json={
                "usage_scope": "usage_cate",
                "group_field": "therapy",
                "volcano_data_dir": str(cate_usage / "1VJusage"),
            },
        ))
        db.session.commit()

        resolved_volcano = api_module._resolve_project_cached_usage_path({"project_id": project.id}, preferred="volcano")
        resolved_umapin = api_module._resolve_project_cached_usage_path({"project_id": project.id}, preferred="umapin")
        db.session.remove()
        db.drop_all()

    assert resolved_volcano == str((cate_usage / "1VJusage").resolve())
    assert resolved_umapin == str(cate_usage.resolve())


def test_mait_nkt_inspect_auto_resolves_project_pep_tra(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    output_base = tmp_path / "results" / "script_hub" / "pep_job"
    pep_shared = output_base / "Pep_shared"
    usage_dir = output_base / "usage"
    pep_shared.mkdir(parents=True)
    (usage_dir / "1VJusage").mkdir(parents=True)
    pd.DataFrame({
        "CDR3(pep)": ["AAA", "BBB"],
        "sampleA__TRA.csv": [1, 0],
        "sampleB__TRA.csv": [0, 1],
    }).to_csv(pep_shared / "TRA.csv", index=False)
    profile = tmp_path / "Profile_All.csv"
    pd.DataFrame({"sample": ["sampleA", "sampleB"], "therapy": ["A", "B"]}).to_csv(profile, index=False)

    with app.app_context():
        db.create_all()
        project = Project(name="MAIT PEP Auto Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="profile",
            original_name=profile.name,
            storage_path=str(profile),
            size=profile.stat().st_size,
            metadata_json={"role": "profile"},
        ))
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="cached_usage",
            original_name="pep_usage_pep_job",
            storage_path=str(usage_dir),
            size=0,
            metadata_json={
                "source_module": "pep-analysis",
                "source_job_id": "pep_job",
                "usage_scope": "usage",
                "pep_output_base": str(output_base),
                "pep_shared_TRA_path": str(pep_shared / "TRA.csv"),
            },
        ))
        db.session.commit()

        response = app.test_client().post(
            "/api/script-hub/mait-nkt/inspect",
            json={"project_id": project.id, "tra_source": "pep_analysis"},
        )
        payload = response.get_json()
        db.session.remove()
        db.drop_all()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["resolved_tra_path"] == str((pep_shared / "TRA.csv").resolve())
    assert payload["source_job_id"] == "pep_job"
    assert payload["sample_count"] == 2
    assert payload["profile_groups"]["therapy"] == ["A", "B"]


def test_cached_usage_resolver_reads_mongodb_documents(api_module, tmp_path, monkeypatch):
    from flask_app.models.database import Project, db
    from flask_app.services import mongo_service

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    cate_usage = tmp_path / "therapy" / "usage_cate" / "usage"
    (cate_usage / "1VJusage").mkdir(parents=True)
    (cate_usage / "1VJusage" / "TRA.csv").write_text("sample,Category,VJ\ns1,A,1\n", encoding="utf-8")

    def fake_get_cached_usage(project_id):
        return [{
            "_id": "mongo-cache-id",
            "project_id": project_id,
            "source_job_id": "pep_job_1",
            "original_name": "pep_usage_cate_therapy",
            "storage_path": str(cate_usage),
            "usage_scope": "usage_cate",
            "group_field": "therapy",
            "chains": ["TRA"],
            "group_fields": ["therapy"],
            "usage_types": {"1VJusage": str(cate_usage / "1VJusage")},
            "metadata_json": {
                "usage_scope": "usage_cate",
                "group_field": "therapy",
                "volcano_data_dir": str(cate_usage / "1VJusage"),
                "storage_path": str(cate_usage),
            },
        }]

    monkeypatch.setattr(mongo_service, "get_cached_usage", fake_get_cached_usage)

    with app.app_context():
        db.create_all()
        project = Project(name="Mongo Cached Usage Project")
        db.session.add(project)
        db.session.commit()
        resolved_volcano = api_module._resolve_project_cached_usage_path({"project_id": project.id}, preferred="volcano")
        resolved_umapin = api_module._resolve_project_cached_usage_path({"project_id": project.id}, preferred="umapin")
        db.session.remove()
        db.drop_all()

    assert resolved_volcano == str((cate_usage / "1VJusage").resolve())
    assert resolved_umapin == str(cate_usage.resolve())


def test_cache_pep_usage_assets_writes_mongodb_usage_and_usage_cate(api_module, tmp_path, monkeypatch):
    from flask_app.models.database import Project, db
    from flask_app.services import mongo_service
    from flask_app.services.project_asset_service import get_project_asset_service

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    output_base = tmp_path / "results" / "pep_job"
    usage = output_base / "usage"
    usage_cate = output_base / "therapy" / "usage_cate" / "usage"
    (usage / "1VJusage").mkdir(parents=True)
    (usage_cate / "1VJusage").mkdir(parents=True)
    (usage / "1VJusage" / "TRA.csv").write_text("sample,TRAV1;TRAJ1\ns1,1\n", encoding="utf-8")
    (usage_cate / "1VJusage" / "TRA.csv").write_text("sample,Category,TRAV1;TRAJ1\ns1,A,1\n", encoding="utf-8")
    (usage / "df_1VJusage_all.csv").write_text("sample,Category,TRAV1;TRAJ1\ns1,A,1\n", encoding="utf-8")

    mongo_calls = []

    def fake_save_cached_usage(**kwargs):
        mongo_calls.append(kwargs)
        return f"mongo-{len(mongo_calls)}"

    monkeypatch.setattr(mongo_service, "save_cached_usage", fake_save_cached_usage)

    with app.app_context():
        db.create_all()
        project = Project(name="PEP Mongo Cache Project")
        db.session.add(project)
        db.session.commit()
        get_project_asset_service(tmp_path / "projects")
        api_module._cache_pep_usage_assets(
            project_id=project.id,
            job_id="pep_job",
            output_base=str(output_base),
            selected_chains=["TRA"],
            group_fields=["therapy"],
            pep_data_dir=str(tmp_path / "pep"),
            profile_path=str(tmp_path / "Profile.csv"),
            projects_root=tmp_path / "projects",
        )
        db.session.remove()
        db.drop_all()

    assert len(mongo_calls) == 2
    scopes = {call["metadata_json"]["usage_scope"] for call in mongo_calls}
    assert scopes == {"usage", "usage_cate"}
    usage_cate_call = next(call for call in mongo_calls if call["metadata_json"]["usage_scope"] == "usage_cate")
    assert usage_cate_call["storage_path"] == str(usage_cate)
    assert usage_cate_call["metadata_json"]["volcano_data_dir"] == str(usage_cate / "1VJusage")


def test_run_pep_analysis_task_caches_with_app_context(api_module, tmp_path, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True)

    output_base = tmp_path / "results" / "script_hub" / "pep_job_context"
    output_base.mkdir(parents=True)

    class FakePepAnalysisService:
        def __init__(self, output_parent):
            self.output_parent = output_parent

        def generate_report(self, **kwargs):
            return SimpleNamespace(
                job_id="pep_job_context",
                output_base=output_base,
                shared_matrix_paths=[],
                usage_paths=[],
                heatmap_image_paths=[],
                heatmap_csv_paths=[],
                classification_paths=[],
                proportion_paths=[],
                arrange_heatmap_paths=[],
                plot_heatmap_paths=[],
                zip_path=str(output_base / "pep_analysis_results.zip"),
                metadata={
                    "selected_chains": ["TRA"],
                    "group_fields": ["therapy"],
                    "output_counts": {},
                },
            )

    cache_calls = []

    def fake_cache_pep_usage_assets(**kwargs):
        from flask import current_app

        assert current_app._get_current_object() is app
        cache_calls.append(kwargs)

    monkeypatch.setattr(api_module, "PepAnalysisService", FakePepAnalysisService)
    monkeypatch.setattr(api_module, "_cache_pep_usage_assets", fake_cache_pep_usage_assets)

    task_id = "task_context_cache"
    api_module._run_pep_analysis_task(
        task_id,
        results_root=tmp_path / "results",
        pep_data_dir=str(tmp_path / "pep"),
        profile_path=str(tmp_path / "Profile.csv"),
        group_fields=["therapy"],
        selected_chains=["TRA"],
        project_id="project-1",
        app_context_app=app,
    )

    task = api_module._get_task_state(task_id)
    assert task["status"] == "completed"
    assert len(cache_calls) == 1
    assert cache_calls[0]["project_id"] == "project-1"


def test_volcano_and_umapin_inspect_use_project_cached_usage(api_module, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    app.register_blueprint(api_module.script_hub_bp)

    cate_usage = tmp_path / "therapy" / "usage_cate" / "usage"
    data_dir = cate_usage / "1VJusage"
    data_dir.mkdir(parents=True)
    pd.DataFrame({
        "sample": ["s1", "s2", "s3", "s4"],
        "Category": ["A", "A", "B", "B"],
        "TRAV1;TRAJ1": [1, 2, 5, 6],
        "TRAV2;TRAJ2": [6, 5, 2, 1],
    }).to_csv(data_dir / "TRA.csv", index=False)

    with app.app_context():
        db.create_all()
        project = Project(name="Cached Inspect Project")
        db.session.add(project)
        db.session.commit()
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type="cached_usage",
            original_name="therapy_usage_cate",
            storage_path=str(cate_usage),
            size=0,
            metadata_json={
                "usage_scope": "usage_cate",
                "group_field": "therapy",
                "volcano_data_dir": str(data_dir),
            },
        ))
        db.session.commit()

        client = app.test_client()
        volcano_response = client.post("/api/script-hub/volcano/inspect", json={"project_id": project.id})
        volcano_payload = volcano_response.get_json()
        umapin_response = client.post("/api/script-hub/umapin/inspect", json={"project_id": project.id})
        umapin_payload = umapin_response.get_json()
        db.session.remove()
        db.drop_all()

    assert volcano_response.status_code == 200
    assert volcano_payload["data_dir"] == str(data_dir.resolve())
    assert volcano_payload["file_count"] == 1
    assert umapin_response.status_code == 200
    assert umapin_payload["data_path"] == str(data_dir.resolve())
    assert "Category" in umapin_payload["columns"]
    assert "TRAV1;TRAJ1" in umapin_payload["columns"]


def test_script_hub_jobs_api_tracks_task_state(api_module):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(api_module.script_hub_bp)

    job_service = api_module.get_script_hub_job_service()
    job_service.clear()
    with api_module._script_task_lock:
        api_module._script_tasks.clear()

    api_module._set_task_state(
        "script_task_test_a",
        status="queued",
        progress=0.0,
        stage="Queued",
        detail="waiting",
        meta={"module": "profile"},
        project_id="project-a",
    )
    api_module._set_task_state(
        "script_task_test_b",
        status="failed",
        progress=100.0,
        stage="Failed",
        detail="boom",
        error="boom",
        meta={"module": "umap"},
        project_id="project-a",
    )

    client = app.test_client()
    list_response = client.get("/api/script-hub/jobs?project_id=project-a")
    list_payload = list_response.get_json()
    job_response = client.get("/api/script-hub/jobs/script_task_test_b")
    job_payload = job_response.get_json()
    task_response = client.get("/api/script-hub/task/script_task_test_a")
    task_payload = task_response.get_json()

    assert list_response.status_code == 200
    assert list_payload["success"] is True
    assert {job["job_id"] for job in list_payload["jobs"]} == {"script_task_test_a", "script_task_test_b"}
    assert job_response.status_code == 200
    assert job_payload["job"]["status"] == "failed"
    assert job_payload["job"]["error"] == "boom"
    assert task_response.status_code == 200
    assert task_payload["job_id"] == "script_task_test_a"
    assert task_payload["module"] == "profile"


def test_script_hub_jobs_cancel_updates_task_state(api_module):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(api_module.script_hub_bp)

    api_module.get_script_hub_job_service().clear()
    with api_module._script_task_lock:
        api_module._script_tasks.clear()

    api_module._set_task_state(
        "script_task_cancel",
        status="running",
        progress=25.0,
        stage="Running",
        detail="working",
        meta={"module": "db-alignment"},
    )

    response = app.test_client().post("/api/script-hub/jobs/script_task_cancel/cancel")
    payload = response.get_json()
    task = api_module._get_task_state("script_task_cancel")

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["job"]["status"] == "cancelled"
    assert task["status"] == "cancelled"


def test_global_jobs_list_returns_json_on_service_error(monkeypatch):
    api_jobs = import_module("flask_app.routes.api_jobs")

    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(api_jobs.jobs_bp)

    class BrokenJobService:
        def list_jobs(self, **kwargs):
            raise RuntimeError("analysis_jobs table missing")

    monkeypatch.setattr(api_jobs, "get_background_job_service", lambda: BrokenJobService())

    response = app.test_client().get("/api/jobs?limit=200")
    payload = response.get_json()

    assert response.status_code == 500
    assert response.content_type.startswith("application/json")
    assert payload["success"] is False
    assert payload["error"] == "JOBS_LIST_ERROR"
    assert "analysis_jobs table missing" in payload["details"]["detail"]


def test_background_cancelled_job_cannot_be_overwritten(tmp_path):
    from flask_app.models.database import db
    from flask_app.services.background_job_service import get_background_job_service

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    with app.app_context():
        db.create_all()
        service = get_background_job_service()
        service.clear()
        service.create_job(job_type="script_hub", module="pep-analysis", job_id="job_cancel_guard")
        cancelled = service.request_cancel("job_cancel_guard")
        progressed = service.update_progress("job_cancel_guard", 55, "Running", "should not overwrite")
        completed = service.complete_job("job_cancel_guard", {"ok": True})
        db.session.remove()
        db.drop_all()

    assert cancelled["status"] == "cancelled"
    assert progressed["status"] == "cancelled"
    assert completed["status"] == "cancelled"


def test_script_hub_record_stage_obeys_generic_job_cancel(api_module):
    from flask_app.models.database import db
    from flask_app.services.background_job_service import get_background_job_service

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)

    api_module.get_script_hub_job_service().clear()
    with api_module._script_task_lock:
        api_module._script_tasks.clear()

    with app.app_context():
        db.create_all()
        api_module._set_task_state(
            "script_task_generic_cancel",
            status="running",
            progress=20.0,
            stage="Running",
            detail="working",
            meta={"module": "pep-analysis"},
        )
        get_background_job_service().request_cancel("script_task_generic_cancel")
        with pytest.raises(api_module.ScriptTaskCancelled):
            api_module._record_stage("script_task_generic_cancel", 30, "Running", "next tick")
        task = api_module._get_task_state("script_task_generic_cancel")
        job = get_background_job_service().get_job("script_task_generic_cancel")
        db.session.remove()
        db.drop_all()

    assert task["status"] == "cancelled"
    assert job["status"] == "cancelled"


def test_suggest_umap_ranges(api_module):
    cols = ["sample", "therapy", "disease", "TRA_percent_reads_all", "TRB_reads"]
    result = api_module._suggest_umap_ranges(cols)
    assert result["suggested_classification_begin"] == "therapy"
    assert result["suggested_classification_over"] == "disease"
    assert result["suggested_param_begin"] == "TRA_percent_reads_all"
    assert result["suggested_param_over"] == "TRB_reads"


# ── _sanitize_nan (existing test covered, ensure it still passes) ──

def test_sanitize_nan_strict_json(api_module):
    payload = {
        "preview_rows": [[26, float("nan"), pd.NA, pd.NaT, float("inf")]],
        "nested": {"value": float("-inf")},
    }
    sanitized = api_module._sanitize_nan(payload)
    encoded = json.dumps(sanitized, allow_nan=False)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    assert sanitized["preview_rows"] == [[26, None, None, None, None]]
    assert sanitized["nested"]["value"] is None


# ── _ALLOWED_MODULES check ──

def test_allowed_modules_contains_profile(api_module):
    assert "profile" in api_module._ALLOWED_MODULES
    assert "db-alignment" in api_module._ALLOWED_MODULES
    assert "pep-analysis" in api_module._ALLOWED_MODULES


# ── BoxPlotService viewer generation ──

def test_boxplot_service_viewer():
    """Ensure BoxPlotService.generate_report produces viewer_path and viewer.html."""
    sys.modules.setdefault("umap", SimpleNamespace(UMAP=object))
    try:
        from flask_app.services.boxplot_service import BoxPlotService
    except ModuleNotFoundError:
        from services.boxplot_service import BoxPlotService

    with tempfile.TemporaryDirectory() as td:
        dp = Path(td) / "datapoint.csv"
        df = pd.DataFrame({
            "sample": ["s1", "s2", "s3", "s4"],
            "therapy": ["txA", "txB", "txA", "txB"],
            "disease": ["d1", "d2", "d1", "d2"],
            "TRA_percent_reads_all": [0.1, 0.2, 0.15, 0.25],
            "TRB_reads": [100, 200, 150, 250],
        })
        df.to_csv(dp, index=False, encoding="utf-8")

        service = BoxPlotService(output_parent=Path(td) / "results")
        report = service.generate_report(
            datapoint_path=str(dp),
            grouptype_fields=["therapy"],
            param_begin="TRA_percent_reads_all",
            param_over="TRB_reads",
            pvalue_threshold=1.0,
            output_name="test_boxplot",
        )

        assert report.job_id.startswith("test_boxplot")
        assert report.viewer_path.exists()
        assert report.viewer_path.name == "viewer.html"

        content = report.viewer_path.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "plot-card" in content
        assert "TRA_percent_reads_all" in content
        assert report.metadata["plot_count"] >= 1


def test_volcano_service_concatenates_usage_directory():
    from flask_app.services.volcano_service import VolcanoService

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        usage = root / "1VJusage"
        usage.mkdir()
        pd.DataFrame({
            "sample": ["s1", "s2", "s3", "s4"],
            "Category": ["A", "A", "B", "B"],
            "TRAV1;TRAJ1": [10, 11, 2, 3],
            "TRAV2;TRAJ2": [1, 1, 8, 9],
        }).to_csv(usage / "TRA.csv", index=False)

        service = VolcanoService(output_parent=root / "results")
        report = service.generate_report(data_dir=str(root), pvalue_threshold=1.0)

        assert len(report.png_paths) == 1
        assert len(report.csv_paths) == 1
        assert Path(report.png_paths[0]).exists()
        result_df = pd.read_csv(report.csv_paths[0])
        assert {"Gene", "FC", "log2FC", "P-value", "significant"}.issubset(result_df.columns)


def test_volcano_service_runs_expression_matrix():
    from flask_app.services.volcano_service import VolcanoService

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        expr = root / "aligned.csv"
        pd.DataFrame({
            "gene": ["G1", "G2", "G3"],
            "tpm_A_1": [100, 2, 10],
            "tpm_A_2": [110, 3, 11],
            "tpm_B_1": [5, 90, 10],
            "tpm_B_2": [4, 95, 9],
        }).to_csv(expr, index=False)

        service = VolcanoService(output_parent=root / "results")
        report = service.generate_expression_report(
            expression_path=str(expr),
            comparisons=[["A", "B"]],
            pvalue_threshold=1.0,
            logfc_cutoff=0.1,
        )

        assert report.metadata["input_mode"] == "expression"
        assert report.metadata["comparisons"] == [{"group1": "A", "group2": "B"}]
        assert len(report.png_paths) == 1
        assert Path(report.png_paths[0]).exists()
        deg_df = pd.read_csv(report.csv_paths[0])
        assert {"gene_symbol", "logFC", "P.Value", "adj.P.Val", "significant"}.issubset(deg_df.columns)


def test_go_kegg_inspect_expression_matrix_route(api_module, tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(api_module.script_hub_bp)

    expr = tmp_path / "aligned.csv"
    pd.DataFrame({
        "gene": ["G1", "G2"],
        "tpm_A_1": [1, 2],
        "tpm_A_2": [2, 3],
        "tpm_B_1": [4, 5],
        "tpm_B_2": [5, 6],
    }).to_csv(expr, index=False)

    response = app.test_client().post(
        "/api/script-hub/go-kegg-enrichment/inspect",
        json={"expression_path": str(expr)},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["groups"] == ["A", "B"]
    assert payload["group_counts"] == {"A": 2, "B": 2}
    assert payload["suggested_comparisons"] == [{"group1": "A", "group2": "B"}]


def test_run_go_kegg_task_normalizes_fake_service(api_module, tmp_path, monkeypatch):
    output_base = tmp_path / "results" / "script_hub" / "go_kegg_job"
    output_base.mkdir(parents=True)
    (output_base / "plot.png").write_bytes(b"png")
    (output_base / "table.csv").write_text("term,pvalue\nGO:1,0.01\n", encoding="utf-8")
    (output_base / "plot.pdf").write_bytes(b"pdf")
    (output_base / "go_kegg_enrichment.log").write_text("ok\n", encoding="utf-8")
    (output_base / "go_kegg_enrichment_results.zip").write_bytes(b"zip")

    class FakeGoKeggService:
        def __init__(self, output_parent):
            self.output_parent = output_parent

        def generate_report(self, **kwargs):
            return SimpleNamespace(
                job_id="go_kegg_job",
                output_base=output_base,
                png_paths=[str(output_base / "plot.png")],
                pdf_paths=[str(output_base / "plot.pdf")],
                csv_paths=[str(output_base / "table.csv")],
                zip_path=str(output_base / "go_kegg_enrichment_results.zip"),
                log_path=str(output_base / "go_kegg_enrichment.log"),
                metadata={"expression_path": kwargs["expression_path"], "comparisons": [{"group1": "A", "group2": "B"}]},
            )

    monkeypatch.setattr(api_module, "GoKeggEnrichmentService", FakeGoKeggService)
    task_id = "task_go_kegg_fake"
    api_module._run_go_kegg_enrichment_task(
        task_id,
        results_root=tmp_path / "results",
        expression_path=str(tmp_path / "aligned.csv"),
        comparisons=[["A", "B"]],
    )

    task = api_module._get_task_state(task_id)
    assert task["status"] == "completed"
    assert task["result"]["module"] == "go-kegg-enrichment"
    assert task["result"]["viewer_url"].endswith("/viewer.html")
    assert task["result"]["zip_url"].endswith("/go_kegg_enrichment_results.zip")
    assert task["result"]["log_url"].endswith("/go_kegg_enrichment.log")


def test_pgen_public_distribution_generates_png_and_stats(tmp_path):
    from flask_app.services.pgen_analysis_service import PgenAnalysisService

    output_base = tmp_path / "pgen_job"
    detail_dir = output_base / "Pgen"
    detail_dir.mkdir(parents=True)
    processed = []
    for sample, values in {
        "s1": [("CASSA", 1e-4), ("CASSB", 1e-6)],
        "s2": [("CASSA", 1e-5), ("CASSB", 1e-7)],
    }.items():
        sample_dir = detail_dir / sample
        sample_dir.mkdir()
        detail_path = sample_dir / "TRA.csv"
        pd.DataFrame({
            "CDR3(pep)": [item[0] for item in values],
            "Pgen": [item[1] for item in values],
        }).to_csv(detail_path, index=False)
        processed.append({
            "sample": sample,
            "chain": "TRA",
            "detail_path": str(detail_path),
        })

    profile_df = pd.DataFrame({
        "sample": ["s1", "s2"],
        "Symptoms": ["A", "A"],
    })
    png_paths = []

    csv_paths = PgenAnalysisService._plot_public_pgen_distributions(
        processed_records=processed,
        profile_df=profile_df,
        sample_col="sample",
        category_col="Symptoms",
        output_base=output_base,
        png_paths=png_paths,
    )

    assert len(png_paths) == 1
    assert Path(png_paths[0]).name == "TRA_Symptoms_pgen_public.png"
    assert Path(png_paths[0]).exists()
    assert len(csv_paths) == 1
    stats = pd.read_csv(csv_paths[0])
    assert stats.loc[0, "public_cdr3"] == 2
    assert stats.loc[0, "public_nonzero"] == 4


def test_pgen_inspect_returns_distribution_category_candidates(api_module, tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(api_module.script_hub_bp)

    pep_dir = tmp_path / "pep"
    chain_dir = pep_dir / "TRA"
    chain_dir.mkdir(parents=True)
    pd.DataFrame({
        "CDR3(pep)": ["AAA"],
        "V": ["TRAV1"],
        "J": ["TRAJ1"],
        "copy": [1],
    }).to_csv(chain_dir / "s1__TRA.csv", index=False)
    profile = tmp_path / "Profile.csv"
    pd.DataFrame({
        "sample": ["s1"],
        "Symptoms": ["A"],
        "therapy": ["before"],
    }).to_csv(profile, index=False)

    response = app.test_client().post(
        "/api/script-hub/pgen-analysis/inspect",
        json={"base_path": str(pep_dir), "profile_path": str(profile)},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["distribution_category_candidates"] == ["Symptoms", "therapy"]


def test_combined_charts_cache_context_includes_transcriptome(tmp_path):
    api_jobs = import_module("flask_app.routes.api_jobs")

    sample_file = tmp_path / "sample.csv"
    transcriptome = tmp_path / "aligned.csv"
    sample_file.write_text("cdr3,copy,v,j\nAAA,1,TRBV1,TRBJ1\n", encoding="utf-8")
    transcriptome.write_text("Gene,tpm_A_1,tpm_B_1\nG1,1,2\n", encoding="utf-8")

    context = api_jobs._build_charts_cache_context("", {
        "selected_modules": ["heatmap"],
        "selected_chains": ["TRB"],
        "field_mapping": {"cdr3_column": "cdr3", "copy_column": "copy"},
        "transcriptome_path": str(transcriptome),
        "samples": [{
            "sample_key": "S1",
            "data_files": [{"filepath": str(sample_file)}],
        }],
    })

    asset_types = [asset["asset_type"] for asset in context["input_assets"]]
    assert asset_types == ["sample", "transcriptome"]
    transcriptome_asset = context["input_assets"][1]
    assert transcriptome_asset["path"] == str(transcriptome.resolve())
    assert context["config_json"]["has_transcriptome"] is True


def test_umapin_service_concatenates_usage_directory(monkeypatch):
    import numpy as np
    from flask_app.services.umapin_service import UmapinService

    class FakeUmap:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def fit_transform(self, values):
            return np.column_stack([np.arange(values.shape[0]), np.arange(values.shape[0]) * 0.5])

    monkeypatch.setitem(sys.modules, "umap", SimpleNamespace(UMAP=FakeUmap))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        usage = root / "1VJusage"
        usage.mkdir()
        pd.DataFrame({
            "sample": ["s1", "s2", "s3", "s4"],
            "Category": ["A", "A", "B", "B"],
            "TRBV1;TRBJ1": [1, 2, 3, 4],
            "TRBV2;TRBJ2": [4, 3, 2, 1],
        }).to_csv(usage / "TRB.csv", index=False)

        service = UmapinService(output_parent=root / "results")
        report = service.generate_report(
            data_path=str(root),
            param_begin="TRBV1;TRBJ1",
            param_over="TRBV2;TRBJ2",
            category_col="Category",
        )

        assert len(report.png_paths) == 1
        assert len(report.csv_paths) >= 1
        assert Path(report.output_base / "df_VJ_all.csv").exists()
        coord_df = pd.read_csv(report.csv_paths[0])
        assert {"sample", "Category", "UMAP1", "UMAP2"}.issubset(coord_df.columns)


def test_topclone_viewer_exposes_chain_and_topn_filters(api_module, tmp_path):
    output_base = tmp_path / "topclone_job"
    output_base.mkdir()
    result = {
        "job_id": output_base.name,
        "png_urls": [
            f"/api/script-hub/results/{output_base.name}/boxplot/therapy/top10TRA.png",
            f"/api/script-hub/results/{output_base.name}/boxplot/therapy/top20TRB.png",
        ],
        "topclone_csv_url": f"/api/script-hub/results/{output_base.name}/topclone.csv",
        "cdr3_urls": [f"/api/script-hub/results/{output_base.name}/top_cdr3_sequences/TRA/top10_cdr3s.csv"],
    }
    metadata = {
        "mode": "trace",
        "chains": ["TRA", "TRB"],
        "sample_count": 2,
        "top_clone_values": [10, 20, 50, 100],
    }

    api_module._build_topclone_viewer(output_base, result, metadata)

    html = (output_base / "viewer.html").read_text(encoding="utf-8")
    assert 'id="chainSelect"' in html
    assert 'id="topSelect"' in html
    assert '"chain": "TRA"' in html
    assert '"top_n": "10"' in html
    assert "top10_cdr3s.csv" in html


def test_script_hub_result_route_finds_user_scoped_viewer(api_module, tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, RESULTS_FOLDER=str(tmp_path / "results"))
    app.register_blueprint(api_module.script_hub_bp)

    viewer = tmp_path / "results" / "1" / "script_hub" / "topclone_job" / "viewer.html"
    viewer.parent.mkdir(parents=True)
    viewer.write_text("<!doctype html><title>viewer</title>", encoding="utf-8")

    response = app.test_client().get("/api/script-hub/results/topclone_job/viewer.html")

    assert response.status_code == 200
    assert b"<title>viewer</title>" in response.data


def test_mait_nkt_service_matches_profile_sample_alias(monkeypatch, tmp_path):
    from flask_app.services.mait_nkt_service import MaitNktService

    def fake_boxplot(*, out_path, **kwargs):
        Path(out_path).write_bytes(b"png")

    monkeypatch.setattr(MaitNktService, "_load_reference", lambda self: {"MAIT": ["AAA"]})
    monkeypatch.setattr(MaitNktService, "_make_boxplot", staticmethod(fake_boxplot))

    tra_df = pd.DataFrame({
        "CDR3(pep)": ["AAA", "BBB"],
        "sampleA__TRA.csv": [5, 0],
        "sampleB__TRA.csv": [0, 7],
    })
    profile_df = pd.DataFrame({
        "SampleID": ["sampleA", "sampleB"],
        "therapy": ["Control", "Treatment"],
    })

    report = MaitNktService(output_parent=tmp_path).generate_report(
        tra_df=tra_df,
        profile_df=profile_df,
        group_field="therapy",
        job_id="mait_alias",
    )

    profile = pd.read_csv(report.csv_paths[0])
    assert profile["category"].tolist() == ["Control", "Treatment"]
    assert profile["MAIT_sum"].tolist() == [5, 0]


def test_mait_nkt_run_reuses_resolved_pep_tra_path(api_module, monkeypatch, tmp_path):
    app = Flask(__name__)
    app.config.update(TESTING=True)
    app.register_blueprint(api_module.script_hub_bp)

    tra = tmp_path / "TRA.csv"
    profile = tmp_path / "Profile_All.csv"
    pd.DataFrame({
        "CDR3(pep)": ["AAA"],
        "sampleA__TRA.csv": [1],
    }).to_csv(tra, index=False)
    pd.DataFrame({"sample": ["sampleA"], "therapy": ["A"]}).to_csv(profile, index=False)

    submitted = {}

    def fake_submit(fn, *args, **kwargs):
        submitted["fn"] = fn
        submitted["kwargs"] = kwargs
        return SimpleNamespace()

    monkeypatch.setattr(api_module, "_resolve_pep_analysis_tra_source", lambda data: (_ for _ in ()).throw(AssertionError("resolver should not run")))
    monkeypatch.setattr(api_module._script_executor, "submit", fake_submit)

    response = app.test_client().post("/api/script-hub/mait-nkt/run", json={
        "tra_source": "pep_analysis",
        "tra_path": str(tra),
        "profile_path": str(profile),
        "group_field": "therapy",
        "force_rerun": True,
    })
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert submitted["kwargs"]["tra_path"] == str(tra.resolve())
