"""Generate deployment configuration inside a container, without replacing secrets."""
import argparse
import os
from pathlib import Path
import secrets


def initialize(target: Path) -> bool:
    lines = [
        f"APP_UID={os.getuid() if hasattr(os, 'getuid') and os.getuid() else 10001}",
        f"APP_GID={os.getgid() if hasattr(os, 'getgid') and os.getgid() else 10001}",
        "APP_STORAGE_USER=zhengqinyun",
        "# APP_DATA_DIR=/colddata/SCigblast/platform/storage",
        "ANALYSIS_FLAVOR=full",
        "ANALYSIS_RUNTIME_IMAGE=immune-analysis-runtime:3.20-v1",
        "APP_DOCKERFILE=docker/app/Dockerfile.analysis",
        "FLASK_CONFIG=internal",
        "AUTH_REGISTER_ENABLED=false",
        "HTTP_BIND=127.0.0.1",
        "HTTP_PORT=8080",
        "API_CPUS=2",
        "API_MEMORY_LIMIT=2g",
        "WORKER_CPUS=4",
        "WORKER_MEMORY_LIMIT=8g",
        "ANALYSIS_NUM_THREADS=1",
        "ANALYSIS_TIMEOUT_SECONDS=7200",
        "WORKER_STOP_GRACE_PERIOD=2m",
    ]
    lines.extend(f"{key}={secrets.token_hex(32)}" for key in (
        "SECRET_KEY", "MYSQL_PASSWORD", "MYSQL_ROOT_PASSWORD", "MONGO_PASSWORD"
    ))
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        print("配置文件已存在，保留原有内容。")
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")
    print("已生成完整分析环境配置，密钥未显示。")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / ".env")
    initialize(parser.parse_args().output)
