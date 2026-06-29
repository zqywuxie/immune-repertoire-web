# 重构迁移进度追踪

> 最后更新：2026-06-29 | 当前阶段：Phase 2 收尾 → Phase 3 准备

本文档对照 `docs/architecture/frontend-backend-separation-refactor.md` 的迁移路线，
追踪每个 Phase 的任务完成状态。完成状态标记：✅ 已完成 | 🔄 进行中 | ⬜ 未开始 | ❌ 已废弃

---

## Phase 0：冻结边界与补文档

**目标**：不大改代码，先明确系统边界。

| 任务 | 状态 | 产出/备注 |
|------|------|-----------|
| 梳理现有 API endpoint | ✅ | 各模块 route 已识别，见 `api_projects.py`, `api_jobs.py`, `api_script_hub.py` 等 |
| 标记稳定接口 vs 旧 Jinja 页面接口 | ✅ | `domain-model.md` 已定义稳定前端接口面 |
| 定义 OpenAPI 草案 | ✅ | `docs/api/openapi-draft.yaml` (v0.1.0) |
| 确定前端技术栈和目录结构 | ✅ | Vite 6 + React 19 + TypeScript 5.7, 结构见 `frontend/` |
| 编写架构文档 | ✅ | `domain-model.md`, `frontend-backend-separation-refactor.md` |

**Phase 0 完成度：5/5 (100%)**

---

## Phase 1：前端独立化

**目标**：新前端接管高价值页面，后端仍使用 Flask。

### 前端基础设施

| 任务 | 状态 | 产出/备注 |
|------|------|-----------|
| 创建 `frontend/` 目录和 Vite 项目 | ✅ | `6682c1a` - Vite + React + TypeScript + lucide-react |
| API Client 统一封装 (`client.ts`) | ✅ | `frontend/src/shared/api/client.ts` - GET/POST, error handling |
| 域名类型定义 (`domain.ts`) | ✅ | `frontend/src/shared/types/domain.ts` - Project, Asset, Job, JobModule |
| API 模块 (`projects.ts`, `jobs.ts`) | ✅ | Typed API wrappers for project and job endpoints |
| CORS / Dev Proxy | ✅ | Vite dev server proxy to Flask (`http://127.0.0.1:5173`) |

### 前端页面迁移

| 页面 | 状态 | 备注 |
|------|------|------|
| 项目列表 | ✅ | App.tsx - 表格展示, 排序, 状态筛选 |
| 项目详情 | ✅ | App.tsx - 详情面板 + 统计 (assets, samples, results) |
| Script Hub (任务提交) | ✅ | Job submission form - module 选择, payload JSON, force_rerun |
| 任务列表 | ✅ | Jobs tab - 状态轮询, 进度条 |
| 结果查看 | ✅ | Job results panel - outputs + registered assets |
| Asset 上传 | ✅ | Upload form - multipart/form-data, 多种 asset_type |
| Asset 预览/下载 | ✅ | Preview & Download links (global + project-scoped routes) |
| Asset 分页 | ✅ | PaginationControls - page/page_size/total_pages |

### 后端桥接

| 任务 | 状态 | 提交 | 备注 |
|------|------|------|------|
| 项目列表/详情 API | ✅ | 已有 (`/api/projects`) | 已在 Flask 中 |
| Asset CRUD API | ✅ | `78d9d78`, `10db451` | GET/POST/DELETE + 分页 |
| Asset 文件服务 (project-scoped) | ✅ | `78d9d78` | `/api/projects/{id}/assets/{id}/preview\|download` |
| Asset 文件服务 (global) | ✅ | `a270b15` | `/api/assets/{id}/preview\|download` |
| 统一 Job 提交桥接 | ✅ | `3b67f31` | `/api/jobs` POST - 支持 20+ module |
| 统一 Job 列表/详情 | ✅ | 已有 | `/api/jobs`, `/api/jobs/{job_id}` |
| Job 取消 | ✅ | 已有 | `/api/jobs/{job_id}/cancel` |
| 统一 Job 结果 | ✅ | `8dec5df` | `/api/jobs/{job_id}/results` - 规范化 outputs + assets |
| Job 模块列表 | ✅ | 已有 | `/api/jobs/modules` |
| Storage URI adapter | ✅ | `a33e3cc` | `local://` URI + metadata.storage_uri bridge |

