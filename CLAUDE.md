# Immune Repertoire Web Platform

免疫组库分析平台 — 渐进式前后端分离重构中。

## 技术栈

| 层 | 当前 | 目标 |
|---|------|------|
| Frontend | Vite 6 + React 19 + TypeScript 5.7 | 独立 SPA |
| Backend API | Flask (Python) | FastAPI (远期) |
| Analysis | Python (Flask 进程内) | Python workers + Redis queue |
| Database | MySQL + MongoDB | 治理后的 MySQL + storage adapter |
| Storage | 本地文件系统 (Windows path) | storage_uri → Local/MinIO/S3 |

## 目录结构

```
frontend/          # Vite + React 独立前端 (Phase 1)
flask_app/         # Flask 单体后端 (当前主力)
  routes/          # API 路由 (Blueprint)
  services/        # 业务逻辑 + 分析服务
  models/          # SQLAlchemy ORM 模型
  templates/       # Jinja2 旧页面 (绞杀者模式保留)
igblast_pipeline/  # IG Blast 分析管道
docs/              # 架构文档 + API 规范 + 迁移追踪
_reference/        # 参考实现和对照脚本
```

## 开发命令

```bash
# 前端
cd frontend && npm run dev        # 启动 Vite dev server (:5173)
cd frontend && npm run build      # 生产构建
cd frontend && npm run typecheck  # 类型检查

# 后端
cd flask_app && python -m flask run --port 5000  # 启动 Flask
cd flask_app && pytest                             # 运行测试
```

## 重构状态

当前处于 **Phase 1 (前端独立化)** 进行中，约 90% 完成。
详见 `docs/migration-progress.md`。

## 关键文档

- `docs/architecture/frontend-backend-separation-refactor.md` — 完整重构方案
- `docs/architecture/domain-model.md` — 领域模型 (Project/Asset/Job/Result)
- `docs/api/openapi-draft.yaml` — API 契约 (v0.2.0)
- `docs/migration-progress.md` — 迁移进度追踪

## 架构约定

- API JSON 保持 snake_case（Flask 桥接期）
- 前端类型镜像 API JSON 结构
- 资产读取：优先 `storage_uri` → fallback `storage_path`
- 新前端代码通过 typed API modules 调用后端
- 旧 Jinja 页面仍可运行（绞杀者模式）
