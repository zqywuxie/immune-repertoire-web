> 后续环境统一使用 Docker。应用部署请使用 [Docker 部署说明](docs/docker-deployment.md) 与 `compose.docker.yml`；原 `docker-compose.yml` 保留为历史基础服务配置。

# 免疫组库分析平台

面向科研用户的免疫组库分析应用。React 前端提供项目、数据集、分析向导和结果浏览；Flask 提供当前本地运行的 API 与分析服务。仓库同时保留 FastAPI 后端和分析 worker，具体边界见[当前架构](docs/architecture/current-system.md)。

## 启动与分析

在项目根目录执行 `rtk docker compose --env-file .env -f compose.docker.yml up -d --build --wait`，访问 `http://127.0.0.1:8080`。首次部署的环境文件生成、完整分析镜像、数据迁移与测试见[Docker 部署说明](docs/docker-deployment.md)。

Profile 箱线图流程：

1. 登录并创建项目，打开“分析向导”。
2. 在第一步选择项目，点击“上传数据”，上传包含样本、分组和数值指标的 Profile CSV/TSV/Excel；无需 PEP。
3. 选择保存的数据集，检查样本和列预览。
4. 选择 Profile 分析，明确设置分组列、指标起止列及组别顺序。
5. 开始运行，完成后点击“查看结果”，打开报告或下载图像、CSV 和 ZIP。

PEP、Transcriptome 可根据其他分析的需要补充。真实文件在服务器处理；失败上传保留所选文件供修正后重试。

## 目录与文档

- `frontend/`：React + TypeScript + Vite。
- `flask_app/`：当前 API、分析服务、数据模型、旧页面与测试。
- `backend-api/`：FastAPI API 与任务/资产基础设施。
- `analysis_workers/`：后台分析 worker。
- [当前架构与模块边界](docs/architecture/current-system.md)
- [开发启动指南](docs/dev-startup-guide.md)
- [本地 Docker 数据库](LOCAL_DOCKER.md)、[数据库部署](DEPLOY_DATABASE.md)
- [外置数据与目录联接](docs/local-data-storage.md)
- [迁移进度](docs/migration-progress.md)
- [历史架构与计划](docs/archive/README.md)

`docs/api/module-manifest.yaml` 是运行时模块注册表，不能按文档清理删除。`docs/superpowers/` 中未完成的计划继续保留。

## 验证

```powershell
rtk docker compose --env-file .env -f compose.docker.yml run --rm frontend-test
rtk docker run --rm --network immune-platform_default --tmpfs /app/flask_app/data --tmpfs /app/tmp -e FLASK_CONFIG=testing -e JOB_QUEUE=threadpool -e REDIS_URL=redis://redis:6379/15 immune-platform-api:full python -B -m pytest flask_app/tests/ analysis_workers/tests/ -q
```

本地项目位于 `E:\Desktop\project\immune-repertoire-web`，大数据位于同级 `immune-repertoire-web-data`。目录联接用于保留数据访问；清理缓存时不能跨越这些联接。
