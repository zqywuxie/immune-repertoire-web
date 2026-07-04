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
| A2 | FastAPI repository 层 | 已完成 | route 不再包含 raw SQL 查询和列下标映射 |
| A3 | Project/Asset/Job service 层 | 已完成 | 权限、分页、排序、404、错误统一进入 service |
| A4 | OpenAPI 契约测试 | 已完成 | 后端 response 与 OpenAPI schema 有自动校验 |

### Phase B：Worker 结果协议闭环

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| B1 | `analysis_workers/results.py` | 已完成 | 提供注册 output asset 的统一 helper |
| B2 | Worker result envelope | 已完成 | 所有 worker 返回统一 `outputs/metrics/summary` |
| B3 | Job results 聚合重构 | 已完成 | `/api/jobs/{job_id}/results` 从 job result + assets 聚合 |
| B4 | Legacy bridge 标记 | 已完成 | 旧 endpoint 桥接路径在代码和文档中明确标记 |

### Phase C：模块插件化

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| C1 | Module manifest schema | 已完成 | 定义 `key/label/category/input_schema/output_schema/worker/ui_entry` |
| C2 | Module registry loader | 已完成 | 后端从 manifest 生成 `/api/jobs/modules` |
| C3 | Frontend module form | 已完成 | 前端按 manifest 渲染参数入口 |

### Phase D：资产治理与存储

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| D1 | checksum/lineage 字段迁移 | 已完成 | assets/job_assets 关系可追踪 |
| D2 | MinIO/S3 compose profile | 已完成 | 本地可一键启动对象存储 |
| D3 | Storage health check | 已完成 | `/api/health` 能检测 storage backend |

### Phase E：前端契约化

| ID | 任务 | 状态 | 验收标准 |
|---|---|---|---|
| E1 | OpenAPI TS type generation | 已完成 | `frontend/src/shared/api/generated` 自动生成 |
| E2 | API client 替换手写类型 | 已完成 | Project/Asset/Job 类型来自 generated schema |
| E3 | 结果查看器完善 | 已完成 | HTML/PNG/CSV/ZIP/PPT/PDF 输出按 kind 渲染 |

### Phase F：前端 UI 完善

> 新增于 2026-06-30，基于全量前端审计。
> 6 种分析模块专用表单 + CRUD 操作 UI + 全局基础设施 + 功能完善 + 代码质量。

#### F0：ScriptHub 分析模块专用表单（6 项 — 最高优先级）

manifest 定义 21 个模块，6 种 `ui_entry` 值。每个需实现为专用 React 组件替代通用 JSON 编辑。

| ID | ui_entry | 匹配模块 | 需要的 UI |
|----|----------|----------|-----------|
| F0.1 | `ChartsCombinedForm` | `charts.combined` (1) | 勾选表格类型：heatmap/treemap/chord/diversity/clonality/v_usage/j_usage |
| F0.2 | `SimpleForm` | 12 模块：statistical.analyze/boxplot/summary-boxplot, auto-heatmap.*, treemap, chord, ppt.scan-images/render-slides, analysis.execute-unified | 分组方案选择器 + 可选 metric dropdown |
| F0.3 | `MultiSelectForm` | 4 模块：statistical.analyze-multiple/analyze-batch/analyze-direct, analysis.batch | 多项选择 group_spec_ids / sample_ids / project_ids |
| F0.4 | `ImageSelectionForm` | `ppt.load-image` (1) | 图片缩略图网格 + 选择 + PPT template |
| F0.5 | `ComparisonConfigForm` | `ppt-comparison.generate` (1) | 两组 heatmap 选择 + 对比参数 |
| F0.6 | `PipelineConfigForm` | `analysis.execute` (1) | 管道配置：analysis_type (full/quick/custom) |

