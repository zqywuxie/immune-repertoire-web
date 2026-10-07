"""Real report exports must retain identifiers and the exact computed CSV values."""
import csv
import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from flask_app.services.boxplot_service import BoxPlotService
from flask_app.tests.test_profile_workflow import profile_app


def _write_profile(path, sample_column="Sample"):
    frame = pd.DataFrame({
        sample_column: [f"{n:03d}" for n in range(1, 13)],
        "类别": ["01"] * 4 + ["1"] * 4 + ["02"] * 4,
        "批次": ["001"] * 4 + ["002"] * 8,
        "metric": [1., 2., 3., 4., 8., 9., 10., 11., 20., 21., 22., 23.],
    })
    frame.to_csv(path, index=False)
    return frame


def _rows(path):
    return list(csv.DictReader(Path(path).read_text(encoding="utf-8").splitlines()))


@pytest.mark.parametrize("sample_column", ["sample", "Sample", "sample_id"])
@pytest.mark.parametrize("grouped", [True, False])
def test_profile_exports_keep_actual_sample_header_and_significance_records(tmp_path, sample_column, grouped):
    source = tmp_path / "profile.csv"
    frame = _write_profile(source, sample_column)
    original = source.read_bytes()
    report = BoxPlotService(output_parent=tmp_path / "results").generate_report(
        datapoint_path=str(source), grouptype_fields=["类别", "批次"] if grouped else None,
        param_begin="metric", param_over="metric",
        group_order='{"类别":["02","01","1"],"批次":["002","001"]}',
        selected_samples=frame[sample_column].tolist(),
    )
    assert source.read_bytes() == original
    assert report.metadata["sample_filter"]["sample_column"] == sample_column
    assert report.metadata["sample_filter"]["matched_count"] == 12
    for file in report.csv_paths:
        table = pd.read_csv(file, dtype={sample_column: str})
        assert sample_column in table.columns
        assert set(table[sample_column]) == set(frame[sample_column])
        actual = table.set_index(sample_column)["metric"].to_dict()
        assert actual == frame.set_index(sample_column)["metric"].to_dict()
    if grouped:
        individual = [p for p in report.significant_paths if Path(p).name != "_all_significant.csv"]
        aggregate = report.output_base / "_all_significant.csv"
        expected = [row for path in individual for row in _rows(path)]
        assert len(individual) == 2
        assert _rows(aggregate) == expected
        assert any(row["group_a"] == "01" and row["group_b"] == "1" for row in expected)
        assert expected[0]["pvalue"] == "0.02857142857142857"
    else:
        assert report.significant_paths == []
        assert report.metadata["significant_plot_count"] == 0
        assert report.metadata["non_significant_plot_count"] == 0
        viewer = report.viewer_path.read_text(encoding="utf-8")
        assert "未进行组间检验" in viewer
        assert "data-sig=" in viewer and "unknown" in viewer
        assert 'ungrouped/metric.png' in viewer
    with zipfile.ZipFile(report.zip_path) as archive:
        for file in report.csv_paths:
            name = "data/" + Path(file).relative_to(report.output_base).as_posix()
            assert archive.read(name) == Path(file).read_bytes()
        for file in report.significant_paths:
            assert archive.read("significance/" + Path(file).name) == Path(file).read_bytes()


@pytest.mark.parametrize("grouped", [True, False])
def test_shared_boxplot_exports_keep_raw_sample_identifiers(tmp_path, grouped):
    source = tmp_path / "prepared.csv"
    frame = _write_profile(source)
    if not grouped:
        frame.drop(columns=["类别", "批次"]).to_csv(source, index=False)
    before = source.read_bytes()
    result = BoxPlotService(output_parent=tmp_path / "unused").generate_significance_boxplots(
        output_base=tmp_path / "outputs", sources=[{"path": str(source), "label": "实际合成输入", "source": "synthetic"}],
        category_columns=["类别"], metric_columns=["metric"],
    )
    assert source.read_bytes() == before
    assert len(result["all_plots"]) == 1
    table = pd.read_csv(tmp_path / "outputs" / result["all_plots"][0]["csv"], dtype={"Sample": str, "类别": str})
    assert table.set_index("Sample")["metric"].to_dict() == frame.set_index("Sample")["metric"].to_dict()
    if grouped:
        assert table.set_index("Sample")["类别"].to_dict() == frame.set_index("Sample")["类别"].to_dict()
        stats = _rows(result["significant_summary_path"])
        assert {row["group1"] for row in stats} | {row["group2"] for row in stats} == {"01", "1", "02"}


def test_ungrouped_export_without_sample_column_remains_supported(tmp_path):
    source = tmp_path / "metric.csv"
    source.write_text("metric\n1\n2\n3\n", encoding="utf-8")
    report = BoxPlotService(output_parent=tmp_path / "outputs").generate_report(
        datapoint_path=str(source), param_begin="metric", param_over="metric",
    )
    assert _rows(report.csv_paths[0]) == [{"metric": "1"}, {"metric": "2"}, {"metric": "3"}]


def test_project_group_inspection_and_http_download_keep_same_identifiers(profile_app, tmp_path):
    from flask_app.models.database import Project, ProjectAsset, db
    source = tmp_path / "原始指标.csv"
    frame = _write_profile(source)
    project = Project(name="指标导出一致性")
    db.session.add(project)
    db.session.flush()
    db.session.add(ProjectAsset(project_id=project.id, asset_type="profile",
        original_name=source.name, storage_path=str(source), size=source.stat().st_size,
        metadata_json={"asset_set": "Set2"}))
    db.session.commit()
    client = profile_app.test_client()
    inspected = client.post("/api/script-hub/boxplot/group-values",
        json={"file_path": str(source), "column": "类别"})
    assert inspected.status_code == 200, inspected.json
    assert inspected.json["sample_column"] == "Sample"
    assert inspected.json["values"] == ["01", "02", "1"]
    assert inspected.json["samples_by_value"] == {
        "01": ["001", "002", "003", "004"],
        "1": ["005", "006", "007", "008"],
        "02": ["009", "010", "011", "012"],
    }
    report = BoxPlotService(output_parent=Path(profile_app.config["RESULTS_FOLDER"]) / "shared" / "script_hub").generate_report(
        datapoint_path=str(source), grouptype_fields=["类别", "批次"],
        param_begin="metric", param_over="metric", group_order="02,01,1",
        selected_samples=frame["Sample"].tolist(),
    )
    db.session.add(ProjectAsset(project_id=project.id, asset_type="processed_result",
        storage_path=str(report.output_base), original_name="指标分析结果", size=0,
        metadata_json={"job_id": report.job_id, "output_base": str(report.output_base), "asset_set": "Set2"}))
    db.session.commit()
    for file in report.csv_paths + report.significant_paths + [report.zip_path, str(report.viewer_path)]:
        response = client.get("/api/script-hub/results/" + report.job_id + "/" + Path(file).relative_to(report.output_base).as_posix())
        assert response.status_code == 200
        assert response.data == Path(file).read_bytes()
    response = client.get("/api/script-hub/results/" + report.job_id + "/_all_significant.csv")
    assert list(csv.DictReader(io.StringIO(response.get_data(as_text=True)))) == [
        row for file in report.significant_paths if Path(file).name != "_all_significant.csv" for row in _rows(file)
    ]
