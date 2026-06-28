# Immune Repertoire Web 前后端分离与平台化重构方案

## 1. 背景与目标

当前项目是以 Flask 为中心的单机架构：页面渲染、API、长任务调度、分析计算、文件读写、结果注册、数据库访问大多集中在同一个应用进程内。这个模式适合早期快速集成功能，但随着 Script Hub、项目管理、PPT/PDF 处理、统计分析、缓存资产、用户权限和结果管理继续增长，会逐渐出现以下问题：

- Web 请求、后台计算和文件操作耦合过深，单个模块异常容易影响整个平台。
- 长任务生命周期分散在不同 route/service 中，任务状态、取消、重试和恢复难统一。
- 数据库查询容易出现大 JSON 字段、无分页列表、排序内存不足等问题。
- 前端页面和后端模板耦合，复杂交互难维护，也不利于后续 UI 迭代。
- Python 适合分析计算，但不宜继续承担全部平台架构职责。

本方案目标不是一次性重写，而是以“渐进式迁移”的方式，将系统重构为：

- 独立前端应用
- 独立 API 平台
- Python 分析 worker
- 统一任务系统
- 统一资产与结果存储
- 更可治理的数据库访问层

## 2. 推荐目标架构

```text
immune-repertoire-web/
  frontend/
    React or Next.js
    项目管理、Script Hub、结果查看、任务监控、设置页

  backend-api/
    FastAPI or NestJS
    用户、项目、资产、任务、权限、结果查询、OpenAPI

  analysis-workers/
    Python
    heatmap、treemap、chord、statistical、PPT/PDF、Script Hub modules

  database/
    PostgreSQL or MySQL
    结构化元数据、用户、项目、资产索引、任务状态

  object-storage/
    Local/MinIO/S3 abstraction
    原始文件、结果目录、HTML report、PNG/PDF/PPT/ZIP

  queue/
    Redis + Celery/RQ/Arq
    后台任务投递、状态更新、取消、重试
```

### 2.1 分层职责

| 层 | 推荐技术 | 职责 |
|---|---|---|
| Frontend | Next.js 或 Vite + React | 页面、交互、上传、任务状态展示、结果查看 |
| API Platform | FastAPI 优先；复杂平台化可选 NestJS | 认证、权限、项目、资产、任务提交、结果查询 |
| Analysis Workers | Python | 复用现有分析服务，执行长任务和生成结果 |
| Queue | Redis + Celery/RQ/Arq | 解耦 Web 请求与分析计算 |
| Database | PostgreSQL 优先，MySQL 可过渡 | 存储结构化元数据和任务状态 |
| Storage | Local adapter -> MinIO/S3 | 存储大文件和分析输出 |

## 3. 技术选型建议

### 3.1 前端

推荐优先级：

1. Next.js：适合后续有登录、权限、项目门户、复杂页面和部署要求的场景。
2. Vite + React：适合快速迁移当前 Bootstrap/Jinja 页面，工程复杂度更低。
3. Vue：如果团队已有 Vue 经验，也可采用，但当前项目没有 Vue 基础，迁移收益不明显。

建议第一阶段选择 `Vite + React + TypeScript` 或 `Next.js + TypeScript`。如果短期目标是快速拆页面，Vite 更轻；如果长期目标是平台化，Next.js 更完整。

### 3.2 API 平台

推荐两条路线：

| 路线 | 优点 | 风险 |
|---|---|---|
| FastAPI | 迁移成本低，Python 服务和模型复用容易，OpenAPI 友好 | 平台工程能力需要团队主动规范 |
| NestJS | 平台边界、模块化、权限、DTO、依赖注入更成熟 | 需要 Node/TypeScript 后端能力，和 Python 分析层需 RPC/队列解耦 |

当前项目算法和分析服务大量使用 Python，因此建议先采用 FastAPI 作为 API 平台，避免过早跨语言重写。后续如果用户、组织、审计、权限、插件市场等平台能力显著增长，再评估 NestJS。

