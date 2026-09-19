# 原始 Flask 单机架构文档

> 创建日期：2026-06-30
> 目的：完整记录原始 Flask 单体应用的功能模块结构、服务层、UI 设计和数据流，作为前端重构的参考基线。
> 状态：绞杀者模式运行中 — Flask 正在被 React SPA + FastAPI 逐步替换。

---

## 目录

1. [总体架构](#1-总体架构)
2. [双工作区设计](#2-双工作区设计)
3. [领域模型](#3-领域模型)
4. [服务层](#4-服务层)
5. [分析系统](#5-分析系统)
6. [ScriptHub 系统](#6-scripthub-系统)
7. [独立分析工具](#7-独立分析工具)
8. [UI 页面结构](#8-ui-页面结构)
9. [关键架构模式](#9-关键架构模式)
10. [数据流追踪](#10-数据流追踪)

---

## 1. 总体架构

```
Flask 单体 (flask_app/)
├── routes/           # Blueprint 路由层 (HTTP 入口)
├── services/         # 业务逻辑层
│   ├── analysis/     # 可插拔分析模块 (旧)
│   ├── analyzers/    # 方案驱动分析器 (新)
│   └── ...           # 各类支撑服务
├── models/           # SQLAlchemy ORM (MySQL)
├── templates/        # Jinja2 模板 (正在退役)
├── static/           # CSS/JS 静态资源
└── config/           # 配置 (JSON/YAML)

analysis_workers/     # Worker 进程 (Phase 3 新增)
backend-api/          # FastAPI 替换层 (Phase 5)
```

**执行模型 (原始单机)**：
```
HTTP Request → Flask Blueprint → Service Layer → ThreadPoolExecutor (max_workers=4)
                                                      ↓
                                              后台线程执行分析
                                                      ↓
                                              结果写入文件系统 + DB
                                                      ↓
                                              ← 返回给客户端
```

**核心依赖**：MySQL (ORM)、MongoDB (结果/缓存)、本地文件系统 (Windows/Linux 路径)

---

## 2. 双工作区设计

原始 UI 有两个工作区，通过侧边栏切换：

### Management 工作区 (`/management`)

| 页面 | 路由 | 功能 |
|------|------|------|
| 数据工作台 | `/management` | 卡片式概览：项目管理、样本库、设置入口 |
| 项目库 | `/projects` | 创建/搜索/管理项目，统计面板 |
| 项目详情 | `/projects/<id>` | 5 标签页：概览/资产/分析/样本/设置 |
| 样本库 | `/samples` | 多条件筛选 + 可编辑表格 + CSV 导出 |
| 数据上传 | `/upload` | 已集成到项目详情中 |
| 管理设置 | `/settings?workspace=management` | 不适用 |

### Analysis 工作区 (`/analysis`)

| 页面 | 路由 | 功能 |
|------|------|------|
| 统一分析 | `/analysis` | 方案驱动分析入口（simple_analysis.html） |
| ScriptHub | `/analysis/script-hub` | **6 阶段流水线向导** (核心页面) |
| 后台任务 | `/analysis/script-hub/jobs` | 任务监控中心 |
| 管道对比 | `/analysis/pipeline-comparison` | 多管道并排比较 |
| 统计比较 | `/analysis/statistical` | Kruskal-Wallis + 箱线图 |
| PDF 提取 | `/analysis/pdf-extractor` | 表格提取 + 图像提取 |
| PPT 替换 | `/analysis/ppt-heatmap` | 热图替换到模板 |
| 结果查看 | `/analysis/<id>/results` | 按链/Tab 展示图表+数据 |
| 高级分析 | `/analysis/advanced-analysis` | 已弃用，重定向 |
| 分析设置 | `/settings?workspace=analysis` | 可视化/导出/图表配置 |

**侧边栏结构** (来自 `templates/components/sidebar.html`)：

```
Management 导航:                  Analysis 导航:
┌─────────────────────┐          ┌─────────────────────┐
│ Data Management     │          │ Analysis Workspace  │
│  ├ 数据工作台        │          │  ├ 数据分析          │
│  ├ 项目库            │          │  ├ 管道对比          │
│  ├ 样本库            │          │  ├ 项目综合分析(ScHub) │
│  └ 数据上传          │          │  ├ 后台任务          │
│ ─────────────────── │          │  └ 统计检验          │
│ Management Settings │          │ ─────────────────── │
└─────────────────────┘          │ Tools               │
                                 │  ├ PDF表格提取      │
                                 │  └ PPT图表替换      │
                                 │ ─────────────────── │
                                 │ Analysis Settings   │
                                 └─────────────────────┘
```

工作区切换由导航栏按钮 + `data-workspace` body 属性控制。

---

## 3. 领域模型

### 3.1 核心 ORM 模型 (MySQL)

```
User ─── owns ─── Project
  │                   │
  │                   ├── ProjectAsset (资产：pep/profile/transcriptome/group_spec/...)
  │                   ├── SampleRecord (样本元数据)
  │                   └── ProjectGroupSpec (分组方案)
  │
  ├── File (上传数据文件)
  │
  └── AnalysisJob (所有后台任务的统一记录)
       │
       ├── job_type: 模块标识 (e.g. "charts.combined")
       ├── status: queued → running → completed/failed/cancelled
       ├── payload: JSON 输入参数
       ├── progress: 0-100
       └── result: JSON 输出数据
```

### 3.2 补充存储

| 存储 | 用途 |
|------|------|
| MongoDB `results` | 分析结果（按签名去重），所有 ScriptHub 模块 |
| MongoDB `rawdata` | 原始数据资产（pep/datapoint/raw_archive） |
| MongoDB `cached_usage` | pep-analysis 输出的 VJ usage 缓存（供下游模块） |
| MongoDB `script_hub_jobs` | ScriptHub 专有作业记录 |
| 文件系统 | 所有结果文件：PNG、CSV、ZIP、HTML |

---

## 4. 服务层

### 4.1 核心服务

| 服务 | 文件 | 职责 |
|------|------|------|
| **BackgroundJobService** | `background_job_service.py` | 统一任务目录：创建、轮询、完成、失败、取消。ThreadPoolExecutor(max_workers=4) |
| **FileParserService** | `file_parser.py` | CSV/Excel/TSV 解析，编码自动检测 (UTF-8/GBK) |
| **FieldMappingService** | `field_mapping.py` | 文件列 → 分析器字段映射，自动建议 |
| **SchemeManager** | `scheme_manager.py` | 方案注册、自动映射、信心评分 |
| **PathAccessService** | `path_access_service.py` | 路径沙盒验证 |
| **MongoService** | `mongo_service.py` | MongoDB CRUD + 签名去重 |
| **JobQueue** | `job_queue.py` | 队列抽象层 (ThreadPool / Redis/RQ) |
| **ScriptHubJobService** | `script_hub_job_service.py` | ScriptHub 专用作业管理 |
| **ProjectAnalysisBridge** | `project_analysis_bridge.py` | 项目资产到分析页面的桥接 |

### 4.2 分析器层 (`services/analyzers/`)

基于方案的分析器（用于 UnifiedAnalysis）：

| 分析器 | 方案 ID | 必需字段 | 输出 |
|--------|---------|----------|------|
| **BCellIsotypeAnalyzer** | `bcell_isotype` | Sample | 6 种同种型表达 + 百分比差异 + 堆叠/热图/雷达图 |
| **SHMAnalyzer** | `shm_analysis` | Sample | 体细胞高频突变频率 (SHM Rate) |
| **IGMetricsAnalyzer** | `ig_metrics` | Sample, Chain | 5 种多样性指标 + 相关性矩阵 |
| **CustomFieldAnalyzer** | `custom_field_analysis` | (用户选择) | 通用字段分析 |
| **SequencingReadsChartAnalyzer** | `sequencing_reads_chart` | Sample | 链分布条形图 |
| **BcellMaturationAnalyzer** | `ig_other_isotype` | Sample | B 细胞成熟阶段 |
| **PPTReportGenerator** | `ppt_report` | Sample | PPT 幻灯片生成 |

### 4.3 分析模块系统 (`services/analysis/modules/`)

旧的可插拔模块系统（不同于分析器层）：

| 模块类 | 名称 | 类别 | 文件 |
|--------|------|------|------|
| `BCellIsotypeModule` | `bcell_isotype` | bcell_analysis | `bcell_isotype.py` |
| `SHMAnalysisModule` | `shm_analysis` | mutation_analysis | `shm_analysis.py` |
| `IGMetricsModule` | `ig_metrics` | diversity_analysis | `ig_metrics.py` |
| `SequencingDepthModule` | `sequencing_depth` | quality_control | `sequencing_depth.py` |
| `SequencingReadsModule` | `sequencing_reads` | sequencing | `sequencing_reads.py` |
| `ChainAnalysisModule` | `chain_analysis` | chain_specificity | `chain_analysis.py` |
| `FieldAnalyzerModule` | `field_analyzer` | field_analysis | `field_analyzer.py` |
| `StatisticalComparisonModule` | `statistical_comparison` | 统计分析 | `statistical_comparison.py` |

---

## 5. 分析系统

### 5.1 两套分析系统

| 特性 | ScriptHub 系统 | 统一分析系统 |
|------|---------------|-------------|
| **路由** | `/api/script-hub/*` | `/api/analysis/*` |
| **执行** | ThreadPoolExecutor (async) | Flask 直接执行 (sync) |
| **作业追踪** | `_script_tasks` dict + MongoDB | `BackgroundJobService` |
| **模块数** | 12 个 | 5+ 个 |
| **数据源** | PEP 目录 + Profile + 表达矩阵 | 上传的 File 记录 |
| **输出格式** | 文件 + viewer.html | Base64 编码图表 |
| **签名缓存** | MongoDB 去重 | 无 |

### 5.2 ScriptHub 通用执行模式

所有 12 个 ScriptHub 模块遵循相同的 5 阶段执行模式：

```
阶段 1: 数据摄入
  → 选择项目 → 浏览文件系统 → 选择 PEP/Profile/Transcriptome 路径
  
阶段 2: 源检查
  → 解析文件 → 检测列/链/样本 → 展示指标预览

阶段 3: 模块配置
  → 选择分析模块 → 配置参数 (field_mapping/chains/groups/thresholds)

阶段 4: 执行
  → POST /api/script-hub/<module>/run
  → 创建 task_id → 提交到 ThreadPoolExecutor
  → 立即返回 task_id + 状态 URL
  → 后台线程: _record_stage() 心跳 → Service.generate_report() → _normalize_script_result()
  → _try_reuse_script_result() 检查 MongoDB 缓存（相同签名可复用）

阶段 5: 结果
  → viewer.html + metadata.json + results.zip
  → MongoDB save_result() + SQL ProjectAsset 注册
```

---

## 6. ScriptHub 系统

### 6.1 模块完整目录

12 个模块分布在 3 个 Blueprint 文件中：

| 模块键 | 功能 | 服务类 | 输入 | 输出 | 文件 |
|--------|------|--------|------|------|------|
| `db-alignment` | VDJdb/McPAS-TCR 数据库比对 | `DBAlignmentService` | PEP 目录 + Profile | viewer.html, align_bundle.zip, summary.csv | `modules_config.py` |
| `boxplot` | 分组箱线图 | `BoxPlotService` | Profile CSV | PNGs, p-value CSV, ZIP | `boxplot.py` |
| `profile` | Profile 分组分析 | `BoxPlotService` (复用) | Profile CSV | PNGs, CSV, ZIP | `profile_analysis.py` |
| `topclone` | 前 N 克隆丰度 | `TopCloneService` | PEP + Profile | TopClone CSV, BoxPlot PNGs, CDR3 seq | `profile_analysis.py` |
| `pep-analysis` | PEP 共享分析 | `PepAnalysisService` | PEP 目录 + Profile | 共享矩阵 CSV, usage CSV, 热图 PNG, ZIP | `profile_analysis.py` |
| `pgen-analysis` | Pgen/SoNNia 生成概率 | `PgenAnalysisService` | PEP 目录 + Profile | Detail CSV, Summary CSV, PNG, ZIP | `profile_analysis.py` |
| `umap` | UMAP 降维聚类 | `UmapService` | Profile CSV | UMAP PNGs, CSV 坐标, PDF | `enrichment.py` |
| `volcano` | 火山图差异分析 | `VolcanoService` | Usage 数据 或 Expression | Volcano PNGs, CSV, ZIP | `enrichment.py` |
| `go-kegg-enrichment` | GO/KEGG 富集 | `GoKeggEnrichmentService` | Expression matrix | Volcano PNGs, Enrichment tables, ZIP | `enrichment.py` |
| `umapin` | UMAP (VJ usage) 集成 | `UmapinService` | Usage 数据目录 | UMAP PNGs, CSV | `enrichment.py` |
| `ml-analysis` | 随机森林分类 | `MLAnalysisService` | Profile + VJ usage | ROC PNGs, Feature importance, CSV | `enrichment.py` |
| `mait-nkt` | MAIT/NKT 分析 | `MaitNktService` | TRA CSV + Profile | Boxplot PNGs, ZIP | `enrichment.py` |

### 6.2 共享基础设施 (`_common.py`)

关键全局状态和函数：

```python
# 模块级执行器
_script_executor = ThreadPoolExecutor(max_workers=2)
_script_tasks: Dict[str, Dict] = {}  # 内存任务状态

# 输入解析（项目优先）
_pep_paths_from_request()      # 从 project_id 资产获取 PEP 路径
_profile_path_from_request()   # 从 project_id 资产获取 Profile 路径
_transcriptome_path_from_request()  # 获取表达矩阵路径

# 缓存复用
_build_script_cache_context()  # 构建签名：project_id + module + assets + config
_try_reuse_script_result()     # 查询 MongoDB 是否已有相同签名的结果

# 任务生命周期
_set_task_state()              # 更新内存状态
_sync_job_state()              # 同步到 ScriptHubJobService
_record_stage()                # 进度心跳（checked for cancellation）
_complete_script_task()        # 最终化结果

# 结果打包
_normalize_script_result()     # 标准化输出格式
_build_and_save_viewer()       # 生成 viewer.html
_ensure_result_zip()           # 生成 results.zip
```

### 6.3 pep-analysis 后处理

`pep-analysis` 完成后有特殊逻辑：
- `_cache_pep_usage_assets()` 将输出的 `usage/` 目录注册为 `cached_usage` 类型的项目资产
- 这些缓存的 usage 数据供下游模块使用：volcano、umapin、ml-analysis

---

## 7. 独立分析工具

这些有自己的 Blueprint 和独立的 ThreadPoolExecutor：

### 7.1 Auto Heatmap (`/api/auto-heatmap`)

**4 个作业模块**：
- `auto-heatmap.generate-heatmap` — 文件夹扫描 → 样本检测 → 字段映射 → 热图生成
- `auto-heatmap.generate-pipeline-report` — 管道目录扫描 → CDR3 共享矩阵 → 相似度热图
- `auto-heatmap.generate-heatmap-report` — 完整热图报告 (HTML + ZIP)
- `auto-heatmap.export-shared-cdr3` — CDR3 序列导出

**服务**: `auto_heatmap_service.py`, `heatmap_generator.py`

### 7.2 Statistical (`/api/statistical`)

**6 个作业模块**：
- `statistical.analyze` — 单文件 Kruskal-Wallis + Dunn's test
- `statistical.boxplot` — 分组箱线图
- `statistical.analyze-multiple` — 多文件汇总分析
- `statistical.summary-boxplot` — 汇总箱线图
- `statistical.analyze-batch` — 批量分析
- `statistical.analyze-direct` — 直接分析

**服务**: `statistical_analysis_service.py`

### 7.3 PPT (`/api/ppt`)

**3 个作业模块**：
- `ppt.scan-images` — 扫描 PPT 模板中的图像槽位
- `ppt.load-image` — 加载热图图像到指定槽位
- `ppt.render-slides` — 渲染最终 PPT

**服务**: `ppt_service.py`, `ppt_heatmap_service.py`

### 7.4 PPT Comparison (`/api/ppt-comparison`)

**2 个作业模块**：
- `ppt-comparison.scan-heatmaps` — 扫描对比热图目录
- `ppt-comparison.generate` — 生成对比 PPT

### 7.5 Chord (`/api/chord`)

**1 个作业模块**：
- `chord.generate` — 生成 V/J 配对 Chord 图

**独立 ThreadPoolExecutor**，独立任务字典

### 7.6 Treemap (`/api/treemap`)

**1 个作业模块**：
- `treemap.generate` — 生成 CDR3 丰度 Treemap

**独立 ThreadPoolExecutor**，独立任务字典

### 7.7 Charts Combined (`charts.combined`)

特殊的多步骤协调作业：
1. 生成热图 (heatmap → heatmap report)
2. 并行生成子作业：Chord 图 + Treemap
3. 等待子作业完成 (`wait_child_job()`，1.5s 轮询，最多 18 分钟)
4. 合并结果 → 持久化到 MongoDB

---

## 8. UI 页面结构

### 8.1 设计令牌

原始 UI 定义了多套 CSS 变量系统：

**Management 工作区** (`management_common.css`)：
```css
--mg-ink, --mg-muted, --mg-soft, --mg-panel, --mg-border
--mg-blue, --mg-green, --mg-amber, --mg-red
```
- 英雄区渐变边框
- 统计卡片悬浮效果
- 粘性工具栏 (backdrop-blur)
- Tab 导航蓝色激活态

**ScriptHub** (内联 CSS, ~2800 行模板)：
```css
--sh-page, --sh-panel, --sh-line, --sh-ink, --sh-muted
--sh-accent, --sh-accent-soft, --sh-warm, --sh-warm-soft
--sh-success, --sh-success-soft
```
- 阶段卡片 22px 圆角
- 渐变页面背景
- 可选中 Chip 组件
- 模块卡片网格（带推荐/就绪/缓存/阻止状态）
- 分类选择器（双面板：字段列表 + 值预览）
- 管道步骤可视化（彩色左边界）
- 深色日志面板

**统一分析** (`unified_analysis.css`)：
```css
--ua-ink, --ua-muted, --ua-border, --ua-panel, --ua-blue, --ua-teal
```
- 步骤指示器：水平编号步骤 + 激活/完成状态
- 远程文件树：嵌套分支/节点布局
- 字段映射表格 + 置信度徽章

### 8.2 ScriptHub 6 阶段向导 UI

最复杂的 UI 组件（~2800 行 Jinja + ~1000 行 JS）：

**阶段 01 — 选择项目**：
- 项目下拉选择 + "创建项目" 按钮
- 可用资产摘要
- 状态徽章：活动

**阶段 02 — 数据选择**：
- 双面板布局：左侧目录树浏览器 + 右侧选择篮
- 3 种资产篮：PEP 路径 / Profile 文件 / Transcriptome 矩阵
- 操作按钮：添加为 PEP、设为 Profile、设为 Transcriptome、上传 Transcriptome

**阶段 03 — 检测结果**：
- 紧凑指标网格：Samples、Chains、PEP Files、Profile
- Profile 格式预览表
- PEP 格式预览表
- 参数范围建议

**阶段 04 — 模块选择**：
- 模块卡片网格（每个模块：图标+名称+描述+状态徽章+标签）
- 悬停高亮 + 选中态
- 选中后显示数据摘要面板

**阶段 05 — 运行配置**：
- 通用控件：任务名称、"检测数据" 按钮、运行摘要芯片
- **模块特定控件**（通过 `data-module` 属性显示/隐藏）：
  - `db-alignment`：CDR3/Copy 列选择，分类字段选择器（双面板），病理模式
  - `charts`：折叠子步骤（扫描摘要 → 链选择芯片 → 样本选择 → 字段映射 → 内容选择（热图/Treemap/Chord 复选框））
  - `profile/boxplot`：DataPoint 文件选择，分组字段多选，字段排序拖拽
  - `pep-analysis`：管道步骤（步骤 2-8），强制步骤（红色左边框，锁定），可选步骤（绿色左边框，可切换）
  - `volcano`：输入类型（VJ usage/Expression），P 值/Log2FC 阈值，分组前缀，比较列表
  - `go-kegg-enrichment`：表达矩阵路径，富集参数，GSEA/GO Simplification 切换
  - `ml-analysis`：特征来源（Profile/VJ usage），标签/过滤列选择 + 值预览，CV 折数
  - `pgen-analysis`：企业模块（特殊左边框），物种选择，SoNNia 依赖检查
  - `umap`：n_neighbors, min_dist 配置
  - `umapin`：usage 数据路径，FDR 切换
  - `mait-nkt`：TRA 源选择，分组字段 + 排序
- 执行按钮："Run [module name]" + "查看后台任务"

**阶段 06 — 结果**：
- 成功摘要 + 操作按钮（Open Viewer, Download ZIP, Metadata）
- 执行日志（深色主题，等宽字体）
- 状态徽章

### 8.3 其他重要页面 UI

**项目详情** (`project_detail.html`) — 5 标签页：
1. **概览**：统计卡片 + 元数据表 + 快捷操作
2. **资产**：搜索栏 + 类型筛选 + 可折叠资产表 + 上传模态框
3. **分析**：3 列模块网格（管道对比/ScriptHub/GO-KEGG）
4. **样本**：统计摘要 + 预览表（链接到完整样本库）
5. **设置**：左侧分组方案编辑器 + 右侧项目设置表单

**管道对比** (`pipeline_comparison.html`) — 双面板：
- 左侧：运行参数卡片 + 结果卡片
- 右侧：运行日志卡片
- 操作：目录浏览 → 扫描管道 → 配置 CDR3/Copy 列 → 拖拽排序 → 过滤器 → 切换选项 → 运行

**统计比较** (`statistical_comparison.html`) — Tab 布局：
- 单文件 Tab：上传/选择文件 → 配置列 → 运行 → Kruskal-Wallis 表 + Dunn's test + 箱线图
- 多文件 Tab：多文件上传 → 相同配置 → P 值校正模式

---

## 9. 关键架构模式

### 9.1 项目优先的资源解析

所有 ScriptHub 端点优先检查 `project_id`：
- 有 project_id → 从 `ProjectAsset` 表查询获取路径
- 无 project_id → 使用请求体中的原始路径

### 9.2 分析签名缓存

`_build_script_cache_context()` 创建确定性签名：
```
signature = SHA256(project_id + module_name + input_asset_paths + input_asset_mtimes + config_json)
```

执行前查询 MongoDB 匹配签名；命中则直接返回存储的结果。

### 9.3 合作式取消 (PEP-0505)

`_record_stage()` 在每次进度心跳时检查 `_script_task_cancel_requested()`，取消时抛出 `ScriptTaskCancelled` 异常。

### 9.4 pep-analysis → downstream 数据管线

```
pep-analysis 执行
  → 输出 usage/ 目录 (VJ usage CSV 文件)
  → _cache_pep_usage_assets() 注册为 cached_usage 类型资产
  → volcano / umapin / ml-analysis 读取这些缓存资产
```

### 9.5 遗留桥接模式 (Legacy Bridge)

`analysis_workers/tasks/` 中所有 8 个文件：
```
Worker 接收 job_id
  → 创建完整 Flask app (app_context)
  → 从 DB 获取 job payload
  → call_json_endpoint(module, payload, user_id)
      → 通过 ALLOWED_API_JOBS 映射查找 Flask 视图函数
      → 使用 test_request_context 调用 Flask 端点
  → 将结果写回 DB
```

推荐迁移目标：`analysis_workers/results.py` 的 `WorkerResults` 类（零 Flask 依赖）。

---

## 10. 数据流追踪

### 10.1 ScriptHub 数据流

```
用户操作 (Jinja 页面)
  │
  ├── 阶段 1: 选择项目
  │   └── GET /api/projects → DOM 填充项目下拉框
  │
  ├── 阶段 2: 浏览文件系统
  │   └── GET /api/projects/<id>/assets → 目录树组件渲染
  │   用户选择 PEP/Profile/Transcriptome 路径 → 存入隐藏 input
  │
  ├── 阶段 3: 检测数据
  │   └── POST /api/script-hub/<module>/inspect → 返回解析后的列/链/样本
  │
  ├── 阶段 4: 选择模块 + 配置参数
  │   └── GET /api/script-hub/modules → 渲染模块卡片网格
  │   用户填写模块特定参数表单
  │
  ├── 阶段 5: 执行
  │   └── POST /api/script-hub/<module>/run
  │       ├── 构建 cache_context (签名)
  │       ├── _try_reuse_script_result() → MongoDB 查询
  │       │   └── 命中 → 立即返回已有结果
  │       │   └── 未命中 → 创建 task_id → 提交到 ThreadPoolExecutor
  │       │              → 返回 task_id + status_url
  │       │              → 后台: Service.generate_report()
  │       │              → _normalize_script_result()
  │       │              → _persist_script_result()
  │       │                 ├── save_result() → MongoDB
  │       │                 ├── register_analysis_result() → SQL ProjectAsset
  │       │                 └── 写入文件系统 (viewer.html, metadata.json, results.zip)
  │       └── 客户端轮询 GET /api/script-hub/tasks/<task_id>/status
  │           └── 返回 { status, progress, stage, detail }
  │
  └── 阶段 6: 查看结果
      └── GET /api/script-hub/tasks/<task_id>/result
          └── 返回 { outputs: [{url, kind, label}], metrics, summary }
```

### 10.2 UnifiedAnalysis 数据流

```
用户上传文件
  └── POST /api/files/upload → File 记录存入 DB
      └── FileParserService 解析 → 返回文件列

自动方案建议
  └── POST /api/analysis/suggest-scheme
      └── SchemeManager.suggest_scheme(columns) → 返回 [{id, confidence}]

字段映射
  └── POST /api/analysis/auto-map
      └── SchemeManager.apply_scheme(scheme, columns) → 返回 field_mapping

执行分析
  └── POST /api/analysis/execute-unified
      └── UnifiedAnalysisService.execute_analysis()
          ├── _execute_scheme_analysis() [方案模式]
          │   ├── 加载方案 → 实例化分析器 (e.g., BCellIsotypeAnalyzer)
          │   ├── 合并参数
          │   └── AnalysisPipeline.execute(analyzer, data, field_mapping, params)
          │       ├── _preprocess_data() → 重命名列
          │       ├── analyzer.analyze() → 统计 + 表格
          │       ├── analyzer.visualize() → matplotlib 图表
          │       └── _save_to_history() → Analysis DB 记录
          └── 返回 { analysis_id, status, results: {charts, tables, statistics} }
```

### 10.3 后台作业数据流 (charts.combined 示例)

```
POST /api/jobs { module: "charts.combined", payload: {...}, project_id: ... }
  └── BackgroundJobService.create_job() → AnalysisJob 记录 (status: queued)
  └── JobQueue.submit() → ThreadPoolExecutor
      └── run_combined_charts_job(context)
          ├── run_analysis_job_step("auto-heatmap.generate-heatmap", ...)
          │   └── call_json_endpoint() → Flask test_request_context → 调用端点函数
          ├── run_analysis_job_step("auto-heatmap.generate-heatmap-report", ...)
          ├── 并行子作业:
          │   ├── submit_child_job("chord.generate", ...)
          │   │   └── wait_child_job(child_id) — 1.5s 轮询, 最多 18 分钟
          │   └── submit_child_job("treemap.generate", ...)
          │       └── wait_child_job(child_id)
          └── 合并结果 → MongoDB save_result()
```

---

## 附录 A: 关键文件索引

### 后端核心
- `flask_app/routes/pages.py` — **25+ 页面路由**（原始路由表）
- `flask_app/services/background_job_service.py` — 统一后台作业系统
- `flask_app/services/unified_analysis_service.py` — 统一分析编排器
- `flask_app/services/scheme_manager.py` — 分析方案系统
- `flask_app/services/api_job_runner.py` — API 作业 → Flask 端点桥接

### ScriptHub
- `flask_app/routes/api_script_hub/_common.py` — **2288 行，12 个模块的共享基础设施**
- `flask_app/routes/api_script_hub/modules_config.py` — db-alignment + 模块列表
- `flask_app/routes/api_script_hub/boxplot.py` — boxplot (+ profile)
- `flask_app/routes/api_script_hub/profile_analysis.py` — topclone + pep-analysis + pgen-analysis
- `flask_app/routes/api_script_hub/enrichment.py` — umap + volcano + go-kegg + umapin + ml + mait-nkt

### 分析模块
- `flask_app/services/analysis/base_module.py` — `AnalysisModule` 基类
- `flask_app/services/analysis/registry.py` — `AnalysisRegistry` + `register_module` 装饰器
- `flask_app/services/analyzers/` — 方案驱动分析器（BaseAnalyzer 基类）

### 独立工具
- `flask_app/routes/api_auto_heatmap.py` — 热图 Blueprint
- `flask_app/routes/api_statistical.py` — 统计 Blueprint
- `flask_app/routes/api_ppt.py` + `api_ppt_comparison.py` — PPT Blueprints
- `flask_app/routes/api_chord.py` — Chord 图 (独立 ThreadPoolExecutor)
- `flask_app/routes/api_treemap.py` — Treemap (独立 ThreadPoolExecutor)

### Worker 桥接
- `analysis_workers/tasks/charts.py` — charts.combined (多步骤协调)
- `analysis_workers/tasks/heatmap.py` — 4 个 heatmap 任务
- `analysis_workers/tasks/statistical.py` — 6 个 statistical 任务
- `analysis_workers/tasks/ppt.py` — 5 个 PPT 任务
- `analysis_workers/tasks/treemap.py`、`chord.py`、`analysis.py`、`generic.py`

### 前端 (Jinja — 正在退役)
- `flask_app/templates/analysis/script_hub.html` — **~2800 行，完整的 6 阶段向导**
- `flask_app/templates/simple_analysis.html` — 统一分析页面 (内联 ~500 行 JS)
- `flask_app/templates/components/sidebar.html` — **双工作区侧边栏** (参考导航结构)
- `flask_app/static/js/script_hub.js` — **~1000 行 JS 控制器**
- `flask_app/static/css/unified_analysis.css` — 分析工作区样式
- `flask_app/static/css/management_common.css` — 管理工作区样式

---

## 附录 B: 术语对照

| 术语 | 含义 |
|------|------|
| **PEP** | 每个样本的子目录，包含 CDR3 数据文件 |
| **Profile / Datapoint** | 包含样本级指标 (Reads, UCDR3, D50 等) 的 CSV 文件 |
| **Transcriptome / Expression Matrix** | 基因表达矩阵 CSV |
| **Scheme** | 数据列到分析类型的预设映射 (bcell_isotype, shm_analysis, ig_metrics) |
| **Field Mapping** | CSV 列名 → 分析器期望字段名的映射 |
| **Group Spec** | 样本分组和排序规范 |
| **cached_usage** | pep-analysis 输出的 VJ 使用频率缓存资产 |
| **viewer.html** | 交互式结果查看器 (独立 HTML 文件) |
| **Legacy Bridge** | 通过 Flask test_request_context 调用 Flask 端点的 worker 模式 |