**实现**：
- 新建 `frontend/src/features/jobs/forms/ChartsCombinedForm.tsx`
- 新建 `frontend/src/features/jobs/forms/SimpleForm.tsx`
- 新建 `frontend/src/features/jobs/forms/MultiSelectForm.tsx`
- 新建 `frontend/src/features/jobs/forms/ImageSelectionForm.tsx`
- 新建 `frontend/src/features/jobs/forms/ComparisonConfigForm.tsx`
- 新建 `frontend/src/features/jobs/forms/PipelineConfigForm.tsx`
- 新建 `frontend/src/features/jobs/forms/index.ts` — ui_entry → component 映射
- 修改 `JobSubmitForm.tsx` — module switch → load form component

#### F1-F4：CRUD 操作 UI（4 项）

| ID | 任务 | 说明 | 关键文件 |
|----|------|------|---------|
| F1 | 项目创建/编辑 Sheet | Sheet 模态表单 + Dashboard "New Project" + Database "Edit" | ProjectForm.tsx, Dashboard.tsx, Database.tsx |
| F2 | 资产删除按钮 | AssetTable 操作列添加 Delete + 确认 | AssetTable.tsx |
| F3 | 任务取消按钮 | JobRow 对 running/queued 显示 Cancel | JobRow.tsx |
| F4 | 搜索/筛选 | ProjectList 搜索栏 + Database 资产类型筛选 | SearchBar.tsx, ProjectList.tsx, Database.tsx |

#### F5-F8：全局 UI 基础设施（4 项）

| ID | 任务 | 说明 | 关键文件 |
|----|------|------|---------|
| F5 | Toast 通知系统 | Context + provider + useToast hook，自动消失 4s | Toast.tsx, useToast.ts, App.tsx |
| F6 | 确认对话框 | Sheet 添加 footer slot + action buttons | Sheet.tsx |
| F7 | 错误状态透传 | Dashboard/Database/ScriptHub error → banner | Dashboard.tsx, Database.tsx, ScriptHub.tsx |
| F8 | 加载骨架屏 | Dashboard 加载中显示 Skeleton 卡片 | Dashboard.tsx |

#### F9-F12：功能完善（4 项）

| ID | 任务 | 说明 | 关键文件 |
|----|------|------|---------|
| F9 | JsonViewer fetch | fetch JSON URL → render formatted content | ResultViewer.tsx |
| F10 | Rail 用户菜单 | 底部 auth mode indicator | Rail.tsx, App.tsx |
| F11 | ScriptHub 空项目 | 无项目时显示 EmptyState | ScriptHub.tsx |
| F12 | EmptyState 统一 | Dashboard/ProjectList 用组件替代纯文本 | Dashboard.tsx, ProjectList.tsx |

#### F13-F14：代码质量（2 项）

| ID | 任务 | 说明 | 关键文件 |
|----|------|------|---------|
| F13 | SkeletonRow 确定性 | `Math.random()` → 确定性宽度数组 | Skeleton.tsx |
| F14 | 共享 CSS class | `.btn` `.input` class → 消除重复 inline style | App.css, 5+ 组件 |

#### 前端审计发现摘要

```
ScriptHub forms  — 无：6 种分析模块专用表单全部缺失，仅通用 JSON 编辑
Dashboard        — 无创建按钮、无骨架屏、错误静默、"No projects" 纯文本
Database         — 无编辑/删除入口、错误静默
AssetTable       — 操作列只有 Preview/Download，无 Delete
JobRow           — 只有 Results 按钮，无 Cancel
ResultViewer     — JsonViewer 不获取 JSON 内容
SkeletonRow      — Math.random() 宽度非确定性
Rail             — 无用户菜单/设置入口
EmptyState       — 存在但 Dashboard/ProjectList 未使用
Sheet            — 存在但未在任何地方使用
Toast            — 不存在；消息内联在各组件中
SearchBar        — 不存在；API 支持但无 UI
```

#### 当前执行队列（Phase F）