### 3.3 分析计算

Python 分析服务应保留。重构目标不是重写算法，而是让 Python 从“Web 平台进程”转变为“分析 worker 进程”。

现有服务可以逐步迁移：

- `similarity_heatmap_report_service.py`
- `treemap_report_service.py`
- `chord_report_service.py`
- `pipeline_comparison_integration_service.py`
- `statistical_analysis_service.py`
- `boxplot_service.py`
- `pep_analysis_service.py`
- `umap_service.py`
- `volcano_service.py`
- `ppt_service.py`
- `pdf_extractor.py`

## 4. 核心架构改造

### 4.1 从 route 直接执行改为统一任务模型

当前模式：

```text
POST /api/script-hub/<module>/run
  -> route 校验参数
  -> route 或 service 启动线程/执行分析
  -> 内存任务表或分散 job service 记录状态
  -> 前端轮询模块专属 task endpoint
```

目标模式：

```text
POST /api/jobs
  -> API 校验参数和权限
  -> 创建 analysis_jobs 记录
  -> 投递 queue
  -> 返回 job_id

worker
  -> 拉取 job
  -> 解析 input assets
  -> 执行分析
  -> 写入 outputs
  -> 注册 result assets
  -> 更新 job status/progress/result

GET /api/jobs/<job_id>
  -> 返回统一任务状态

GET /api/jobs/<job_id>/results
  -> 返回统一结果资产
```

统一任务字段建议：

```text
analysis_jobs
  id
  job_type
  module
  status
  progress
  stage
  detail
  payload
  result
  error
  cancel_requested
  project_id
  user_id
  created_at
  updated_at
  started_at
  completed_at
```

任务状态建议统一为：

```text
queued -> running -> completed
queued -> running -> failed
queued -> running -> cancelled
```

### 4.2 统一资产模型

当前 `ProjectAsset` 已经是资产模型雏形，但仍存在以下问题：

- `storage_path` 直接存 Windows 本地路径，迁移和部署不灵活。
- `metadata_json` 过重，列表查询容易读取大字段。
- SQL 资产、Mongo 缓存和文件系统结果之间边界不清。
- 结果注册、缓存资产、输入资产没有统一生命周期。

建议目标模型：

```text
assets
  id
  project_id
  asset_type
  logical_name
  storage_uri
  mime_type
  size
  checksum
  status
  created_by
  created_at
  updated_at

asset_metadata
  asset_id
  metadata_json

job_assets
  job_id
  asset_id
  role
```

`storage_uri` 示例：

```text
local://projects/{project_id}/assets/profile/Profile_All.csv
local://results/{user_id}/script_hub/{job_id}/viewer.html
minio://immune-repertoire/projects/{project_id}/assets/...
s3://bucket/projects/{project_id}/assets/...
```

资产类型建议统一：

```text
input:
  pep
  profile
  transcriptome
  sample_summary
  ppt_template
  pdf_source

cache:
  cached_usage
  cached_step34

result:
  processed_result
  report_html
  plot_png
  table_csv
  bundle_zip
  ppt_output
```

### 4.3 数据库访问治理

本次 MySQL `Out of sort memory` 暴露的不是单点问题，而是数据访问层需要治理。

强制规则：

- 所有列表接口必须分页，禁止无限制 `.all()`。
- 列表查询不读取大 JSON 字段，详情接口再读取 metadata。
- 所有列表查询必须有明确排序索引。
- 排序字段必须和过滤字段组成复合索引。
- 大结果、报告内容、表格内容不进主业务表。
- metadata 超过一定体积后拆到 `asset_metadata` 或对象存储。
- API 层禁止直接拼装复杂 ORM 查询，统一走 repository/service。

建议索引：

