# 免疫组库数据分析平台

## 1. 项目背景与目标
本项目为“免疫受体库（Immune Repertoire）分析”Web 应用，目标是将常见的免疫组库数据处理与可视化流程产品化，提供：

- 数据文件上传与管理（CSV / Excel / gzip CSV / PDF）
- 多种分析任务的统一配置与执行（方案模式/自定义字段）
- 热图等可视化结果展示与导出
- 基于模板的 PPT 热图替换、以及多方法热图对比 PPT 生成

## 2. 技术栈与依赖
后端为 Flask 单体应用，SQLite 作为默认数据库，静态资源/模板直接由 Flask 提供。

- Web 框架：`flask==3.0.0`
- ORM：`flask-sqlalchemy==3.1.1`（底层 `sqlalchemy==2.0.25`）
- 数据处理：`pandas==2.1.4`、`numpy==1.26.3`、`openpyxl==3.1.2`
- 可视化：`matplotlib==3.8.2`、`seaborn==0.13.1`、`Pillow==10.2.0`
- PDF：`pdfplumber`、`PyMuPDF`、`tabula-py`
- 测试：`pytest`、`pytest-cov`、`hypothesis`

## 3. 目录结构（核心）
- `app.py`
  - Flask 应用入口（`create_app`），注册蓝图/错误处理器/初始化各类 service。
- `config.py`
  - 配置与环境变量读取，默认 SQLite 文件：`flask_app/data/immune_repertoire.db`。
- `models/database.py`
  - SQLAlchemy 模型：文件（`File`）、分析任务（`Analysis`）、结果（`AnalysisResult`）、注释（`Annotation`）、参数模板（`CustomParameter`）等。
- `routes/`
  - `pages.py`：页面路由（`/`、`/upload`、`/files`、`/analysis` 等）
  - `api.py`：文件管理/分析/配置等 REST API（`/api/*`）
  - `api_analysis.py`：模块化分析系统 API（`/api/analysis/*`）
  - `api_statistical.py`：统计分析 API（`/api/statistical/*`）
  - `api_auto_heatmap.py`：基于文件夹扫描的自动热图分析（`/api/auto-heatmap/*`）
  - `api_ppt.py`：PPT 热图替换（`/api/ppt/*`）
  - `api_ppt_comparison.py`：多方法热图对比 PPT 生成（`/api/ppt-comparison/*`）
- `services/`
  - 分析编排与执行：`analysis_service.py`、`analysis_pipeline.py`、`unified_analysis_service.py`
  - 方案/字段映射：`scheme_manager.py`、`field_mapping.py`
  - 自动热图：`auto_heatmap_service.py`、`heatmap_generator.py`
  - PPT：`ppt_heatmap_service.py`、`ppt_service.py`、`ppt_comparison_service.py`
  - PDF：`pdf_extractor.py`、`pdf_table_extractor.py`

## 4. 应用启动与运行方式
### 4.1 单命令启动
- 启动脚本：`python app.py`
- 配置选择：环境变量 `FLASK_CONFIG`（`development/production/testing/default`）

### 4.2 关键配置
在 `config.py` 中：

- 服务端监听：`HOST`（默认 `0.0.0.0`）、`PORT`（默认 `5000`）
- 上传/结果目录：
  - `UPLOAD_FOLDER = flask_app/data/uploads`
  - `RESULTS_FOLDER = flask_app/data/results`
- 上传大小：`MAX_CONTENT_LENGTH = 100MB`

## 5. 系统核心流程（端到端）
### 5.1 文件上传与解析
- 入口：`POST /api/files/upload`
- 关键点：
  - 文件后缀校验（`FileParserService.validate_extension`）
  - 解析列名与行数（`FileParserService.parse_file`）
  - 保存文件到 `UPLOAD_FOLDER`，并写入 `File` 表

### 5.2 分析任务创建与执行（异步）
- 后端服务：`services/analysis_service.py`
- 关键机制：
  - `ThreadPoolExecutor` 进行后台执行（最大并发 `MAX_CONCURRENT_TASKS=4`）
  - 在 DB 中维护 `Analysis` 的 `status/progress/current_step` 等字段
  - 将图表/表格等输出落盘，并以 `AnalysisResult` 记录元信息

