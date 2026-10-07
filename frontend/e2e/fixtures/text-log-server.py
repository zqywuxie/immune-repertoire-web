"""Synthetic UTF-8 outputs, served by the production Script Hub file controller."""
import tempfile
from pathlib import Path
from flask import Flask, request, jsonify
from flask_app.routes.api_script_hub import script_hub_bp

root = Path(tempfile.mkdtemp(prefix="immune-text-log-"))
folder = root / "1" / "script_hub" / "logs"
folder.mkdir(parents=True)
lines = [f"日志 {i:04d} 样本 001 p=1.00000000001e-9" for i in range(2105)]
(folder / "run.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
# Exactly 2 MiB suffix starts on the second byte of 中.
ending = "\n末尾完成 001 p=1.00000000001e-9\n".encode()
suffix = b"\xb8\xad" + "文".encode() + b"x" * (2097152 - 5 - len(ending)) + ending
large = b"HEAD 001\n" + b"x" * (1024 * 1024) + b"\xe4" + suffix
(folder / "large.log").write_bytes(large)
(folder / "notes.txt").write_text("样本 001\n编号 9007199254740993\np=1.00000000001e-9\n<script>window.textExecuted=true</script>\n", encoding="utf-8")
(folder / "empty.log").write_bytes(b"")
(folder / "retry.log").write_text("恢复读取 001\n", encoding="utf-8")
app = Flask(__name__)
app.config.update(TESTING=True, REQUIRE_LOGIN=False, RESULTS_FOLDER=str(root))
app.register_blueprint(script_hub_bp)
counts = {}

@app.before_request
def fixture_failures():
    name = request.path.rsplit("/", 1)[-1]
    key = name + ":" + request.method
    counts[key] = counts.get(key, 0) + 1
    if name == "retry.log" and request.method == "GET" and counts[key] == 1:
        return jsonify(error="FILE_NOT_FOUND"), 404
    if name == "ignored.log":
        return large, 200, {"Content-Type": "text/plain"}
    if name == "wrong.log":
        return "<html>错误页面</html>", 200, {"Content-Type": "text/html"}
    if name == "private.log":
        return jsonify(error="FORBIDDEN"), 403
    return None
