# 全栈重构执行计划与完成记录

> 创建日期：2026-06-29
> 依据文档：`enterprise-analysis-platform-refactor-optimization.md`、`frontend-backend-separation-refactor.md`、`migration-progress.md`
> 执行规则：每完成一项实施任务，必须在本文末尾“执行记录”追加日期、范围、改动、验证、提交信息和后续风险。

## 1. 执行目标

把当前 Flask 单体逐步推进为企业级分析平台架构：

```text
frontend React SPA
  -> backend-api FastAPI
  -> SQL metadata / object storage / Redis queue
  -> analysis-workers Python
```

核心完成标准：

| 层 | 完成标准 |
|---|---|
| Frontend | 独立 SPA 只依赖稳定 API；API 类型由 OpenAPI 生成；任务、资产、结果页面可独立运行 |
| Backend API | FastAPI 覆盖 auth/projects/assets/jobs/results/system；具备权限、错误治理、repository/service 层 |
| Workers | 所有长任务只接收 `job_id`；统一写回 progress、result、outputs、registered assets |
| Storage | 结果和输入都通过 `storage_uri` 访问；本地路径只作为兼容字段存在 |
| Database | 列表分页、索引明确、不读取大 JSON；资产、任务、结果关系可追溯 |
| Operations | Docker Compose 能启动 API、worker、Redis、DB、MinIO；健康检查覆盖关键依赖 |
| Documentation | OpenAPI、执行计划、迁移进度、部署说明持续同步 |

## 2. 全栈设计

### 2.1 前端设计

目标目录：

```text
frontend/src/
  app/
    App.tsx
    routes.tsx
  features/
    dashboard/
    database/
    script-hub/
    jobs/
    results/
    settings/
  shared/
    api/
      client.ts
      generated/
      projects.ts
      assets.ts
      jobs.ts
    components/
    hooks/
    types/
```

设计要求：

- API 类型由 OpenAPI 生成，手写类型只保留 UI view model。
- 任务状态优先使用 SSE，保留 polling fallback。
- 模块入口来自后端 module manifest，不在前端硬编码分析模块。
- 结果查看器按 `kind` 渲染：HTML、PNG、CSV、ZIP、PPT、PDF。
- 前端必须提供任务控制台、资产详情、结果详情、运行历史和错误详情。

### 2.2 Backend API 设计

目标目录：

```text
backend-api/app/
  api/
    auth.py
    projects.py
    assets.py
    jobs.py
    results.py
    system.py
  core/
    auth.py
    config.py
    database.py
    errors.py
    storage.py
  repositories/
    projects.py
    assets.py
    jobs.py
    users.py
  services/
    auth_service.py
    asset_service.py
    job_service.py
    result_service.py
  schemas/
    domain.py
```

设计要求：

- Route 只处理 HTTP 入参、依赖注入和 response model。
- Repository 负责 SQL 查询，不在 route 中写 `SELECT *` 或列下标映射。
- Service 负责权限、业务规则、状态机和跨表聚合。
- Auth 第一阶段采用迁移期 `API_AUTH_TOKEN`，后续切换用户表/JWT/RBAC。
- Jobs API 创建任务后只入队 `module + job_id`。

### 2.3 Worker 设计

目标目录：

```text
analysis_workers/
  main.py
  registry.py
  context.py
  results.py
  tasks/
    charts.py
    treemap.py
    chord.py
    heatmap.py
    statistical.py
    ppt.py
```

设计要求：

- Worker 函数签名统一为 `run_xxx_job(job_id: str) -> dict`。
- Worker 必须通过数据库读取 payload、project_id、user_id。
- Worker 必须通过统一 helper 写 progress、result、outputs、assets。
- Worker 不直接依赖 Flask request context。
- 对旧 Flask endpoint 的桥接允许暂存，但必须被标记为 legacy bridge。

### 2.4 存储与资产设计

目标模型：

