#!/usr/bin/env bash
set -Eeuo pipefail

trap 'printf "部署失败（第 %s 行）。请检查错误；数据卷及现有配置未删除。\n" "$LINENO" >&2' ERR

usage() {
  printf '用法：bash deploy.sh [分支]\n默认更新当前分支；远端固定为 origin。需安装 Git、Docker 和 Docker Compose 插件。\n'
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

# 拉取后重新执行新版本脚本，避免使用更新前的部署逻辑。
revision="$(git rev-parse HEAD)"
if [[ ${IMMUNE_DEPLOY_PULLED_REVISION:-} != "$revision" ]]; then
  printf '正在拉取 origin/%s…\n' "$branch"
  git pull --ff-only origin "$branch"
  export IMMUNE_DEPLOY_PULLED_REVISION="$(git rev-parse HEAD)"
  exec bash "$script_dir/deploy.sh" "$branch"
fi
unset IMMUNE_DEPLOY_PULLED_REVISION

if [[ ! -f .env ]]; then
  printf '缺少 .env。请先执行 bash init-env.sh，编辑数据路径、端口及用户编号后，再运行 bash deploy.sh。\n' >&2
  exit 1
fi
compose=(docker compose --env-file .env -f compose.docker.yml)
"${compose[@]}" config --quiet
printf '正在复用分析基础镜像构建业务代码和前端；依赖变化时请先更新基础镜像。\n'
"${compose[@]}" build api web
printf '正在启动服务并等待健康检查…\n'
"${compose[@]}" up -d --wait --wait-timeout 300
"${compose[@]}" ps
printf '部署完成，提交：%s\n默认入口：http://127.0.0.1:8080；实际地址以 .env 为准。\n' "$(git rev-parse --short HEAD)"