```text
assets(project_id, asset_type, created_at)
assets(project_id, created_at)
assets(project_id, status, created_at)
analysis_jobs(project_id, module, status, created_at)
analysis_jobs(user_id, status, created_at)
job_assets(job_id, role)
```

列表接口示例：

```http
GET /api/projects/{project_id}/assets?type=profile&page=1&page_size=50
GET /api/jobs?project_id=xxx&status=running&page=1&page_size=50
GET /api/projects/{project_id}/results?module=pep-analysis&page=1&page_size=20
```

### 4.4 结果读取与静态文件服务

当前结果路径通常由 Flask route 根据本地路径直接 `send_file`。目标架构应改成：

```text
GET /api/assets/{asset_id}/download
GET /api/assets/{asset_id}/preview
GET /api/jobs/{job_id}/files/{relative_path}
```

API 层只负责权限校验和签名 URL/文件流转发，实际文件存储由 storage adapter 管理。

Storage adapter 接口建议：

```python
class StorageAdapter:
    def put_file(self, local_path: Path, key: str) -> str: ...
    def get_file(self, storage_uri: str) -> Path | BinaryIO: ...
    def exists(self, storage_uri: str) -> bool: ...
    def delete(self, storage_uri: str) -> None: ...
    def presign(self, storage_uri: str, expires: int = 3600) -> str: ...
```

第一阶段可以实现 `LocalStorageAdapter`，后续切换到 MinIO/S3。

## 5. 迁移路线

### Phase 0：冻结边界与补文档

目标：不大改代码，先明确系统边界。

任务：

- 梳理现有 API endpoint。
- 标记哪些 API 是前端迁移必须保留的稳定接口。
- 标记哪些 route 是旧 Jinja 页面专用接口。
- 为项目、资产、任务、结果定义 OpenAPI 草案。
- 确定前端技术栈和目录结构。

产出：

- `docs/architecture/frontend-backend-separation-refactor.md`
- `docs/api/openapi-draft.yaml`
- `docs/architecture/domain-model.md`

### Phase 1：前端独立化

目标：新前端先接管高价值页面，后端仍可使用 Flask。

优先迁移页面：

1. 项目列表
2. 项目详情
3. Script Hub
4. 任务列表
5. 结果查看

建议目录：

```text
frontend/
  src/
    app/
    pages/
    features/
      projects/
      assets/
      script-hub/
      jobs/
      results/
    shared/
      api/
      components/
      hooks/
      types/
```

API client 统一封装：

```text
frontend/src/shared/api/client.ts
frontend/src/shared/api/projects.ts
frontend/src/shared/api/assets.ts
frontend/src/shared/api/jobs.ts
frontend/src/shared/api/scriptHub.ts
```

### Phase 2：统一任务系统

目标：把分散的 task pattern 收敛到统一 jobs API。

优先接入：

- Script Hub modules
- combined analysis
- treemap
- chord
- pipeline comparison
- PPT/PDF processing

新增接口：

```http
POST /api/jobs
GET /api/jobs
GET /api/jobs/{job_id}
POST /api/jobs/{job_id}/cancel
GET /api/jobs/{job_id}/events
GET /api/jobs/{job_id}/results
```

前端轮询可先保留，后续升级 SSE：

```text
polling -> Server-Sent Events -> WebSocket
```

### Phase 3：Worker 化分析服务

目标：Web API 不再直接执行分析。

建议步骤：

1. 引入 Redis。
2. 选择 Celery/RQ/Arq。
3. 为每个分析模块封装 worker task。
4. 任务输入只接收 `job_id`。
5. worker 从数据库读取 payload 和 assets。
6. worker 写回 progress/result/assets。

Worker 任务示例：

```text
run_script_hub_job(job_id)
run_treemap_job(job_id)
run_chord_job(job_id)
run_ppt_job(job_id)
run_combined_analysis_job(job_id)
```

### Phase 4：资产存储抽象

目标：从本地绝对路径迁移到 `storage_uri`。

步骤：

