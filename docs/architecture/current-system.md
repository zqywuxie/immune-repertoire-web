# 当前架构与维护入口

更新：2026-09-19。本文描述当前代码；历史目标和未完成提案见[归档](../archive/README.md)。

## 实际运行结构

当前入口为 Docker Nginx `:8080`，静态 React 页面通过 `/api` 访问 Flask/Gunicorn；独立 RQ worker 执行分析，MySQL、MongoDB、Redis 位于内部网络。依赖、测试和构建均在容器内完成。Flask 的 `create_app` 注册业务 API，调用 `flask_app/services/` 内的分析服务。`backend-api/` 保留 FastAPI 实现，不能把它的接口清单当成全部 Legacy Script Hub 能力。

前端路由以 `frontend/src/app/App.tsx` 为准。主要业务导航仅保留“分析中心”和“任务与结果”；根路径进入分析中心。创建项目、选择项目及四类输入上传嵌入分析中心，项目详情作为必要的次级管理入口。BCR、PDF/PPT、统计工具及旧管理总览不再列入主业务入口。

新容器默认启用真实登录注册；注册账号为普通用户，业务数据按账号隔离，管理员也不能在普通业务 API 中跨账号浏览。既有 `.env` 保持原样；旧 internal 配置仍为明确的匿名内部模式，升级时须按部署文档切换。上传版本及校验摘要保存在 ProjectAsset.metadata_json，正式任务沿用 AnalysisJob，结果文件沿用 processed_result 资产，无新增数据库表。


## 两类任务接口

- 通用任务通过 jobs API，模块元数据在 `docs/api/module-manifest.yaml`。worker、请求字段与实现必须一致。
- Script Hub 通过自身 modules、inspect、jobs/task/results 接口；React 的 `shared/api/scriptHub.ts` 负责现有响应适配。
- Profile 对应 Script Hub 的 `profile`，复用 `BoxPlotService`；上传资产后按数据集读取已注册的 Profile，不要求同时有 PEP。
- 仅在任务完成并取得结果后进入结果页。结果资产和历史任务应通过现有 API 管理，不直接删结果目录。

## 数据与维护

项目数据由项目资产服务注册，metadata 的 `asset_set` 标识数据集。向导的检查与任务提交必须传递相同数据集。新上传和结果分别保存在 app_uploads、app_results 卷或配置的宿主机目录，原应用数据保留 app_data 卷；原 Windows 外置目录继续保留，迁移记录见[Docker 部署说明](../docker-deployment.md)。

仅清理确定可重建的 `__pycache__`、`.pytest_cache` 和工具缓存。数据库、项目资产、PDF 提取和结果文件属于业务数据。缓存清理不跟随任何目录联接。

## 开发与测试

React 共用组件位于 `frontend/src/shared/components/`，分析配置位于 `features/scripthub/`。复用现有上传、检查、任务与结果流程；不要再新增独立一套分析表单框架。

前端用 Vitest，后端用 pytest。Profile 回归覆盖独立上传、上传失败保留文件、等待任务完成、按数据集检查与执行，以及实际报告生成。完整优化路线包含公开 UI 和 pipeline 01–10 对齐，这些不能仅凭当前入口存在就标记完成。

## 分析入口拆分验证（2026-09-13）

新增七类、19 个独立工具入口，展示注册表为 `frontend/src/features/analysis/tools.ts`。图表预设和表达 / usage 模式在提交前固定；方案工具固定 scheme。原组合分析和自定义指标接口保留。跨工具复用会话中的项目数据，任务地址可刷新重开。

Docker 内前端 21 个测试文件、73 项测试通过，生产构建通过。Docker Chromium 使用合成 API 响应验证了全部入口、Profile 配置提交与结果重开、SHM 固定方案、图表固定模式、数据复用、搜索及 390px 布局，无浏览器运行错误。此项是界面与请求契约验证，不替代原始脚本数值回归。

## 2026-09-13 项目输入基础

项目输入已增加免疫细胞浸润结果资产，与克隆序列表、样本指标表、转录组组成四类输入。当前仅资产、上传、选择和检查响应贯通；浸润算法及分析依赖完整改造仍在执行，见 `docs/superpowers/project-input-workflow-progress.md`。