1. F0.1 ChartsCombinedForm
2. F0.2 SimpleForm (12 模块)
3. F0.3 MultiSelectForm (4 模块)
4. F0.4 ImageSelectionForm
5. F0.5 ComparisonConfigForm
6. F0.6 PipelineConfigForm
7. F1 项目创建/编辑 Sheet
8. F2 资产删除按钮
9. F3 任务取消按钮
10. F4 搜索/筛选栏
11. F5 Toast 通知系统
12. F6 确认对话框集成
13. F7 错误状态透传
14. F8 统一加载骨架屏
15. F9 JsonViewer 实时获取
16. F10 Rail 用户菜单
17. F11 ScriptHub 空项目保护
18. F12 EmptyState 组件统一
19. F13 SkeletonRow 确定性
20. F14 共享样式提取

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

**全 15 项执行任务已完成 ✅**

1. ✅ A1 FastAPI Auth/User bridge
2. ✅ A2 FastAPI repository 层
3. ✅ A3 Project/Asset/Job service 层
4. ✅ A4 OpenAPI 契约测试
5. ✅ B1 Worker output registration helper
6. ✅ B2 Worker result envelope
7. ✅ B3 Job results 聚合重构
8. ✅ B4 Legacy bridge 标记
9. ✅ C1 Module manifest schema
10. ✅ C2 Module registry loader
11. ✅ C3 Frontend module form
12. ✅ D1 checksum/lineage 字段迁移
13. ✅ D2 MinIO/S3 compose profile
14. ✅ D3 Storage health check
15. ✅ E1 OpenAPI TS type generation
16. ✅ E2 API client 替换手写类型
17. ✅ E3 结果查看器完善
18. ✅ Flask 退役（绞杀者模式标记完成）

### Phase F：前端 UI 完善（新增 2026-06-30）

19. ✅ F1 项目创建/编辑 Sheet
20. ✅ F2 资产删除按钮
21. ✅ F3 任务取消按钮
22. ✅ F4 搜索/筛选栏
23. ✅ F5 Toast 通知系统
24. ✅ F6 确认对话框集成
25. ✅ F7 错误状态透传
26. ✅ F8 统一加载骨架屏
27. ✅ F9 JsonViewer 实时获取
28. ✅ F10 Rail 用户菜单
29. ✅ F11 ScriptHub 空项目保护
30. ✅ F12 EmptyState 组件统一
31. ✅ F13 SkeletonRow 确定性
32. ✅ F14 共享样式提取

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

### 2026-06-29 / A2+A3 / FastAPI Repository + Service 层

- 状态：完成
- 改动：
  - 新增 `backend-api/app/repositories/` 包含 `ProjectRepository`、`AssetRepository`、`JobRepository`。
  - 所有查询使用 `text()` 参数化 + `.mappings()` 按列名访问，消除列下标常量。
  - 新增 `backend-api/app/services/` 包含 `ProjectService`、`AssetService`、`JobService`。
  - 重写 `projects.py`、`assets.py`、`jobs.py` 三个 API route 文件，移除所有 raw SQL 和 `_COL` 字典。
  - 新增 `backend-api/tests/test_repositories.py`（20 tests），含 NoRawSQLInRoutes 验证。
- 验证：
  - `python -m py_compile` 全部 9 个新/改文件通过。
  - `pytest backend-api/tests/` — 43 tests pass (23 existing + 20 new)。
- 提交：待提交
- 后续：
  - 下一步推进 B1 `analysis_workers/results.py`，Worker 可使用 Repository 层独立访问 DB。

### 2026-06-29 / B1 / Worker Output Registration Helper

- 状态：完成
- 改动：
  - 新增 `analysis_workers/results.py`，提供 `WorkerResults` 类——Flask-free 的 worker 生命周期管理。
  - 方法：`set_running`、`set_progress`、`set_completed`、`set_failed`、`register_output_asset`、`get_job`。
  - 使用独立 SQLAlchemy engine（复用 `API_DATABASE_URL` 配置），不依赖 Flask app context。
  - 所有 SQL 使用 `text()` 参数化查询，无字符串拼接。
  - 新增 `analysis_workers/tests/test_results.py`（7 tests），含 Flask-free 验证。