1. 保留现有 `storage_path`，新增 `storage_uri`。
2. 新上传文件同时写入两列。
3. 新结果优先写 `storage_uri`。
4. 读取时优先 `storage_uri`，缺失时 fallback 到 `storage_path`。
5. 批量迁移历史资产。
6. 废弃直接依赖 Windows path 的逻辑。

当前过渡实现：在不触发表结构迁移的前提下，先由 `ProjectAsset.metadata_json.storage_uri` 承载 `local://` URI，并在 API 响应中映射为顶层 `storage_uri`；读取文件时优先解析该 URI，再 fallback 到历史 `storage_path`。

### Phase 5：API 平台替换

目标：从 Flask 单体迁到 FastAPI 或 NestJS。

推荐 FastAPI 迁移顺序：

1. Auth/User
2. Projects
3. Assets
4. Jobs
5. Results
6. Script Hub job submission
7. Legacy Flask 只保留旧页面和未迁移模块

最终目标：

```text
frontend -> backend-api -> database/storage/queue
analysis-workers -> database/storage/queue
legacy-flask -> gradually retired
```

## 6. 风险与应对

| 风险 | 说明 | 应对 |
|---|---|---|
| 一次性重写失败 | 当前分析功能多，重写面过大 | 绞杀者迁移，旧系统保持可用 |
| 文件路径迁移复杂 | 现有大量 Windows 绝对路径 | storage adapter + fallback |
| 长任务状态不一致 | 多模块 task pattern 分散 | 统一 jobs 表和 worker 状态协议 |
| 前后端接口漂移 | 新前端依赖接口稳定性 | OpenAPI + typed client |
| 数据库性能继续恶化 | 列表读取大 JSON 或无分页 | repository/service 统一治理 |
| Python/Node 混合复杂 | 跨语言增加部署成本 | 第一阶段优先 FastAPI + Python worker |

## 7. 推荐落地优先级

近期优先做：

1. 所有项目资产和结果列表接口分页。
2. 所有 Script Hub 资产读取走统一 `ProjectAssetService`。
3. 新建 `frontend/`，先迁移项目详情和 Script Hub。
4. 建统一 `jobs` API，前端任务轮询改读统一 job endpoint。
5. 把新增分析模块默认接入 `analysis_jobs`，不再新增模块专属内存 task。

中期做：

1. 引入 Redis + worker。
2. 把 treemap/chord/combined/script-hub 长任务 worker 化。
3. 拆 `metadata_json` 大字段读取路径。
4. 引入 storage adapter。
5. 输出 OpenAPI 并生成前端类型。

长期做：

1. 迁移 Flask API 到 FastAPI。
2. 旧 Jinja 页面下线。
3. 本地文件存储迁移到 MinIO/S3。
4. 数据库迁移到 PostgreSQL 或治理后的 MySQL。
5. 支持多用户、多项目、多 worker 横向扩展。

## 8. 建议的最终目录结构

```text
immune-repertoire-web/
  frontend/
    package.json
    src/

  backend-api/
    pyproject.toml
    app/
      main.py
      api/
      core/
      models/
      schemas/
      services/
      repositories/

  analysis-workers/
    pyproject.toml
    workers/
      main.py
      tasks/
      services/

  shared/
    openapi/
    schemas/

  legacy-flask/
    flask_app/

  docs/
    architecture/
    api/
    migration/
```

在迁移初期可以不移动 `flask_app/`，只新增 `frontend/` 和 `docs/`。等 API 平台和 worker 基本稳定后，再考虑目录重组。

## 9. 关键判断

这个项目真正需要保护的是分析能力、项目资产和结果数据，而不是当前 Flask 单体形态。最稳的策略是：

```text
先拆前端
再统一任务
再 worker 化分析
再抽象存储
最后替换平台 API
```

Python 继续负责科学计算和图表生成是合理的；平台层则应逐步转向更清晰的 API、任务、资产和权限架构。
