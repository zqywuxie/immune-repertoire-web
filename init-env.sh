#!/usr/bin/env bash
set -Eeuo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$script_dir"
trap 'printf "更新或初始化失败（第 %s 行），尚未执行部署。\n" "$LINENO" >&2' ERR
usage() {
  printf '用法：bash init-env.sh [分支]\n拉取 origin 当前分支后准备 .env；编辑参数后再执行 bash deploy.sh。\n'
}
if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
if (( $# > 1 )); then usage >&2; exit 2; fi
command -v git >/dev/null || { printf '请先安装 Git。\n' >&2; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null
branch="$(git symbolic-ref --quiet --short HEAD)" || { printf '当前处于游离提交，请先检出部署分支。\n' >&2; exit 1; }
if [[ -n ${1:-} && $1 != "$branch" ]]; then
  printf '当前分支是 %s，与指定分支 %s 不一致；请先手动切换分支。\n' "$branch" "$1" >&2
  exit 1
fi
if [[ -n $(git status --porcelain --untracked-files=normal) ]]; then
  printf '工作区存在未提交或未跟踪文件，请先处理后再更新；不会覆盖本地修改。\n' >&2
  exit 1
fi

# 拉取后重新执行新版本脚本，避免使用更新前的部署逻辑。
revision="$(git rev-parse HEAD)"
if [[ ${IMMUNE_INIT_PULLED_REVISION:-} != "$revision" ]]; then
  printf '正在拉取 origin/%s…\n' "$branch"
  git pull --ff-only origin "$branch"
  export IMMUNE_INIT_PULLED_REVISION="$(git rev-parse HEAD)"
  exec bash "$script_dir/init-env.sh" "$branch"
fi
unset IMMUNE_INIT_PULLED_REVISION

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
