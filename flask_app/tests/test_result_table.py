import csv
import pytest
from flask_app.tests.test_result_archive import app, item
from flask_app.services.background_job_service import get_background_job_service


def test_complete_table_pagination_and_filter_beyond_first_thousand(app, tmp_path):
    path = tmp_path / "first" / "表.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["样本", "备注", "数值"])
        for index in range(1200):
            writer.writerow([f"{index:05}", '目标,记录\n第二行"引号' if index == 1100 else "常规", "1.000000000001e-9"])
    client = app.test_client(); url = f"/api/jobs/{app.config['first']}/table-preview"
    response = client.post(url, json={"url": item(app)["url"], "offset": 1175, "limit": 25})
    assert response.status_code == 200, response.json
    assert response.json["total_rows"] == 1200
    assert len(response.json["rows"]) == 25
    assert response.json["rows"][0][0] == "01175"
    filtered = client.post(url, json={"url": item(app)["url"], "query": "目标"}).json
    assert filtered["matched_rows"] == 1 and filtered["total_rows"] == 1200
    assert filtered["rows"] == [["01100", '目标,记录\n第二行"引号', "1.000000000001e-9"]]


def test_asset_filename_tsv_empty_and_parse_errors(app, tmp_path):
    client = app.test_client(); endpoint = f"/api/jobs/{app.config['first']}/table-preview"
    path = tmp_path / "first" / "table.tsv"
    path.write_text("样本\t值\n001\t3", encoding="utf-8")
    url = "/api/script-hub/results/first/table.tsv"
    get_background_job_service().upsert_job(app.config['first'], {"result": {"csv_urls": [url]}})
    assert client.post(endpoint, json={"url": url}).json["rows"] == [["001", "3"]]
    path.write_text("", encoding="utf-8")
    assert client.post(endpoint, json={"url": url}).json["columns"] == []
    path.write_text('样本\t值\n001\t"未闭合', encoding="utf-8")
    assert client.post(endpoint, json={"url": url}).status_code == 422


def test_table_cannot_read_another_tasks_output(app, monkeypatch):
    endpoint = f"/api/jobs/{app.config['first']}/table-preview"
    client = app.test_client()
    assert client.post(endpoint, json={"url": item(app, "second")["url"]}).status_code == 400
    assert client.post(endpoint, json={"url": item(app, name="missing.csv")["url"]}).status_code == 409
    import flask_app.routes.api_jobs as api
    app.config['REQUIRE_LOGIN'] = True
    monkeypatch.setattr(api, 'current_user_id', lambda: 8)
    monkeypatch.setattr(api, 'is_admin', lambda: False)
    assert client.post(endpoint, json={"url": item(app)["url"]}).status_code == 404


@pytest.mark.parametrize('parameters', [{"offset": -1}, {"offset": True}, {"limit": 101}, {"query": []}])
def test_invalid_page_parameters(app, parameters):
    response = app.test_client().post(f"/api/jobs/{app.config['first']}/table-preview", json={"url": item(app)["url"], **parameters})
    assert response.status_code == 400

def test_numeric_sort_preserves_precision_and_stable_ties(app, tmp_path, monkeypatch):
    from decimal import localcontext
    import flask_app.services.result_table as tables
    sort_root = tmp_path / "sorting"
    sort_root.mkdir()
    original = tables.tempfile.TemporaryDirectory
    monkeypatch.setattr(tables.tempfile, "TemporaryDirectory", lambda **kwargs: original(dir=sort_root, **kwargs))
    rows = [
        ["001", "1790983155444449152"],
        ["002", "1790983155444449151"],
        ["003", "1.000000000000000000000001e-9"],
        ["004", "1.000000000000000000000000e-9"],
        ["005", "1e-1000"],
        ["006", "-0"],
        ["007", "-.25"],
        ["008", "NaN"],
        ["009", ""],
        ["010", "not numeric"],
        ["011", "1790983155444449151"],
    ]
    path = tmp_path / "first" / "表.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["样本", "数值"])
        writer.writerows(rows)
    original_bytes = path.read_bytes()
    client = app.test_client()
    endpoint = f"/api/jobs/{app.config['first']}/table-preview"
    base = {"url": item(app)["url"], "sort_column": 1, "sort_mode": "numeric"}
    with localcontext() as context:
        context.prec = 4
        ascending = client.post(endpoint, json=base)
        assert ascending.status_code == 200, ascending.json
        assert [row[0] for row in ascending.json["rows"]] == ["007", "006", "005", "004", "003", "002", "011", "001", "008", "009", "010"]
        descending = client.post(endpoint, json={**base, "sort_direction": "desc"})
        assert [row[0] for row in descending.json["rows"]] == ["001", "002", "011", "003", "004", "005", "006", "007", "008", "009", "010"]
    assert ascending.json["rows"][7] == rows[0]
    assert path.read_bytes() == original_bytes
    assert list(sort_root.iterdir()) == []
    restored = client.post(endpoint, json={"url": item(app)["url"]})
    assert restored.json["rows"] == rows


