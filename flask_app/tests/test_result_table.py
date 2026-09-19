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
