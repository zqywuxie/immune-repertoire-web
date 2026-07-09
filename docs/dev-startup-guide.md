# 开发环境启动指南

> 最后更新：2026-06-30

---

## 总体架构

```
React SPA (:5173) ──proxy──▶ Flask (:5000) ──▶ MySQL (:3307)
                                        ├──▶ MongoDB (:27018)
                                        └──▶ Redis (:6379) — RQ workers
```

---

## 前置条件

- **Node.js** ≥ 18 + npm
- **Python** ≥ 3.10 + pip
- **Docker Desktop**（用于 MySQL / MongoDB / Redis）或手动安装对应服务

---

## 第一步：启动基础设施 (Docker)

```bash
# 在项目根目录执行
cd E:\Desktop\南华\Work\WenJingPan\immune-repertoire-web

# 启动 MySQL + MongoDB + Redis（必须）
docker compose up -d mysql mongodb redis

# 可选：启动 MinIO 对象存储（需要时）
docker compose --profile storage up -d minio minio-init

# 检查服务状态
docker compose ps
```

**端口映射：**

| 服务 | 容器内 | 宿主机 |
|------|--------|--------|
| MySQL | 3306 | **3307** |
| MongoDB | 27017 | **27018** |
| Redis | 6379 | **6379** |
| MinIO API | 9000 | **9000** |

配置文件：`.env`（项目根目录）

---

## 第二步：安装依赖

```bash
# Python 后端依赖
cd E:\Desktop\南华\Work\WenJingPan\immune-repertoire-web
pip install -r flask_app/requirements.txt

# 前端依赖
cd frontend
npm install
```

---

## 第三步：启动后端 (Flask)

```bash
# 回到项目根目录
cd E:\Desktop\南华\Work\WenJingPan\immune-repertoire-web

# 方式一：Flask CLI
cd flask_app
python -m flask run --host 0.0.0.0 --port 5000 --debug

# 方式二：直接运行（推荐，自动加载 .env）
python flask_app/app.py
```

**验证后端：**
```bash
# 健康检查
curl http://127.0.0.1:5000/api/health

# 项目列表
curl http://127.0.0.1:5000/api/projects

# 可用分析模块
curl http://127.0.0.1:5000/api/jobs/modules
```

---

## 第四步：启动前端 (Vite)

```bash
# 新开一个终端
cd E:\Desktop\南华\Work\WenJingPan\immune-repertoire-web\frontend
npm run dev
```

**Vite 开发服务器：**
- 地址：`http://127.0.0.1:5173`
- API 代理：`/api/*` → `http://127.0.0.1:5000`（配置在 `frontend/vite.config.ts`）

---

## 第五步：启动 RQ Worker（可选，用于后台任务）

```bash
cd E:\Desktop\南华\Work\WenJingPan\immune-repertoire-web

# 设置环境变量
set PYTHONPATH=.

# 启动 RQ Worker（处理分析任务）
rq worker analysis-jobs --url redis://127.0.0.1:6379/0
```

如果不需要后台任务队列，Flask 会在进程内线程池中执行任务（`JOB_QUEUE=redis` 切换）。

---

## 常用开发命令汇总

| 命令 | 目录 | 用途 |
|------|------|------|
| `docker compose up -d mysql mongodb redis` | 项目根 | 启动数据库 |
| `docker compose down` | 项目根 | 停止所有服务 |
| `python flask_app/app.py` | 项目根 | 启动 Flask (:5000) |
| `npm run dev` | frontend | 启动 Vite (:5173) |
| `npm run typecheck` | frontend | TypeScript 类型检查 |
| `npm run test` | frontend | 运行前端测试 (vitest) |
| `npm run build` | frontend | 生产构建 |
| `npm run generate-types` | frontend | 从 OpenAPI 生成 TS 类型 |
| `pytest flask_app/` | 项目根 | Flask 测试 |
| `pytest backend-api/tests/` | 项目根 | FastAPI 测试 |
| `pytest analysis_workers/tests/` | 项目根 | Worker 测试 |

---

## 页面路由对照

**前端 SPA (React) — `http://127.0.0.1:5173`：**

| 路由 | 页面 | 状态 |
|------|------|------|
| `/management` | 数据管理工作台 | ✅ 新 |
| `/management/projects` | 项目库 | ✅ 新 |
| `/management/projects/:id` | 项目详情 | ✅ 新 |
| `/management/samples` | 样本注册表 | ✅ 新 |
| `/management/settings` | 管理设置 | ✅ 新 |
| `/analysis` | 统一分析入口 | ✅ 新 |
| `/analysis/script-hub` | ScriptHub 6 阶段向导 | ✅ 新 |
| `/analysis/script-hub/jobs` | 任务监控中心 | ✅ 新 |
| `/analysis/pipeline-comparison` | 管道对比 | ✅ 新 |
| `/analysis/statistical` | 统计比较 | ✅ 新 |
| `/analysis/pdf-extractor` | PDF 提取 | ✅ 新 |
| `/analysis/ppt-tools` | PPT 工具 | ✅ 新 |
| `/analysis/settings` | 分析设置 | ✅ 新 |
| `/login` | 登录 | ✅ 新 |

**旧 Flask Jinja 页面 — `http://127.0.0.1:5000`：**

| 路由 | 状态 |
|------|------|
| `/management`、`/projects`、`/samples`、`/analysis/*` | 🟡 退役中 (带 Deprecation 横幅) |

---

## 环境变量参考

**`.env`（项目根目录，Docker + Flask 共用）：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MYSQL_HOST` | 127.0.0.1 | MySQL 主机 |
| `MYSQL_PORT` | 3307 | MySQL 端口 |
| `MYSQL_ROOT_PASSWORD` | ir_root_2024 | MySQL root 密码 |
| `MYSQL_USER` | ir_user | MySQL 用户名 |
| `MYSQL_PASSWORD` | ir_pass_2024 | MySQL 密码 |
| `MYSQL_DATABASE` | immune_repertoire | 数据库名 |
| `MONGO_HOST` | 127.0.0.1 | MongoDB 主机 |
| `MONGO_PORT` | 27018 | MongoDB 端口 |
| `REDIS_URL` | redis://127.0.0.1:6379/0 | Redis 连接 |
| `JOB_QUEUE` | redis | 队列后端 (redis / thread) |
| `FLASK_ENV` | development | Flask 环境 |
| `SECRET_KEY` | change-this… | Flask 密钥 |
| `VITE_API_TARGET` | http://127.0.0.1:5000 | Vite 代理目标 |

---

## 常见问题

**Q: 前端页面显示 500 错误？**
A: 确保 Flask 后端正在运行（`python flask_app/app.py`），Vite 代理会将 `/api/*` 转发到 `:5000`。

**Q: 数据库连接失败？**
A: 确保 Docker 服务已启动：`docker compose up -d mysql mongodb redis`

**Q: TypeScript 类型检查失败？**
A: 运行 `npm run generate-types` 重新生成 OpenAPI 类型，然后 `npm run typecheck`

**Q: 前端路由刷新 404？**
A: Vite dev server 已配置 SPA fallback，生产环境需配置 nginx `try_files`
