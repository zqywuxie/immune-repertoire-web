"""Result file metadata, inline PDF and explicit download contracts."""
from flask import Flask
from flask_app.routes.api_script_hub import script_hub_bp


def app_and_file(tmp_path, name, body):
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, RESULTS_FOLDER=str(tmp_path / "results"))
    app.register_blueprint(script_hub_bp)
    path = tmp_path / "results" / "1" / "script_hub" / "report" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return app, path, "/api/script-hub/results/report/" + name


def test_pdf_inline_head_download_and_range(tmp_path):
    data = b"%PDF-1.4\n" + b"synthetic " * 1000
    app, path, url = app_and_file(tmp_path, "文档.pdf", data)
    client = app.test_client()
    head = client.head(url)
    assert head.status_code == 200 and head.data == b""
    assert head.mimetype == "application/pdf"
    assert head.headers["Content-Disposition"].startswith("inline;")
    assert int(head.headers["Content-Length"]) == len(data)
    inline = client.get(url)
    assert inline.data == data and inline.headers["Content-Disposition"].startswith("inline;")
    download = client.get(url + "?download=1")
    assert download.data == data and download.headers["Content-Disposition"].startswith("attachment;")
    partial = client.get(url, headers={"Range": "bytes=0-7"})
    assert partial.status_code == 206 and partial.data == data[:8]
    assert path.read_bytes() == data
    for response in (head, inline, download, partial):
        response.close()


def test_html_metadata_and_missing_files_are_distinct(tmp_path):
    app, path, url = app_and_file(tmp_path, "viewer.html", "<!doctype html><title>合成报告</title>".encode())
    client = app.test_client()
    response = client.head(url)
    assert response.status_code == 200 and response.mimetype == "text/html" and response.data == b""
    path.unlink()
    response = client.get(url)
    assert response.status_code == 404 and response.json["error"] == "FILE_NOT_FOUND"
    assert response.json["message"] == "结果文件不存在或已移除。"
    assert client.head(url).status_code == 404


def test_other_attachments_and_rejected_paths_remain_unchanged(tmp_path):
    app, _, url = app_and_file(tmp_path, "result.zip", b"synthetic")
    assert app.test_client().head(url).headers["Content-Disposition"].startswith("attachment;")
    assert app.test_client().get("/api/script-hub/results/report/../secret.pdf").status_code == 400


def test_log_suffix_clamps_to_small_file_and_keeps_attachment(tmp_path):
    data = "样本 001\np=1.00000000001e-9\n".encode()
    app, path, url = app_and_file(tmp_path, "运行.log", data)
    client = app.test_client()
    for header, expected, status in [
        ("bytes=-2097152", data, 206),
        ("bytes=-8", data[-8:], 206),
        ("bytes=0-2097151", data, 206),
        ("bytes=99999-100000", None, 416),
    ]:
        response = client.get(url, headers={"Range": header})
        assert response.status_code == status
        if expected is not None:
            assert response.data == expected
            assert response.headers["Content-Disposition"].startswith("attachment;")
            assert response.headers["Content-Range"].endswith("/" + str(len(data)))
        else:
            assert response.headers["Content-Range"] == f"bytes */{len(data)}"
        response.close()
    assert path.read_bytes() == data


def test_empty_log_suffix_is_empty_not_server_error(tmp_path):
    app, _, url = app_and_file(tmp_path, "empty.log", b"")
    response = app.test_client().get(url, headers={"Range": "bytes=-2097152"})
    assert response.status_code == 200 and response.data == b""
    assert response.headers["Content-Disposition"].startswith("attachment;")
    response.close()


def test_registered_text_asset_uses_same_suffix_handling(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from flask_app.routes import api_projects
    app = Flask(__name__)
    path = tmp_path / "说明.txt"
    data = "原始编号 001 9007199254740993\n".encode()
    path.write_bytes(data)
    asset = SimpleNamespace(original_name=path.name, mime_type="text/plain")
    monkeypatch.setattr(api_projects, "_result_redirect_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api_projects, "_resolve_asset_path", lambda _asset: path)
    app.add_url_rule("/asset/download", view_func=lambda: api_projects._send_asset_file(asset, as_attachment=True))
    response = app.test_client().get("/asset/download", headers={"Range": "bytes=-2097152"})
    assert response.status_code == 206 and response.data == data
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert path.read_bytes() == data
    response.close()