**Phase 1 完成度：约 95%** — 核心功能已全部实现，前端模块化重构完成 (Dashboard/Database/ScriptHub 三页面 Apple 风格 SPA)。
遗留：旧 Jinja 页面仍在 `flask_app/templates/` 中并行运行（预期行为，绞杀者模式）。

### Phase 1 新增 (2026-06-29 重构批次)

| 任务 | 状态 | 提交 | 备注 |
|------|------|------|------|
| 前端模块化重构 (Apple设计系统) | ✅ | `4847742` | Dashboard + Database + ScriptHub 三页面路由 SPA |
| 设计令牌系统 (tokens.css) | ✅ | `e65dbc4` | Apple 风格颜色/圆角/阴影/间距/动效 |
| 11个共享组件库 | ✅ | `e65dbc4` | Rail, Card, Skeleton, StatusBadge, ProgressBar, Tabs, Pagination, PageHeader, EmptyState, MetricCard, Sheet |
| useApi / usePolling hooks | ✅ | `e65dbc4` | 通用异步数据 + 定时轮询 Hook |
| 业务组件抽取 (8个) | ✅ | `ea3a5dc`..`270df6a` | ProjectCard/List, AssetTable/Upload, JobSubmitForm/Row/List/ResultPanel |

---

## Phase 2：统一任务系统

**目标**：把分散的 task pattern 收敛到统一 jobs API。

| 任务 | 状态 | 备注 |
|------|------|------|
| POST /api/jobs | ✅ | Bridge endpoint，内部转发到各模块 route |
| GET /api/jobs | ✅ | 支持 project_id/status/module/limit 过滤 |
| GET /api/jobs/{job_id} | ✅ | 统一 Job detail response |
| POST /api/jobs/{job_id}/cancel | ✅ | Cancel 请求 |
| GET /api/jobs/{job_id}/results | ✅ | 规范化 outputs + assets |
| GET /api/jobs/{job_id}/events | ✅ | `a301d66` | SSE 事件流 — Flask `stream_with_context` |
| charts.combined 接入 | ✅ | `api_jobs.py` ALLOWED_API_JOBS |
| statistical.* 模块接入 | ✅ | 5 个 statistical 模块已注册 |
| auto-heatmap.* 模块接入 | ✅ | 4 个 auto-heatmap 模块已注册 |
| treemap.generate 接入 | ✅ | 已注册 |
| chord.generate 接入 | ✅ | 已注册 |
| ppt.* 模块接入 | ✅ | 3 个 PPT 模块已注册 |
| ppt-comparison.* 接入 | ✅ | 2 个模块已注册 |
| 前端 polling → SSE 升级 | ✅ | `a301d66` | `useJobEvents` Hook, ScriptHub 已集成 live job 状态 |
| Job Queue Adapter 边界 | ✅ | `c84627b` | Protocol-based queue seam for Phase 3 |
| API Job runners 抽取到 services | ✅ | `cfc2d0d` | `api_job_runner.py`, route 从 449 行精简到 200 行 |
| 持久化上下文运行队列任务 | ✅ | `4d89c8b` | Queued jobs run from persisted DB context |
| Job DELETE 端点 | ✅ | `api_jobs.py` | DELETE /api/jobs/{job_id} (需先 cancel) |

**Phase 2 完成度：约 95%** — 统一任务 API 完整，SSE 已替代轮询，queue seam 就位。

---

## Phase 3：Worker 化分析服务

**目标**：Web API 不再直接执行分析。

