# Immune Repertoire Analysis Web Application

免疫组库数据分析Web应用程序，提供用户友好的界面进行免疫组库数据分析。

## 项目结构

```
immune-repertoire-web/
├── backend/                 # FastAPI后端
│   ├── app/
│   │   ├── api/            # API路由
│   │   │   └── routes/     # 路由模块
│   │   ├── models/         # 数据库模型
│   │   ├── services/       # 业务逻辑服务
│   │   ├── tasks/          # Celery异步任务
│   │   ├── utils/          # 工具函数
│   │   ├── config.py       # 配置管理
│   │   ├── main.py         # FastAPI入口
│   │   └── celery_app.py   # Celery配置
│   ├── alembic/            # 数据库迁移
│   ├── requirements.txt    # Python依赖
│   └── .env.example        # 环境变量示例
├── frontend/               # React前端
│   ├── src/
│   │   ├── components/     # React组件
│   │   ├── pages/          # 页面组件
│   │   ├── services/       # API服务
│   │   ├── store/          # Zustand状态管理
│   │   └── types/          # TypeScript类型定义
│   ├── package.json        # Node依赖
│   └── vite.config.ts      # Vite配置
└── README.md
```

## 技术栈

### 后端
- FastAPI - Web框架
- SQLAlchemy - ORM
- Celery - 异步任务队列
- Redis - 消息代理和缓存
- Alembic - 数据库迁移

### 前端
- React 18 + TypeScript
- Ant Design - UI组件库
- ECharts - 图表库
- Zustand - 状态管理
- Axios - HTTP客户端

## 快速开始

### 后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 复制环境变量配置
cp .env.example .env

# 初始化数据库
alembic upgrade head

# 启动开发服务器
uvicorn app.main:app --reload
```

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

## 功能特性

- 文件上传：支持CSV、Excel、gzip压缩文件
- 相似度分析：R² inner/outer、CDR3 sharing、Morisita-Horn等
- 测序深度分析：质量指标计算和可视化
- 多样性指标：D50、Gini、Shannon、Simpson
- 链特异性分析：支持7种免疫受体链
- 结果导出：PNG、CSV、ZIP批量下载
