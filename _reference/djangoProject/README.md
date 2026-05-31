# djangoProject

这是一个基于 Django 4.2 和 Django REST Framework 的后端项目，核心用途不是通用 CMS 或后台，而是一个面向免疫组库 / 受体测序数据的项目管理与分析服务。

从当前代码结构看，它主要用于：

- 用户注册、邮箱验证码登录与 Token 鉴权
- 项目创建、查询、删除
- `datapoint`、样本说明表、`pep`/克隆数据文件上传
- 样本检索、条件筛选、结果导出
- 免疫组库数据的自动化分析处理
- Swagger 接口文档暴露

项目中出现了 `CDR3`、`gene_usage`、`UMAP`、`TopClone`、`Dominant_Clone`、`vdjdb`、`McPAS-TCR` 等分析脚本和数据库文件，因此可以判断这是一个偏生物信息学场景的后端，重点服务于 TCR/BCR 或类似受体序列分析流程。

## 技术栈

- Python 3.11
- Django 4.2
- Django REST Framework
- MySQL
- MongoDB
- `django-apscheduler`
- `drf-yasg`
- Pandas / NumPy / SciPy / scikit-learn / UMAP 等数据处理库
- matplotlib / seaborn / bokeh 等可视化库

## 存储结构

这个项目同时使用两类数据库：

- MySQL：Django 默认认证体系，保存 `User`、`UserInfo`、`EmailCode` 等关系型数据
- MongoDB：保存项目、样本说明、`datapoint`、上传后的序列数据以及分析结果
- Redis：缓存、定时任务管理

默认环境变量如下：

- `MYSQL_DATABASE=djangoProject`
- `MYSQL_USER=root`
- `MYSQL_PASSWORD=lgy123456`
- `MYSQL_HOST=localhost`
- `MYSQL_PORT=3306`
- `MONGO_URI=mongodb://localhost:27017/`

## 数据库设计

### 双数据库架构
项目采用双数据库架构，根据数据特性选择合适的存储方案：

#### 1. MySQL (关系型数据库)
**用途**：存储用户相关的结构化数据

**表结构**：
- **auth_user** (Django 内置)
  - 用户基本信息：用户名、密码、邮箱等
  
- **user_info** (自定义扩展)
  ```python
  - id: 主键
  - user: 关联 auth_user (OneToOne)
  - username: 用户名
  - creat_time: 创建时间
  - age: 年龄
  - email: 邮箱
  ```

- **email_code** (邮箱验证码)
  ```python
  - id: 主键
  - email: 邮箱地址
  - code: 验证码
  - create_time: 创建时间
  ```

#### 2. MongoDB (文档型数据库)
**用途**：存储项目相关的非结构化数据

**数据库和集合设计**：
- **数据库**: `project`
  - **集合1**: `project_detail` (项目详情)
  ```javascript
  {
    _id: ObjectId,
    name: "项目名称",
    id: "项目UUID",
    user_id: "用户ID",
    cooperation_level: "合作级别",
    institution: "机构",
    create_time: Date,
    update_time: Date
  }
  ```

  - **集合2**: `datapoint` (序列数据点)
  ```javascript
  {
    _id: ObjectId,
    project_id: "项目UUID",
    sequence: "序列数据",
    gene_usage: "基因使用情况",
    cdr3: "CDR3序列",
    umap_coordinates: [x, y],  // UMAP降维结果
    clone_frequency: Number,
    chain_type: "IGH/IGL/IGK/TRA/TRB/TRG/TRD"
  }
  ```

  - **集合3**: `sample_describe` (样本描述)
  ```javascript
  {
    _id: ObjectId,
    project_id: "项目UUID",
    sample_id: "样本ID",
    group: "分组信息",
    description: "样本描述",
    metadata: {}
  }
  ```

#### 3. Redis (缓存数据库)
**用途**：
- 邮箱验证码缓存
- 定时任务管理
- 会话缓存

### 数据流向设计
```
用户操作 → MySQL认证 → MongoDB操作 → 结果返回
```

### 数据备份现状
⚠️ **当前项目没有数据库备份**

**风险**：
- 数据丢失风险：数据库损坏时无法恢复
- 误操作风险：错误操作无法回滚
- 服务中断风险：故障时无法快速恢复

**建议备份策略**：
1. **MySQL 备份**：每天凌晨自动备份
2. **MongoDB 备份**：定期 mongodump 备份
3. **备份保留**：保留最近30天的备份文件

## 核心分析功能

### 自动化分析流程
项目集成了完整的免疫组库数据分析流水线，使用定时任务系统自动处理项目数据：

#### 主要分析模块：

1. **UMAP 降维分析** (`umap_func.py`)
   - 对免疫组库数据进行降维可视化
   - 按分组处理数据，生成降维坐标
   - 帮助识别数据聚类模式

2. **基因使用分析** (`gene_usage.py`)
   - 分析基因使用频率分布
   - 统计 V、D、J 基因使用情况
   - 生成基因使用统计图表

3. **克隆多样性分析**
   - **Top Clone 分析** (`topClone_func.py`)：识别高频克隆
   - **优势克隆分析** (`Dominant_Clone.py`)：分析克隆占比
   - **相似克隆分析** (`Similar_Clone.py`)：计算克隆间相似性

4. **序列比对分析** (`db_alignment.py`)
   - 与参考数据库（VDJdb、McPAS-TCR）比对
   - 识别已知 TCR 克隆
   - 分析序列特异性

5. **结构分析** (`CDR3_length.py`)
   - 分析 CDR3 序列长度分布
   - 生成长度统计箱线图
   - 评估库多样性