```text
assets
  id
  project_id
  asset_type
  logical_name
  storage_uri
  legacy_storage_path
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

设计要求：

- API response 优先返回 `storage_uri`。
- Preview/download 统一从 `/api/assets/{asset_id}/preview|download` 进入。
- 新结果必须注册为 asset，并和 job 建立关系。
- MinIO/S3 部署后不得暴露本地 Windows 路径给前端。

### 2.5 运维与可观测性设计

目标能力：

- `/api/health` 返回 API、DB、Redis、Storage 状态。
- `/api/metrics` 返回任务计数、失败率、队列长度、平均耗时。
- Docker Compose profiles：`api`、`worker`、`storage`、`dev`。
- 每个 job history 使用标准事件名：`queued`、`started`、`progress`、`output_registered`、`completed`、`failed`。

## 3. 执行阶段

### Phase A：API 平台硬化

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| A1 | FastAPI Auth/User bridge | 已完成 | `API_AUTH_TOKEN` 可保护业务 API；`/api/auth/me` 返回当前 principal |
| A2 | FastAPI repository 层 | 待执行 | route 不再包含 raw SQL 查询和列下标映射 |
| A3 | Project/Asset/Job service 层 | 待执行 | 权限、分页、排序、404、错误统一进入 service |
| A4 | OpenAPI 契约测试 | 待执行 | 后端 response 与 OpenAPI schema 有自动校验 |

### Phase B：Worker 结果协议闭环

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| B1 | `analysis_workers/results.py` | 待执行 | 提供注册 output asset 的统一 helper |
| B2 | Worker result envelope | 待执行 | 所有 worker 返回统一 `outputs/metrics/summary` |
| B3 | Job results 聚合重构 | 待执行 | `/api/jobs/{job_id}/results` 从 job result + assets 聚合 |
| B4 | Legacy bridge 标记 | 待执行 | 旧 endpoint 桥接路径在代码和文档中明确标记 |

### Phase C：模块插件化

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| C1 | Module manifest schema | 待执行 | 定义 `key/label/category/input_schema/output_schema/worker/ui_entry` |
| C2 | Module registry loader | 待执行 | 后端从 manifest 生成 `/api/jobs/modules` |
| C3 | Frontend module form | 待执行 | 前端按 manifest 渲染参数入口 |

### Phase D：资产治理与存储

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| D1 | checksum/lineage 字段迁移 | 待执行 | assets/job_assets 关系可追踪 |
| D2 | MinIO/S3 compose profile | 待执行 | 本地可一键启动对象存储 |
| D3 | Storage health check | 待执行 | `/api/health` 能检测 storage backend |

### Phase E：前端契约化

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| E1 | OpenAPI TS type generation | 待执行 | `frontend/src/shared/api/generated` 自动生成 |
| E2 | API client 替换手写类型 | 待执行 | Project/Asset/Job 类型来自 generated schema |
| E3 | 结果查看器完善 | 待执行 | HTML/PNG/CSV/ZIP/PPT/PDF 输出按 kind 渲染 |

## 4. 执行记录格式

每次完成任务后，在“执行记录”追加：

```text
### YYYY-MM-DD / ID / 标题
- 状态：完成 / 部分完成 / 回滚
- 改动：
- 验证：
- 提交：
- 后续：
```

## 5. 当前执行队列

1. A1 FastAPI Auth/User bridge
2. B1 Worker output registration helper
3. A2 FastAPI repository 层
4. C1 Module manifest schema
5. E1 OpenAPI TS type generation

## 6. 执行记录

### 2026-06-29 / A1 / FastAPI Auth/User bridge

- 状态：完成
- 改动：
  - 新增 `backend-api/app/core/auth.py`，提供迁移期 `ApiPrincipal` 和 `require_current_user`。
  - 新增 `API_AUTH_TOKEN` 配置；默认空 token 时保持本地开发兼容。
  - `/api/auth/me` 返回当前迁移期 principal。
  - Projects、Assets、Jobs 稳定业务路由接入认证依赖。
  - 补充 FastAPI 测试，覆盖默认兼容模式、401、Bearer token、`X-API-Key`。
- 验证：
  - `python -m py_compile backend-api\app\core\auth.py backend-api\app\core\config.py backend-api\app\api\auth.py backend-api\app\api\projects.py backend-api\app\api\assets.py backend-api\app\api\jobs.py backend-api\tests\test_projects.py`
  - `PYTHONPATH=backend-api FLASK_CONFIG=testing pytest backend-api\tests\test_projects.py`
- 提交：`Add FastAPI auth bridge execution plan`
- 后续：
  - 下一步应推进 A2 repository 层，减少 FastAPI route 中的 raw SQL 和列下标映射。
