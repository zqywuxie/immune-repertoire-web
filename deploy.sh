#!/usr/bin/env bash
set -Eeuo pipefail

trap 'printf "部署失败（第 %s 行）。请检查错误；数据卷及现有配置未删除。\n" "$LINENO" >&2' ERR

usage() {
  printf '用法：bash deploy.sh [分支]\n只构建和部署当前代码，不拉取 Git。请先运行 bash init-env.sh 并编辑 .env；可选分支参数只校验当前分支。\n'
}
if [[ ${1:-} == --help || ${1:-} == -h ]]; then usage; exit 0; fi
if (( $# > 1 )); then usage >&2; exit 2; fi
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd -- "$script_dir"
for executable in git docker; do
  command -v "$executable" >/dev/null || { printf '缺少命令：%s\n' "$executable" >&2; exit 1; }
done
git rev-parse --is-inside-work-tree >/dev/null
branch="$(git symbolic-ref --quiet --short HEAD)" || { printf '当前处于游离提交，请先检出部署分支。\n' >&2; exit 1; }
if [[ -n ${1:-} && $1 != "$branch" ]]; then
  printf '当前分支是 %s，与指定分支 %s 不一致；请先手动切换分支。\n' "$branch" "$1" >&2
  exit 1
fi
if [[ -n $(git status --porcelain --untracked-files=normal) ]]; then
  printf '工作区存在未提交或未跟踪文件，请先处理后再部署；不会覆盖本地修改。\n' >&2
  exit 1
fi
docker info >/dev/null
docker compose version >/dev/null

if [[ ! -f .env ]]; then
  printf '缺少 .env。请先执行 bash init-env.sh，编辑数据路径、端口及用户编号后，再运行 bash deploy.sh。\n' >&2
  exit 1
fi
compose=(docker compose --env-file .env -f compose.docker.yml)
maintenance_active=false
maintenance_token="deploy-$$-$RANDOM"
release_maintenance() {
  local status=$?
  if [[ $maintenance_active == true ]]; then
    if ! "${compose[@]}" exec -T api python -m flask_app.services.deployment_maintenance disable --token "$maintenance_token"; then
      if ! "${compose[@]}" run --rm --no-deps api python -m flask_app.services.deployment_maintenance disable --token "$maintenance_token"; then
        printf '维护状态解除失败，请恢复服务后执行：docker compose --env-file .env -f compose.docker.yml exec -T api python -m flask_app.services.deployment_maintenance disable --token %s\n' "$maintenance_token" >&2
        status=1
      fi
    fi
  fi
  exit "$status"
}
trap release_maintenance EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"${compose[@]}" config --quiet
printf '正在复用分析基础镜像构建业务代码和前端；依赖变化时请先更新基础镜像。\n'
"${compose[@]}" build api web
# Check immediately before replacing services; first deployments have no API.
running_api="$("${compose[@]}" ps --status running -q api)"
if [[ -n "$running_api" ]]; then
  if "${compose[@]}" exec -T api test -f /app/flask_app/services/deployment_maintenance.py; then
    "${compose[@]}" exec -T api python -m flask_app.services.deployment_maintenance enable --token "$maintenance_token"
    maintenance_active=true
  else
    printf '当前运行版本尚不支持自动维护，请在本次升级期间暂停提交新分析。\n'
  fi
  printf '正在检查活动任务；尚有任务时退出部署并恢复提交…\n'
  "${compose[@]}" exec -T api python - < docker/app/check_active_jobs.py
fi
printf '正在按 APP_UID/APP_GID 初始化应用数据目录权限…\n'
"${compose[@]}" --profile operations run --rm --no-deps volume-init
printf '正在启动服务并等待健康检查…\n'
"${compose[@]}" up -d --wait --wait-timeout 300
"${compose[@]}" ps
if [[ $maintenance_active == true ]]; then
  "${compose[@]}" exec -T api python -m flask_app.services.deployment_maintenance disable --token "$maintenance_token"
  maintenance_active=false
fi
printf '部署完成，提交：%s\n默认入口：http://127.0.0.1:8080；实际地址以 .env 为准。\n' "$(git rev-parse --short HEAD)"