def test_sort_full_filtered_table_before_pagination(app, tmp_path):
    path = tmp_path / "first" / "表.csv"
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["样本", "组别", "数值"])
        for index in range(1300):
            writer.writerow([f"{index:05}", "目标组" if index % 2 else "参考组", str(-1 if index == 1299 else index)])
    client = app.test_client()
    endpoint = f"/api/jobs/{app.config['first']}/table-preview"
    data = {"url": item(app)["url"], "query": "目标组", "sort_column": 2, "sort_mode": "numeric", "limit": 25}
    first = client.post(endpoint, json=data).json
    assert first["total_rows"] == 1300 and first["matched_rows"] == 650
    assert first["rows"][0] == ["01299", "目标组", "-1"]
    second = client.post(endpoint, json={**data, "offset": 25}).json
    assert second["rows"][0] == ["00049", "目标组", "49"]
    assert len(second["rows"]) == 25


def test_text_sort_tsv_and_empty_numeric_cell(app, tmp_path):
    path = tmp_path / "first" / "table.tsv"
    path.write_text("编号\t数值\n010\t10\n002\t2\n001\n", encoding="utf-8")
    url = "/api/script-hub/results/first/table.tsv"
    get_background_job_service().upsert_job(app.config["first"], {"result": {"csv_urls": [url]}})
    client = app.test_client()
    endpoint = f"/api/jobs/{app.config['first']}/table-preview"
    text = client.post(endpoint, json={"url": url, "sort_column": 0}).json
    assert text["rows"] == [["001"], ["002", "2"], ["010", "10"]]
    numeric = client.post(endpoint, json={"url": url, "sort_column": 1, "sort_mode": "numeric"}).json
    assert numeric["rows"] == [["002", "2"], ["010", "10"], ["001"]]


def test_sort_cleanup_after_parse_failure_or_disk_failure(app, tmp_path, monkeypatch):
    import flask_app.services.result_table as tables
    sort_root = tmp_path / "sorting"
    sort_root.mkdir()
    original = tables.tempfile.TemporaryDirectory
    monkeypatch.setattr(tables.tempfile, "TemporaryDirectory", lambda **kwargs: original(dir=sort_root, **kwargs))
    path = tmp_path / "first" / "表.csv"
    path.write_text('样本,数值\n001,2\n002,"未闭合', encoding="utf-8")
    endpoint = f"/api/jobs/{app.config['first']}/table-preview"
    body = {"url": item(app)["url"], "sort_column": 1}
    assert app.test_client().post(endpoint, json=body).status_code == 422
    assert list(sort_root.iterdir()) == []
    path.write_text("样本,数值\n001,2\n", encoding="utf-8")
    def full_disk(**kwargs):
        raise OSError("no space left")
    monkeypatch.setattr(tables.tempfile, "TemporaryDirectory", full_disk)
    response = app.test_client().post(endpoint, json=body)
    assert response.status_code == 503 and "临时排序空间" in response.json["message"]


@pytest.mark.parametrize("parameters", [
    {"sort_column": -1}, {"sort_column": True}, {"sort_column": "1"},
    {"sort_column": 1000}, {"sort_direction": "invalid"}, {"sort_mode": "invalid"},
])
def test_invalid_sort_parameters(app, parameters):
    response = app.test_client().post(f"/api/jobs/{app.config['first']}/table-preview",
                                     json={"url": item(app)["url"], **parameters})
    assert response.status_code == 400
