"""Isolated synthetic documents served through the production Script Hub file route."""
import json
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify
from flask_app.routes.api_script_hub import script_hub_bp

root = Path(tempfile.mkdtemp(prefix="immune-documents-"))
folder = root / "1" / "script_hub" / "report"
folder.mkdir(parents=True)
html = """<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>合成报告</title>
<style>body{font-family:sans-serif;margin:20px;color:#25334d}button,a{padding:8px;border:1px solid #dce2ef;background:white;border-radius:6px;color:#315ec5}h2{font-size:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>
<h2>合成报告：界面验收</h2><p>此报告只用于验证预览交互。</p>
<button id="filter">仅显示研究组</button> <a href="values.csv" download="原始数值.csv">下载原始数据</a>
<p id="selection">当前显示全部分组</p><pre id="data">点击按钮读取同目录合成数据。</pre>
<script>document.querySelector('#filter').onclick=async()=>{const text=await (await fetch('values.csv')).text();document.querySelector('#selection').textContent='当前显示研究组';document.querySelector('#data').textContent=text;};</script></html>"""
for name in ("viewer.html", "retry.html", "fallback.html"):
    (folder / name).write_text(html, encoding="utf-8")
(folder / "empty.html").write_bytes(b"")
(folder / "values.csv").write_text("样本,组别,数值\n001,研究组,1.00000000001e-9\n", encoding="utf-8")
# A small, valid one-page PDF; no extra dependencies or analysis are invoked.
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 500 650] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
    b"<< /Length 82 >>\nstream\nBT /F1 16 Tf 50 570 Td (Synthetic PDF preview) Tj 0 -30 Td (p = 1e-9) Tj ET\nendstream",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
]
# Set the stream length to the exact bytes between stream and endstream.
content = b"BT /F1 16 Tf 50 570 Td (Synthetic PDF preview) Tj 0 -30 Td (p = 1e-9) Tj ET\n"
objects[3] = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream"
data = bytearray(b"%PDF-1.4\n")
offsets = [0]
for index, obj in enumerate(objects, 1):
    offsets.append(len(data))
    data.extend(str(index).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
start = len(data)
data.extend(b"xref\n0 6\n0000000000 65535 f \n")
for offset in offsets[1:]:
    data.extend(f"{offset:010} 00000 n \n".encode())
data.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(start).encode() + b"\n%%EOF\n")
(folder / "document.pdf").write_bytes(data)
app = Flask(__name__)
app.config.update(TESTING=True, REQUIRE_LOGIN=False, RESULTS_FOLDER=str(root))
app.register_blueprint(script_hub_bp)
counts = {}

@app.before_request
def fixture_failures():
    name = request.path.rsplit("/", 1)[-1]
    key = name + ":" + request.method
    counts[key] = counts.get(key, 0) + 1
    if name == "retry.html" and request.method == "HEAD" and counts[key] == 1:
        return jsonify(error="FILE_NOT_FOUND", message="结果文件不存在或已移除。"), 404
    if name == "fallback.html" and request.method == "HEAD":
        return "", 405
    if name == "wrong.pdf":
        return "<html>合成错误网页</html>", 200, {"Content-Type":"text/html"}
    if name == "private.html":
        return jsonify(message="合成权限拒绝"), 403
    return None