### 5.3 “统一分析”（Scheme 模式 / Custom 模式）
- 服务：`services/unified_analysis_service.py`
- Scheme 管理：`services/scheme_manager.py`
  - 预设方案配置文件：`flask_app/config/analysis_schemes.json`
  - 自定义方案目录：`flask_app/data/custom_schemes/*.json`
- 设计要点：
  - Scheme 模式：选择方案 + 映射 required/optional 字段 + 默认参数
  - Custom 模式：用户按需选字段，走自定义分析器（如 `CustomFieldAnalyzer`）

### 5.4 自动热图（基于文件夹扫描）
- 入口：`POST /api/auto-heatmap/scan-folder`、`POST /api/auto-heatmap/generate-heatmap`
- 功能：
  - 扫描“样本子文件夹”并识别数据文件类型
  - 字段映射（如 CDR3 列、copy 列等）
  - 支持样本重命名/分组，生成热图与矩阵数据
  - 可扩展导出（如共享列表导出：`cdr3_export_service`）

### 5.5 统计分析（分组比较）
- 入口：`POST /api/statistical/analyze`、`POST /api/statistical/boxplot`、`POST /api/statistical/analyze-multiple`
- 结果：
  - 统计检验结果（含 P-value 等）
  - base64 编码的箱线图图像

### 5.6 PPT 自动化输出
- PPT 热图替换：`/api/ppt/analyze`、`/api/ppt/replace`、`/api/ppt/download/*`
  - 替换PPT中的热图位置为生成的图片
- PPT 热图对比：`/api/ppt-comparison/scan-heatmaps`、`/api/ppt-comparison/generate`
  - 扫描热图文件夹，按“方法”组织，多方法并排布局生成对比 PPT

## 6. 数据模型（摘要）
来自 `models/database.py`：

- `File`：上传文件元数据（列信息、行数、磁盘路径、项目名等）
- `Analysis`：分析任务（类型、参数、状态、进度、结果路径等；支持 scheme/custom 扩展字段）
- `AnalysisResult`：分析产物（可视化、数据表、summary；保存文件路径与 mime_type）
- `CustomParameter`：保存的参数模板
- `Annotation`：可视化注释（位置、样式、内容）
- `SampleGroup`：样本分组

## 7. 已实现亮点（可用于汇报）
- 单命令启动与默认 SQLite 落地，环境搭建成本低。
- 统一分析（Scheme/Custom）将“字段映射 + 参数配置 + 分析执行”抽象为一条统一链路。
- 自动热图支持“文件夹级批量样本识别 + 分组 + 一键生成”，贴合真实数据组织方式。
- PPT 自动化：支持从模板解析并替换热图，减少人工排版时间；对比 PPT 进一步支持多方法并排展示。
- 异常体系（`exceptions.py`）为 API 返回提供结构化错误码（便于前端识别与提示）。

## 8. 风险与待确认事项（当前从代码检索得到的客观情况）
- 路由注册里引用了 `flask_app.routes.api_similarity`、`flask_app.routes.data_split`、`flask_app.routes.auth`，但在当前 `routes/` 目录未找到对应 `.py` 文件（仅发现 `__pycache__/*.pyc`）。
  - 影响：运行时可能出现 `ModuleNotFoundError`（具体取决于实际运行目录/导入路径是否一致、以及是否存在同名模块在其他位置）。
  - 建议：确认这些文件是否在仓库其他目录、是否被误删、或是否需要从旧版本回迁。
- `routes/api_analysis.py` 使用了相对导入风格（`from services...`、`from models...`），而其他模块多使用 `from flask_app.services...`。在不同启动方式/工作目录下可能引入 import 路径不一致风险。
  - 建议：统一包导入路径或固定启动入口（例如始终从 `flask_app/app.py` 启动并确保 `sys.path` 注入一致）。
- `unified_analysis_service.py` 文件头部出现乱码编码痕迹（注释中中文显示异常），不影响运行但影响可读性与维护性。

## 9. 下一步计划（建议）
- 补齐缺失路由模块（`api_similarity.py` / `data_split.py` / `auth.py`）或修正 `app.py` 中的注册逻辑。
- 将 API/Service 的导入路径风格统一，降低部署环境差异带来的问题。
- 为关键功能链路补充集成测试：
  - 上传->解析->建分析任务->生成结果
  - 自动热图扫描->生成
  - PPT analyze->replace->download