6. **统计分析**
   - **箱线图分析** (`boxplot_func.py`)：不同分组的统计分析
   - **ECDF 分析** (`ECDF_func.py`)：经验累积分布函数
   - **群体比较**：多维度数据比较

#### 分析流程执行顺序：
```
项目数据 → UMAP降维 → 基因使用分析 → 克隆多样性分析 → 数据库比对 → 统计可视化
```

### 定时任务系统 (`TimeTask/`)

#### 核心功能：
1. **批量处理** (`all_func`)
   - 对一个项目执行完整的分析流程
   - 按顺序调用所有分析函数
   - 自动生成分析结果

2. **任务调度** (`test`)
   - 从项目列表中获取待处理项目
   - 执行自动化分析
   - 更新项目处理状态

3. **资源管理** (`rm_dir`)
   - 自动清理10小时前的临时文件
   - 防止磁盘空间不足
   - 保持系统高效运行

4. **并发控制**
   - 使用文件锁避免重复执行
   - 线程安全的任务调度
   - 异步处理提高系统性能

### 日志和监控 (`logger/`)

- 完整的操作日志记录
- 按日期自动分割日志文件
- 保留最近7天的日志
- 支持控制台和文件双输出

## 工作流程

### 完整数据处理流程：
```
数据上传 → 项目创建 → 加入队列 → 定时任务处理 → 自动化分析 → 结果存储 → 状态更新 → 可视化生成
```

### 用户操作流程：
1. 创建项目并上传数据
2. 系统自动加入处理队列
3. 定时任务后台自动分析
4. 用户可查询处理进度
5. 下载分析结果和可视化图表

这套分析系统大大简化了复杂的生物信息学分析流程，用户只需上传数据，系统会自动完成从原始数据到分析结果的全部处理过程。

## 目录说明

- [manage.py](/E:/Desktop/IndividualProject/djangoProject/manage.py) Django 启动入口
- [djangoProject/settings.py](/E:/Desktop/IndividualProject/djangoProject/djangoProject/settings.py) 全局配置
- [djangoProject/urls.py](/E:/Desktop/IndividualProject/djangoProject/djangoProject/urls.py) 项目级路由与 Swagger
- [appone/urls/index.py](/E:/Desktop/IndividualProject/djangoProject/appone/urls/index.py) 业务接口入口
- [appone/views](/E:/Desktop/IndividualProject/djangoProject/appone/views) 登录、注册、项目管理、样本检索、文件上传等接口
- [appone/models](/E:/Desktop/IndividualProject/djangoProject/appone/models) 用户扩展信息和邮箱验证码模型
- [djangoProject/tools/process_func](/E:/Desktop/IndividualProject/djangoProject/djangoProject/tools/process_func) 分析流程封装
- [djangoProject/tools/process_func](/E:/Desktop/IndividualProject/djangoProject/djangoProject/tools/process_func) 核心分析功能实现
- [djangoProject/tools/process_script](/E:/Desktop/IndividualProject/djangoProject/djangoProject/tools/process_script) 各类分析算法实现
- [static](/E:/Desktop/IndividualProject/djangoProject/static) 静态资源、样本模板、项目列表等文件

## 主要接口

- `POST /user/register/` 用户注册
- `POST /user/getCode/` 发送邮箱验证码
- `POST /user/login/` 用户登录
- `GET /user/loginOut/` 用户退出
- `POST /addProject/` 新建项目
- `POST /addDatapoint/` 上传 datapoint 文件
- `POST /addGroupSpecification/` 上传分组说明
- `POST /addPep/` 上传 pep 或压缩包数据
- `POST /addSampleSummaryTable/` 上传样本总表
- `GET /project/` 项目分页查询
- `POST /pageresearch/` 样本分页检索
- `POST /downloadresearchdata/` 导出检索结果
- `GET /downloadprocessfile/` 下载处理后的项目文件
- `GET /swagger/` Swagger 文档

接口大多基于 DRF Token 鉴权，登录后需要在请求头中携带认证信息。

## 本地启动

1. 创建并激活虚拟环境
2. 安装依赖
3. 准备 MySQL 和 MongoDB
4. 执行 Django 迁移
5. 启动开发服务器

示例命令：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

启动后默认访问：

- 后端服务：`http://127.0.0.1:8000/`
- Swagger：`http://127.0.0.1:8000/swagger/`

## Docker

仓库中包含 [Dockerfile](/E:/Desktop/IndividualProject/djangoProject/Dockerfile)，默认使用 `gunicorn` 启动：

```powershell
docker build -t django-project .
docker run -p 8000:8000 django-project
```

需要注意：当前 `Dockerfile` 安装的是 `requirements.txt.bak`，而开发环境更直观的依赖文件是 `requirements.txt`。如果后续要统一部署流程，建议只保留一份依赖清单。

## 当前判断结论

这个项目本质上是一个"免疫组库数据管理 + 分析结果服务"的 Django 后端，提供用户体系、项目管理、样本与序列文件上传、筛选检索、分析脚本整合以及结果下载能力。

## 项目特点

1. **专业生物信息学**：专门针对免疫组库数据分析
2. **全流程支持**：从数据上传到自动化分析处理的完整流程
3. **高级分析能力**：集成多种生物信息学算法和可视化工具
4. **自动化处理**：使用定时任务自动执行复杂分析流程
5. **高性能处理**：使用 Pandas、NumPy 等进行大规模数据处理
6. **RESTful API**：提供标准化的 API 接口
7. **双数据库架构**：MySQL + MongoDB 的混合存储方案

**注意**：这是一个纯后端项目，没有前端可视化界面。用户需要通过 API 调用或 Swagger 接口来使用服务，或者需要单独开发前端界面来调用这些 API。