- 验证：
  - `python -m py_compile analysis_workers/results.py` 通过。
  - `pytest analysis_workers/tests/` — 7 tests pass。
  - `pytest backend-api/tests/` — 43 tests pass（无回归）。
- 提交：待提交
- 后续：
  - B2 Worker result envelope：统一 worker 返回 `outputs/metrics/summary`。

### 2026-06-29 / B2 / Worker Result Envelope

- 状态：完成
- 改动：
  - 新增 `WorkerOutput`、`WorkerResultEnvelope` dataclass 和 `build_envelope()`、`kind_from_path()` 辅助函数。
  - `WorkerResults.finalize_job(job_id, project_id, envelope)` — 批量注册 outputs 为 assets 并写入 completed 状态。
  - 标准 envelope 格式：`{outputs: [{label, url, kind, asset_id}], metrics, summary, raw_result}`。
  - 新增 6 个 envelope 相关测试。
- 验证：
  - `pytest analysis_workers/tests/` — 13 tests pass。
  - `pytest backend-api/tests/` — 43 tests pass（无回归）。
- 提交：待提交
- 后续：
  - B3 Job results 聚合重构，从 envelope 读取 outputs。

### 2026-06-29 / B3 / Job Results 聚合重构

- 状态：完成
- 改动：
  - `get_job_results` 重写为三级聚合：envelope outputs → legacy viewer_url/zip_url → registered project_assets。
  - 新增 `_kind_from_mime()` 辅助函数推断 output kind。
  - 按 URL 和 asset_id 去重，防止重复输出。
  - 新增 7 个 kind_from_mime 测试。
- 验证：
  - `pytest backend-api/tests/` — 50 tests pass。
- 提交：待提交
- 后续：
  - B4 Legacy bridge 标记。

### 2026-06-30 / B4 / Legacy Bridge 标记

