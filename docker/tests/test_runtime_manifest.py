import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("runtime_manifest", Path(__file__).parents[1] / "app/check_runtime_manifest.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_runtime_matches_code_changes_but_rejects_dependency_changes(tmp_path):
    source, installed = tmp_path / "source", tmp_path / "runtime"
    installed.mkdir()
    inputs = {
        "flask_app/requirements.txt": "flask-requirements.txt",
        "docker/app/requirements.txt": "app-requirements.txt",
        "docker/app/install_analysis.R": "install_analysis.R",
        "docker/app/Dockerfile.runtime": "Dockerfile.runtime",
    }
    for name, stored in inputs.items():
        file = source / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"original\r\n")
        (installed / stored).write_bytes(b"original\n")
    (source / "flask_app/app.py").write_text("updated business code")
    module.check(source, installed)
    for name, stored in inputs.items():
        file = source / name
        file.write_text("new dependency")
        with pytest.raises(SystemExit, match="重新构建"):
            module.check(source, installed)
        file.write_text("original\n")
    (installed / "app-requirements.txt").unlink()
    with pytest.raises(SystemExit, match="重新构建"):
        module.check(source, installed)