| 任务 | 状态 | 备注 |
|------|------|------|
| Job Queue Protocol 边界 | ✅ | `job_queue.py` — `ThreadPoolJobQueue` 实现，`JobQueue` Protocol |
| API runners 从 routes 抽取 | ✅ | `api_job_runner.py` — `call_json_endpoint()` |
| 队列从持久化上下文运行 | ✅ | `4d89c8b` — DB context passed to queue |
| 引入 Redis | ⬜ | 需要部署 Redis 实例 |
| 选择 Celery/RQ/Arq | ⬜ | 建议 Arq (async Python) 或 RQ (简单) |
| 实现 RedisJobQueue adapter | ⬜ | 替换 `ThreadPoolJobQueue`，复用 `JobQueue` Protocol |
| run_script_hub_job(job_id) | ⬜ | |
| run_treemap_job(job_id) | ⬜ | |
| run_chord_job(job_id) | ⬜ | |
| run_ppt_job(job_id) | ⬜ | |
| run_combined_analysis_job(job_id) | ⬜ | |
| 任务输入只接收 job_id | ⬜ | 当前 bridge 仍传递完整 payload |
| Worker 写回 progress/result/assets | ⬜ | |

**Phase 3 完成度：约 15%** — Job Queue seam 已就位，Runner 已服务化，可平滑切换到 Redis backend。

---

## Phase 4：资产存储抽象

**目标**：从本地绝对路径迁移到 `storage_uri`。

| 任务 | 状态 | 备注 |
|------|------|------|
| 保留 storage_path，新增 storage_uri | ✅ | `a33e3cc` - metadata.storage_uri → API 映射 |
| LocalStorageAdapter | ✅ | `flask_app/services/storage_adapter.py` |
| 新上传文件同时写入两列 | 🔄 | 进行中 |
| 新结果优先写 storage_uri | 🔄 | 进行中 |
| 读取时优先 storage_uri，fallback storage_path | ✅ | `_resolve_asset_file()` 在 `api_projects.py` |
| 批量迁移历史资产 | ⬜ | |
| 废弃直接依赖 Windows path 的逻辑 | ⬜ | |
| MinIO/S3 adapter | ⬜ | LocalStorageAdapter 已预留接口 |

**Phase 4 完成度：约 40%** — 基础已经打好了，storage_uri 兼容层到位，批量迁移待执行。

---

## Phase 5：API 平台替换

**目标**：从 Flask 单体迁到 FastAPI 或 NestJS。

| 任务 | 状态 | 备注 |
|------|------|------|
| Auth/User | ⬜ | |
| Projects | ⬜ | |
| Assets | ⬜ | |
| Jobs | ⬜ | |
| Results | ⬜ | |
| Script Hub job submission | ⬜ | |
| Legacy Flask retirement | ⬜ | |

**Phase 5 完成度：0%** — 尚未启动；建议等 Phase 3-4 稳定后再启动

---

## 总体进度

```
Phase 0  ████████████████████ 100%  冻结边界与补文档
Phase 1  ███████████████████░  95%  前端独立化 (模块化 Apple SPA 完成)
Phase 2  ███████████████████░  95%  统一任务系统 (SSE + Queue seam 完成)
Phase 3  ███░░░░░░░░░░░░░░░░░  15%  Worker 化分析服务 (Queue boundary 就位)
Phase 4  ████████░░░░░░░░░░░░  40%  资产存储抽象 (Storage URI bridge 完成)
Phase 5  ░░░░░░░░░░░░░░░░░░░░   0%  API 平台替换
────────────────────────────────────
Overall  █████████████░░░░░░░ ~65%
```

## 近期优先级 (2026-06-29 — 更新)

| 优先级 | 事项 | 所属 Phase | 状态 |
|--------|------|-----------|------|
| 1 | ~~前端模块化重构~~ | Phase 1 | ✅ 完成 |
| 2 | ~~SSE 事件流替换轮询~~ | Phase 2 | ✅ 完成 |
| 3 | **批量迁移历史资产到 storage_uri** | Phase 4 | → 下一步 |
| 4 | **存储抽象硬化 (减少 Windows path 依赖)** | Phase 4 | → 下一步 |
| 5 | RedisJobQueue adapter (Phase 3 预备) | Phase 3 | 待启动 |
| 6 | OpenAPI 规范与实际实现同步 | Phase 0/1 | 🔄 进行中 |

## 关联文档

- `docs/architecture/frontend-backend-separation-refactor.md` — 完整重构方案
- `docs/architecture/domain-model.md` — 领域模型定义
- `docs/api/openapi-draft.yaml` — API 契约草案
- `docs/superpowers/plans/` — 各功能实现计划
- `docs/superpowers/specs/` — 功能规范