- 针对数据规模与并发，评估异步执行与结果落盘的性能边界（线程池并发、文件 IO、Matplotlib 渲染耗时等）。

---
生成时间：自动检索代码库后生成（基于当前仓库可见文件内容汇总）。

## 10. 新增：Pipeline 对比脚本整合（2026-03-04）
已将外部脚本 `E:\Desktop\南华\Work\WenJing Pan\pipeline_comparison_heatmap.py` 整合进 Flask 项目，并完成接口与前端入口联动。

### 10.1 设计原则
- 复用项目内已有能力，不重复构建：
  - 热图与相似度矩阵：复用 `AutoHeatmapService` + `HeatmapGenerator`
  - CDR3 共享导出：保持现有机制，可选启用
- 外部脚本只复用其特有能力：
  - 3-pipeline Venn 图生成
  - HTML 报告拼装

### 10.2 新增后端服务
- 文件：`flask_app/services/pipeline_comparison_integration_service.py`
- 核心入口：`PipelineComparisonIntegrationService.generate_pipeline_comparison(...)`
- 结果文件安全访问：`resolve_result_file(job_id, relative_path)`

输出目录规范：
- `<RESULTS_FOLDER>/pipeline_comparison/<job_id>/shared_analysis/`

典型产物：
- `pipeline_comparison_report.html`
- `metadata.json`
- `heatmap/**`
- `metric/**`
- `venn_ucdr3/**`
- `venn_abundance/**`

### 10.3 新增 API
在 `routes/api_auto_heatmap.py` 中新增：

1) 生成 Pipeline 对比报告  
- `POST /api/auto-heatmap/generate-pipeline-report`
- 必填：
  - `base_path`
- 常用可选：
  - `pipelines`（如 `["YXJ","DW","YPL"]` 或 `"YXJ,DW,YPL"`）
  - `samples`
  - `selected_chains` / `chains`
  - `output_name`
  - `enable_heatmap`
  - `enable_venn`
  - `enable_html_report`
  - `include_cdr3_analysis`
  - `embed_images`

2) 访问报告与资源文件  
- `GET /api/auto-heatmap/pipeline-comparison/results/<job_id>/<path:relative_path>`
- 支持访问 HTML、PNG、CSV、JSON 等产物，且带路径穿越防护。

### 10.4 前端入口
已在相似度热图页面增加按钮：
- 模板：`templates/analysis/similarity_heatmap.html`
- 脚本：`static/js/similarity_heatmap.js`
- 方法：`AutoHeatmap.generatePipelineComparisonReport()`

前端行为：
- 使用页面内参数表单输入 pipeline 顺序（默认 `YXJ,DW,YPL`）
- 调用 `POST /api/auto-heatmap/generate-pipeline-report`
- 成功后自动打开 `report_url`
- 参数支持本地复用（`localStorage`）：pipeline 顺序、任务名、是否生成 Venn、是否附带 CDR3 导出、是否内嵌图片

### 10.7 文案与编码清理
- 已清理 `routes/api_auto_heatmap.py` 中历史乱码提示文案（包括扫描、热图、预览、CDR3 导出相关错误信息）。
- 已修复页面 `Step 5` 里“生成热图”按钮乱码文本。

### 10.5 调用示例
```json
POST /api/auto-heatmap/generate-pipeline-report
{
  "base_path": "E:\\Desktop\\南华\\Work\\WenJing Pan\\260125",
  "pipelines": ["YXJ", "DW", "YPL"],
  "selected_chains": ["IGH", "IGK", "IGL"],
  "enable_heatmap": true,
  "enable_venn": true,
  "enable_html_report": true,
  "include_cdr3_analysis": false,
  "embed_images": false
}
```

### 10.6 已验证结果
- 服务层真实数据生成验证：通过
- API 层（POST/GET）烟测：通过
- 新增路由测试：`tests/test_pipeline_comparison_api.py`，4 项通过

已验证的结果文件示例：
- `flask_app/data/results/pipeline_comparison/smoke_full_app_pipeline_integration/shared_analysis/pipeline_comparison_report.html`
- `flask_app/data/results/pipeline_comparison/smoke_api_pipeline_integration/shared_analysis/metadata.json`
