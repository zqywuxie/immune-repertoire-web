# A2: FastAPI Repository Layer Design

> 日期：2026-06-29 | 状态：已批准 | 依赖：A1 (已完成)

## 目标

将 FastAPI route 中的 raw SQL 提取到 repository 层，消除列下标映射、手写 SQL 拼接。

## 架构

```text
Route (HTTP only)
  → Service (permission/business rules)
    → Repository (SQL only)
      → SQLAlchemy Session
```

第一阶段只建 Repository 层，Service 层保持薄壳（直接委托）。

## 文件清单

### 新增

| 文件 | 内容 |
|------|------|
| `backend-api/app/repositories/__init__.py` | 空 |
| `backend-api/app/repositories/projects.py` | `ProjectRepository` — list_all, get_by_id, create, update |
| `backend-api/app/repositories/assets.py` | `AssetRepository` — list_by_project, get_by_id, create, delete, count |
| `backend-api/app/repositories/jobs.py` | `JobRepository` — list_by_project, get_by_id, create, update_status, delete |
| `backend-api/app/services/__init__.py` | 空 |
| `backend-api/app/services/project_service.py` | `ProjectService` — 薄壳委托 |
| `backend-api/app/services/asset_service.py` | `AssetService` — 薄壳委托 + storage_uri 解析 |
| `backend-api/app/services/job_service.py` | `JobService` — 薄壳委托 + 模块验证 |
| `backend-api/tests/test_repositories.py` | Repository 单元测试 |

### 修改

| 文件 | 改动 |
|------|------|
| `backend-api/app/api/projects.py` | raw SQL → `ProjectRepository` + `ProjectService` |
| `backend-api/app/api/assets.py` | raw SQL → `AssetRepository` + `AssetService` |
| `backend-api/app/api/jobs.py` | raw SQL → `JobRepository` + `JobService` |

## Repository 设计约束

- `__init__(self, db: Session)` — 接收 SQLAlchemy Session
- 所有查询使用 `text()` 参数化，禁止 f-string 拼接
- 返回 `dict` / `list[dict]`，使用 `.mappings().all()` 或 `row._asdict()`
- 不做权限检查、不做业务逻辑
- 不抛 HTTPException（那是 route/service 的职责）

## 验收标准

- Route 文件不再包含 `text("SELECT ...")` 或列下标常量
- 所有现有 FastAPI 测试通过
- `pytest backend-api/tests/test_repositories.py` 通过