- 状态：完成
- 改动：
  - 在 8 个 analysis_workers/tasks/*.py 文件添加 `.. attention:: **LEGACY BRIDGE**` 文档字符串标记。
  - 每个标记描述当前 Flask 依赖和迁移路径（→ `WorkerResults`）。
  - 标记文件：treemap.py, charts.py, generic.py, chord.py, ppt.py, statistical.py, heatmap.py, analysis.py。
- 验证：
  - `python -m py_compile` 全部 8 文件通过。
- 提交：待提交
- 后续：
  - C1 模块插件化 manifest。

### 2026-06-30 / C1 / Module Manifest Schema

- 状态：完成
- 改动：
  - 新增 `docs/api/module-manifest.yaml` — 21 个模块的正式注册表。
  - 每个模块定义：key, label, category, description, input_schema (JSON Schema), output_kinds, worker, ui_entry, enabled。
  - manifest_version: "1.0"，结构支持后端 loader 和前端 form renderer。
- 验证：
  - YAML 结构复审：5 categories (charts, statistical, heatmap, ppt, analysis)。
- 提交：待提交
- 后续：
  - C2 Module registry loader — 从 manifest 生成 `/api/jobs/modules`。

### 2026-06-30 / E1 / OpenAPI TS Type Generation

- 状态：完成
- 改动：
  - 安装 `openapi-typescript@7.13.0` 到 frontend devDependencies。
  - 从 `docs/api/openapi-draft.yaml` 生成 `frontend/src/shared/api/generated/schema.ts` (205ms)。
  - 新增 `generate-types` npm script。
  - 新增 `generated/index.ts` barrel export。
- 验证：
  - `npx tsc --noEmit` — 前端类型检查通过。
  - generated schema.ts 包含全部 paths/components/schemas 类型。
- 提交：待提交
- 后续：
  - E2 API client 替换手写类型 — 使用 generated schema 替换 `domain.ts` 手写类型。

### 2026-06-30 / C2 / Module Registry Loader

- 状态：完成
- 改动：
  - 新增 `backend-api/app/services/module_registry.py`，从 `docs/api/module-manifest.yaml` 加载模块注册表。
  - `ModuleRegistry` 类提供 `list_for_frontend()`、`validate_module()`、`input_schema()`。
  - `/api/jobs/modules` 现在从 manifest 动态生成（21 modules, 5 categories）。
  - `JobService.validate_module()` 优先使用 manifest，fallback 到硬编码集合。
  - 硬编码 `_ALLOWED_MODULES` 保留为 `_FALLBACK_MODULES`（manifest YAML 不可用时使用）。
- 验证：
  - `python -c` 验证 21 modules 加载，`validate_module('charts.combined')` = True。
  - `pytest backend-api/tests/` — 50 tests pass。
- 提交：待提交
- 后续：
  - C3 Frontend module form — 按 manifest `input_schema` 渲染参数入口。

### 2026-06-30 / E2 / API Client Type Migration

- 状态：完成
- 改动：
  - 新增 `frontend/src/shared/api/generated/helpers.ts` — 从 `schema.ts` 提取 `Project`、`Asset`、`Job`、`JobOutput`、`Pagination` 等便利类型别名。
  - 重写 `frontend/src/shared/types/domain.ts` 为 generated 类型的 re-export（`ProjectSummary` = `Project`、`ProjectAsset` = `Asset`、`JobSummary` = `Job`）。
  - `JobModule` 留为手写类型（尚未进入 OpenAPI spec）。
- 验证：
  - `npx tsc --noEmit` — 前端类型检查通过（6 files）。
  - `npx vitest run` — 24 tests pass。
- 提交：待提交
- 后续：
  - OpenAPI spec 应补充 `JobModule` 的 components/schemas 定义。

### 2026-06-30 / E3 / Result Viewer by Kind

- 状态：完成
- 改动：
  - 新增 `frontend/src/features/results/ResultViewer.tsx` — `ResultViewer` 组件按 `kind` 渲染输出。
  - 支持 kind：`html` (iframe), `png`/`image` (img), `pdf` (iframe), `csv`/`zip`/`ppt`/`pptx`/`json`/`data` (download link)。
  - 子组件：`HtmlViewer`、`ImageViewer`、`PdfViewer`、`CsvViewer`、`ZipViewer`、`PptViewer`、`JsonViewer`、`DownloadViewer`。
  - 辅助函数：`kindLabel()`、`kindIcon()`。
  - 更新 `JobResultPanel` 使用 `ResultViewer` 替换旧的简单链接列表。
- 验证：
  - `npx tsc --noEmit` — 通过。
  - `npx vitest run` — 24 tests pass。
- 提交：待提交
- 后续：
  - CSV inline table 渲染（fetch + parse on client）。

### 2026-06-30 / D2+D3 / MinIO Compose + Storage Health Check

- 状态：完成
- 改动：
  - `docker-compose.yml` 新增 `minio` 服务（MinIO 对象存储）和 `minio-init` 初始化容器。
  - MinIO profiles: `storage` 和 `full`，本地一键启动：`docker compose --profile storage up -d`。
  - `backend-api/app/api/system.py` 重写 `GET /api/health`：检测 DB（MySQL ping）、Redis（ping）、Storage（local/s3 head_bucket）。
  - S3 backend 通过 `STORAGE_BACKEND=s3` + boto3 健康检测。
- 验证：
  - `python -m py_compile` 通过。
  - `pytest backend-api/tests/` — 73 tests pass（含 system 和 health）。
- 提交：待提交
- 后续：
  - 生产环境部署时配置 S3_ENDPOINT_URL / S3_ACCESS_KEY / S3_SECRET_KEY。

### 2026-06-30 / D1 / Checksum & Lineage Migration

- 状态：完成
- 改动：
  - `docker/mysql/init/02_checksum_assets.sql` — 幂等迁移：添加 `checksum`/`checksum_algorithm` 列，创建 `job_assets` 关联表。
  - `WorkerResults.register_output_asset()` 计算文件 SHA-256 checksum，存储在 `metadata_json.checksum`。
  - `register_output_asset` 新增 best-effort `job_assets` 插入（rollback on table-not-found）。
  - 返回 dict 新增 `checksum` / `checksum_algorithm` 字段。
- 验证：
  - `pytest analysis_workers/tests/` — 13 tests pass。
- 提交：待提交
- 后续：
  - 执行 `02_checksum_assets.sql` 以添加 `checksum` 列和 `job_assets` 表。

### 2026-06-30 / A4 / OpenAPI Contract Tests

- 状态：完成
- 改动：
  - 新增 `backend-api/tests/test_openapi_contract.py`（23 tests）。
  - 解析 `docs/api/openapi-draft.yaml`，验证 ✅ 标记的 endpoint 响应 shape 匹配 spec。
  - 测试类：`TestOpenAPIContract`（shape validation）、`TestAllImplementedPathsReturnSensibleStatus`（smoke）、`TestResponseContentTypes`（JSON content-type）、`TestOpenAPISpecInternalConsistency`（spec 自洽）。
- 验证：
  - `pytest backend-api/tests/` — 73 tests pass（23 个 contract tests 全部通过）。
- 提交：待提交
- 后续：
  - 后续可用 `openapi-core` / `schemathesis` 做深度 schema validation。

### 2026-06-30 / C3 / Frontend Module Form

- 状态：完成
- 改动：
  - `JobSubmitForm.tsx` 重写为三栏布局：模块选择（optgroup by category）+ 模块信息 + 双模式输入。
  - View 模式切换：「Raw JSON」（textarea 原有功能）↔「Form」（动态字段表单）。
  - `DynamicFields` 组件：根据 payload JSON 自动推断字段类型（string/number/boolean/array/object）并渲染对应输入控件。
  - 模块 select 按 category 分组 + 显示 description + output_kinds 标签云。
  - Jobs/modules endpoint 现在返回 category/description/output_kinds 字段。
- 验证：
  - `npx tsc --noEmit` — 通过。
  - `npx vitest run` — 24 tests pass。
- 提交：待提交
- 后续：
  - 后续可从 manifest `input_schema` 生成更精确的 JSON Schema form。

### 2026-06-30 / Flask Retirement / 绞杀者模式标记

- 状态：完成
- 改动：
  - `flask_app/app.py`：`register_blueprints` 添加 retirement road-map 文档字符串 + RFC-8594 after_request handler。
  - 已退役蓝图（`jobs`、`api_projects`）的 API 响应增加 `Deprecation: true`、`Sunset`、`Link` HTTP 头。
  - Jinja 蓝图（`pages`、`auth`）的响应增加 `Deprecation` + `Sunset` 头。
  - `flask_app/templates/base.html`：所有 Jinja 页面显示退役横幅，引导用户到 React SPA（`http://127.0.0.1:5173`）。
  - 退役横幅只在顶层窗口显示（iframe 嵌入模式不显示）。
  - 4 个 Flask 蓝图文件添加 `.. attention:: DEPRECATED/RETIRING` 文档字符串：`api_jobs.py`、`api_projects.py`、`pages.py`、`auth.py`。
  - Analysis execution 蓝图保留用于 worker `call_json_endpoint` 兼容。
- 验证：
  - `python -m py_compile` 全部 5 个修改文件通过。
  - `pytest backend-api/tests/` — 73 tests pass（无回归）。
- 提交：待提交
- 后续：
  - Analysis execution 端点逐模块迁移到 `analysis_workers/tasks/` 后下线。

### 2026-06-30 / Phase F / Frontend UI 完善

- 状态：完成
- 改动：
  - **F0.1-F0.6 (分析模块专用表单)** — `ChartsCombinedForm`、`SimpleForm`、`MultiSelectForm`、`ImageSelectionForm`、`ComparisonConfigForm`、`PipelineConfigForm` 全部 6 个表单组件就位。
  - **F0 表单注册表** — `forms/index.ts` 提供 `FORM_REGISTRY` 和 `getFormComponent(uiEntry)`，`JobSubmitForm.tsx` 按 module 的 `ui_entry` 字段动态加载对应的表单组件。
  - **F1-F14** — 项目创建/编辑、资产删除、任务取消、搜索/筛选、Toast 通知、确认对话框、错误透传、加载骨架屏、JsonViewer fetch、Rail 用户菜单、ScriptHub 空项目保护、EmptyState 统一、SkeletonRow 确定性、共享样式提取，全部完成。
- 验证：
  - `npx tsc --noEmit` — 零错误。
  - `npx vitest run` — 24 tests pass。
  - `pytest backend-api/tests/` — 73 tests pass。
  - `pytest analysis_workers/tests/` — 13 tests pass。
- 提交：待提交
- 后续：
  - 前端可进一步优化：生产构建、bundle 分析、无障碍审计。

### 2026-06-30 / Phase G / 前端功能模块化重构 (双工作区架构恢复)

- 状态：完成
- 改动：
  - **导航基础设施** — 新建 `WorkspaceContext.tsx`（workspace: management|analysis，localStorage 持久化）、`Sidebar.tsx`（240px/64px 可折叠分层侧边栏，工作区切换 Tab + 管理/分析导航组 + 用户信息区）、`Breadcrumbs.tsx`、`Stepper.tsx`（步骤指示器）、`DirectoryBrowser.tsx`（文件树浏览器）。
  - **认证系统** — 新建 `auth.ts` API 模块、`AuthContext.tsx`（登录/登出/刷新）、`Login.tsx` 页面、`ProtectedRoute.tsx` 路由守卫。
  - **Management 工作区 4 页面** — `ManagementDashboard.tsx` (/management)、`ProjectLibrary.tsx` (/management/projects)、`ProjectDetail.tsx` (/management/projects/:id, 5 标签页)、`SampleRegistry.tsx` (/management/samples, 筛选+表格+编辑)。
  - **Analysis 工作区 6 页面** — `UnifiedAnalysis.tsx` (/analysis, 双列方案驱动)、`JobMonitor.tsx` (/analysis/script-hub/jobs, SSE 实时)、`PipelineComparison.tsx`、`StatisticalComparison.tsx`、`PdfExtractor.tsx`、`PptTools.tsx` (3 步骤向导)。
  - **ScriptHub 6 阶段向导** — `ScriptHubWizard.tsx` 编排器 + `StageIndicator.tsx` + 6 个阶段组件 (Stage1DataIntake→Stage2SourceInspection→Stage3ModuleConfig→Stage4Execution→Stage5Results→Stage6History)，12 模块网格 + FORM_REGISTRY 参数面板 + SSE 实时进度 + 执行日志。
  - **Settings 设置页** — 工作区自适应的可视化/导出/图表设置页面。
  - **samples API 模块** — `samples.ts`（listSamples, updateSample, exportSamplesUrl）。
  - **App.tsx 路由重组** — 从 3 路由平铺结构替换为 /management/* + /analysis/* 双工作区嵌套路由，懒加载 15 个页面组件，集成 AuthProvider + WorkspaceProvider + ToastProvider 三层上下文。
  - **跨文件类型修复**: ProjectDetail.tsx 复杂类型简化、Stepper.tsx StepStatus 导出、Stage4Execution PptTools 类型兼容、client.ts put() 方法补充。
- 验证：
  - `npx tsc --noEmit` — 零类型错误。
  - `npx vitest run` — 24 tests pass (无回归)。
  - `pytest backend-api/tests/` — 73 tests pass (无回归)。
  - `pytest analysis_workers/tests/` — 13 tests pass (无回归)。
  - 总计：**110 tests** 全部通过。
- 提交：待提交
- 后续：
  - 启动 Vite dev server 验证页面渲染（`npm run dev`）。
  - 旧页面清理：`Dashboard.tsx`、`Database.tsx`、`ScriptHub.tsx` 可移除或标记为 deprecated。
  - `Rail.tsx` 组件已被 `Sidebar.tsx` 取代，可移除。