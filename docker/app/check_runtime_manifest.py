"""Reject application builds whose dependency inputs differ from the runtime image."""
from pathlib import Path


def check(source: Path, installed: Path):
    files = {
        "flask_app/requirements.txt": "flask-requirements.txt",
        "docker/app/requirements.txt": "app-requirements.txt",
        "docker/app/install_analysis.R": "install_analysis.R",
        "docker/app/Dockerfile.runtime": "Dockerfile.runtime",
    }
    changed = [name for name, stored in files.items()
               if not (installed / stored).is_file()
               or (source / name).read_text(encoding="utf-8") != (installed / stored).read_text(encoding="utf-8")]
    if changed:
        raise SystemExit("分析基础镜像缺失或依赖已变化，请重新构建 Dockerfile.runtime，导入服务器并更新 ANALYSIS_RUNTIME_IMAGE：" + "、".join(changed))
    print("分析依赖与基础镜像一致，无需重新安装。")


if __name__ == "__main__":
    check(Path("/app"), Path("/opt/immune-runtime"))
