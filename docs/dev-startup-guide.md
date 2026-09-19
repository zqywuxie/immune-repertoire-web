# Docker 开发与启动指南

应用、分析、测试和前端构建均在 Linux 容器内执行。宿主机负责编辑源码和管理 Docker。
当前部署入口为 `compose.docker.yml`；旧 `docker-compose.yml` 仅保留历史基础设施配置。
项目路径可自行选择，无需保留 Windows 绝对路径。

## 首次启动

在项目根目录初始化独立配置，已有 `.env.docker` 会保持原样。

Windows PowerShell：

```powershell
rtk proxy powershell -NoProfile -File docker/init-env.ps1
rtk docker compose --env-file .env.docker -f compose.docker.yml up -d --build --wait
```

Linux：

```bash
rtk docker run --rm --user "$(rtk proxy id -u):$(rtk proxy id -g)" --mount "type=bind,source=$PWD,target=/workspace" python:3.11-slim-bookworm python /workspace/docker/init_env.py
rtk docker compose --env-file .env.docker -f compose.docker.yml up -d --build --wait
```

默认访问 `http://127.0.0.1:8080`。内部共享模式使用 `FLASK_CONFIG=internal`，无需登录和注册。
数据库不发布宿主机端口，应用通过 `mysql`、`mongodb`、`redis` 容器服务名连接。
服务器远程入口、配置变量、备份与迁移参见 [Docker 部署说明](docker-deployment.md)。
旧 root 镜像的数据卷升级需要先按部署说明完成 `volume-init`，再启动普通用户版本。

## 修改与构建

前端源码位于 `frontend/src`；Flask 接口位于 `flask_app/routes`；分析服务位于 `flask_app/services`。
工作进程入口为 `analysis_workers.worker_main`。

```bash
rtk docker compose --env-file .env.docker -f compose.docker.yml build web
rtk docker compose --env-file .env.docker -f compose.docker.yml build api
```

依赖变更写入依赖清单或 Dockerfile，然后重建镜像。不要在宿主机安装项目 Python、R 或 Node 依赖。
接口与工作进程共享应用镜像；重建后应统一更新两者，避免接口与计算代码版本不一致。
更新前等待正在执行的任务结束，迁移或恢复数据前完成备份。

## 容器内验证

前端测试容器包含独立依赖，先构建后运行：

```bash
rtk docker compose --env-file .env.docker -f compose.docker.yml --profile test build frontend-test
rtk docker compose --env-file .env.docker -f compose.docker.yml --profile test run --rm frontend-test
```

后端示例使用临时文件系统，不挂载业务数据卷；普通应用用户需要可写目录：

```bash
rtk docker run --rm --tmpfs /app/flask_app/data:uid=10001,gid=10001 --tmpfs /app/tmp:uid=10001,gid=10001 -e FLASK_CONFIG=testing -e JOB_QUEUE=threadpool immune-platform-api:full python -B -m pytest flask_app/tests/test_input_quality.py flask_app/tests/test_result_table.py -q -p no:cacheprovider
```

真实队列回归使用独立 Redis 测试库及唯一测试队列，不能指向生产队列或执行 FLUSHDB。
已有验证范围和未完成事项记录在 [项目输入工作流进度](superpowers/project-input-workflow-progress.md)。

## 查看状态与日志

```bash
rtk docker compose --env-file .env.docker -f compose.docker.yml ps
rtk docker compose --env-file .env.docker -f compose.docker.yml logs --tail 100 api worker
rtk docker compose --env-file .env.docker -f compose.docker.yml exec worker python -m analysis_workers.healthcheck
```

常驻容器日志已配置轮转。应用数据、上传、分析产物和参考资源属于持久数据，不是可随意删除的缓存。
日常停止使用 `stop`，不要使用 `down -v` 删除数据卷。

## 常见问题

- 页面接口错误：先查看 api 健康状态与日志，再确认数据库服务健康。
- 任务一直排队：查看当前 worker 的健康检查、队列连接和实际任务状态。
- 写入被拒绝：检查是否使用普通用户镜像以及应用卷是否已初始化为 UID/GID 10001。
- 大型分析被终止：核对任务错误、容器内存上限与超时；资源变量见部署说明。
- 修改后页面未更新：确认已构建并重新创建 web 容器；绑定 Windows 源码的临时开发容器可能需要重启才能读取变化。
