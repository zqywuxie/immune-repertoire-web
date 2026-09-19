#!/usr/bin/env bash
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$script_dir"
if [[ -e .env ]]; then
  printf '.env 已存在，保留全部配置和密钥。请编辑后再运行 bash deploy.sh。\n'
  exit 0
fi
if [[ -f .env.docker ]]; then
  # 旧配置迁移也只发生在显式初始化时。
  (umask 077; set -o noclobber; cat -- .env.docker > .env)
  printf '已从 .env.docker 创建 .env，旧文件和密钥保留。\n'
else
  command -v docker >/dev/null || { printf '请先安装 Docker。\n' >&2; exit 1; }
  docker info >/dev/null
  docker run --rm --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$script_dir,target=/workspace" \
    python:3.11-slim-bookworm python /workspace/docker/init_env.py
fi
printf '初始化完成，尚未部署。请编辑 .env 中 APP_DATA_DIR、HTTP_PORT、APP_UID、APP_GID，再执行 bash deploy.sh。\n'
