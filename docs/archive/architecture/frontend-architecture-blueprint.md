# Frontend Architecture Blueprint — 基于原始单机架构的前端完善指南

> 创建：2026-06-30 | 版本：1.0
> 
> 本文档建立原始 Flask Jinja 应用（45 模板）与当前 React SPA（~30 页面组件）之间的 1:1 映射，明确每个页面的缺失功能、待完善 UI、和 API 对齐要求。
>
> **核心原则**：React SPA 恢复原始 Flask 单机架构中每个页面的完整功能 —— UI 布局、交互流程、字段定义、状态处理。

---

## 目录

1. [全局差距总览](#1-全局差距总览)
2. [Management 工作区](#2-management-工作区)
3. [Analysis 工作区](#3-analysis-工作区)
4. [ScriptHub 6 阶段向导](#4-scripthub-6-阶段向导)
5. [独立分析工具](#5-独立分析工具)
6. [基础设施与导航](#6-基础设施与导航)
7. [实施优先级](#7-实施优先级)

---

## 1. 全局差距总览

### 架构差异：文件系统 vs API-only

原始 Flask 使用 `directory_browser.html` 组件直接浏览服务器本地文件系统。React SPA 只能通过 API 访问数据。**所有文件浏览功能必须改为通过项目资产 API**。

### 模拟数据问题

以下组件使用了硬编码模拟数据，需要接入真实 API：

| 文件 | 模拟内容 | 需要的真实 API |
|------|----------|---------------|
| `ScriptHubWizard.tsx:handleInspect` | 检测结果 | `POST /api/script-hub/<module>/inspect` |
| `PdfExtractor.tsx:setTablePreview` | 提取表格预览 | `POST /api/pdf/extract` |
| `StatisticalComparison.tsx:multiResults` | 多文件汇总表 | `POST /api/statistical/analyze-batch` |
| `PptTools.tsx:handleDetectSlots` | PPT 槽位检测 | `POST /api/ppt/scan-images` |

### ScriptHubWizard 关键 bug

`ScriptHubWizard.tsx` 传递给 `Stage3ModuleConfig` 的 `modules={[]}` 是空数组，导致模块选择页面永远显示"没有可用的分析模块"。**必须改为从 `listJobModules()` API 获取的真实数据。**

### 全局缺失功能

| 功能 | 原始页面 | 当前状态 |
|------|----------|----------|
| 服务器端文件系统浏览器 | `directory_browser.html` | ❌ 不存在 — 需改为资产 API |
| 分析结果查看器（独立页面） | `analysis/results.html` | ❌ 只有内联 ResultViewer |
| 图片合并功能 | `analysis/results.html` merge modal | ❌ 不存在 |
| 进度覆盖层（含日志） | `sh-loading-overlay` | ❌ 只有骨架屏 |
| 分析失败重试 | `retryAnalysis()` | ❌ 不存在 |

---

## 2. Management 工作区

### 2.1 ManagementDashboard (`/management`)

**原始页面**: `templates/management.html`

**当前状态**: ✅ 基本功能完整

**待完善**:
- [ ] **推荐工作流程区块** — 原始页面有 4 步工作流指导（创建项目 → 上传资产 → 核对样本 → 启动分析），当前缺失
- [ ] **"前往分析" 直接跳转按钮** — 原始页面有 "Go to Analysis" CTA 按钮，当前需通过侧边栏切换
- [ ] **"数据上传" 导航入口** — 侧边栏缺少独立的上传入口（原始侧边栏有）

### 2.2 ProjectLibrary (`/management/projects`)

**原始页面**: `templates/projects.html`
**原始 JS**: `static/js/project_management.js`

**当前状态**: ✅ 基本功能完整，已有统计卡片 + 搜索 + 状态筛选

**待完善**:
- [ ] **筛选字段对齐** — 原始页面有独立的机构筛选、合作等级筛选字段。当前合并为单一搜索框
- [ ] **"含 PEP 项目" 统计指标** — 原始页面统计含 PEP 数据的项目数
- [ ] **表格视图模式** — 原始页面有表格视图（项目/机构/样本/资产/结果/时间/操作），当前只有卡片网格

**API 对齐**: ✅ `GET /api/projects`, `POST /api/projects` 已对齐

### 2.3 ProjectDetail (`/management/projects/:id`)

**原始页面**: `templates/project_detail.html`
**原始 JS**: `static/js/project_detail.js`

**当前状态**: ✅ 5 标签页齐全，Settings 已改为可编辑表单

**待完善**:
- [ ] **分析模块选择标签页** — 原始页面有"分析"标签页，列出 3 个分析入口卡片（Pipeline Comparison / ScriptHub / GO-KEGG）。当前 Overview 只有快捷操作卡片
- [ ] **样本标签页** — 原始页面有"样本信息"标签页，显示项目关联样本的预览表。当前缺失
- [ ] **资产标签页搜索/筛选** — 原始页面有资产搜索输入框 + 类型筛选下拉框。当前 `AssetTable` 可能缺少内联搜索
- [ ] **上传模态框** — 原始上传表单字段：
  ```
  assetTypeSelect: pep_data | profile_file | transcriptome_expression | 
                    sample_summary | raw_archive | pipeline_root
  fileSelector / folderSelector
  replaceExistingAssetsSwitch: boolean
  ```
- [ ] **Settings 合作等级选项对齐** — 原始使用 basic/standard/premium，当前使用 internal/public/collaboration/restricted
- [ ] **未保存更改指示器** — 原始有 `settingsDirtyBadge`，当前无

**API 对齐**:

| 操作 | 原始 API | 当前 API | 状态 |
|------|----------|----------|------|
| 加载项目 | `GET /api/projects/{id}` | 同 | ✅ |
| 更新设置 | `PATCH /api/projects/{id}` | `PUT` → 已改为 `PATCH` | ✅ |
| 上传资产 | `POST /api/projects/{id}/assets` (FormData) | 同 | ✅ |
| 删除资产 | `DELETE /api/projects/{id}/assets/{id}` | 同 | ✅ |
| 分组方案 | `POST/DELETE /api/projects/{id}/group-specs` | 只读展示 | ⚠️ 需增加 CRUD |

### 2.4 SampleRegistry (`/management/samples`)

**原始页面**: `templates/samples.html`
**原始 JS**: `static/js/sample_registry.js`

**当前状态**: ✅ 基本筛选 + 表格 + 编辑面板

**待完善**:
- [ ] **高级筛选** — 原始页面有可折叠的高级筛选区：
  ```
  project_id (text), institution (text), sequence_id (text),
  contain_method (text), iso_tag (text), spices (text, comma-sep),
  illness (text, comma-sep)
  ```
- [ ] **表格列补全** — 原始 12 列 vs 当前 9 列：
  ```
  缺失列: sequence_id, is_pe, institution
  ```
- [ ] **编辑表单字段补全** — 原始编辑模态框字段 vs 当前：
  ```
  缺失: sequence_id, institution, is_pe
  ```
- [ ] **PE 列筛选器** — 原始有 True/False/All 筛选，当前无

**API 对齐**: ✅ `GET /api/samples`, `PUT /api/samples/{id}`

### 2.5 Settings (`/management/settings`, `/analysis/settings`)

**原始页面**: `templates/settings.html`
**原始 JS**: `static/js/settings.js`（纯 localStorage）

**当前状态**: ✅ 可视化/导出/图表/热图设置齐全

**待完善**:
- [ ] **颜色方案补全** — 原始有 `RdYlBu_r`, `coolwarm`，当前缺失
- [ ] **导出格式补全** — 原始包括 `csv`, `zip`，当前只有 png/svg/pdf
- [ ] **图形尺寸单位** — 原始使用英寸，当前使用 px（需确认 API 期望）
- [ ] **"清除本地数据" 按钮** — 原始有，当前缺失
- [ ] **Vmin/Vmax 默认值** — 原始默认 vmin=0, vmax=1，当前默认 null

---

## 3. Analysis 工作区

### 3.1 UnifiedAnalysis (`/analysis`)

**原始页面**: `templates/simple_analysis.html`
**原始 JS**: 内联 `SimpleAnalysis` 类 (~500 行)

**当前状态**: ✅ 双列布局（配置左 + 结果右）

**待完善**:
- [ ] **方案选择器** — 原始从 `GET /api/analysis/schemes` 加载预设方案并渲染方案卡片网格。当前使用模块列表而非方案
- [ ] **字段映射表** — 原始有按字段名称+数据列下拉框+置信度徽章的映射表。当前使用简化的角色映射
- [ ] **文件选择** — 原始支持"已上传文件选择"和"新文件上传"双模式切换
- [ ] **链特定映射**（IG Metrics） — 原始对 IG Metrics 方案有链特定映射表（IGH/IGK/IGL 各自映射）
- [ ] **参数配置** — 原始字段：
  ```
  baselineSampleSelect: dropdown
  chartWidth: number (default 16)
  chartHeight: number (default 10)
  showValues: checkbox (default true)
  chains: checkbox group (IGH/IGK/IGL)
  ```
- [ ] **结果导出按钮** — 下载图表、下载数据、复制数据

**API 对齐**:

| 操作 | 原始 API | 当前 API | 状态 |
|------|----------|----------|------|
| 方案列表 | `GET /api/analysis/schemes` | 未调用 | ⚠️ 需接入 |
| 方案详情 | `GET /api/analysis/schemes/{id}` | 未调用 | ⚠️ 需接入 |
| 文件上传 | `POST /api/files/upload` | 使用 jobs API | ⚠️ 需对齐 |
| 执行分析 | `POST /api/analysis/execute-unified` | `POST /api/jobs` | ⚠️ 需对齐 |

### 3.2 JobMonitor (`/analysis/script-hub/jobs`)

**原始页面**: `templates/analysis/script_hub_jobs.html`
**原始 JS**: `static/js/script_hub_jobs.js`

**当前状态**: ✅ 筛选 + 统计栏 + 双面板 + SSE 实时更新

**待完善**:
- [ ] **"显示子任务" 切换** — 原始有 `showSubtasks` 复选框
- [ ] **删除记录按钮** — 原始详情面板中有删除按钮
- [ ] **执行历史** — 原始有 `#scriptJobHistory` 区域展示阶段历史
- [ ] **原始 JSON 查看** — 原始有预格式化 JSON 块
- [ ] **子结果展示** — 原始有 `#scriptJobChildResults` 区域

---

## 4. ScriptHub 6 阶段向导

> **这是整个前端最重要的页面，也是最需要完善的部分。**

**原始页面**: `templates/analysis/script_hub.html` (~2800 行)
**原始 JS**: `static/js/script_hub.js` (~1000+ 行)

### 4.1 关键 bug 修复

**`ScriptHubWizard.tsx` 传递 `modules={[]}` 导致模块选择无法使用**

`ScriptHubWizard.tsx` 必须改为：

```tsx
// 当前（错误）：
<Stage3ModuleConfig modules={[]} selectedModule={wizard.selectedModule} ... />

// 应该：
const modulesState = useApi(() => listJobModules(), []);
const modules = modulesState.status === "ready" ? modulesState.data.modules : [];
// ...
<Stage3ModuleConfig modules={modules} selectedModule={wizard.selectedModule} ... />
```

### 4.2 阶段 1: DataIntake vs 原始阶段 01-02

**原始功能**:
- 项目选择 + 完整目录树浏览器（文件系统 + 项目资产）
- 3 个资产篮子：PEP 路径（多选）、Profile 文件（单选）、Transcriptome（单选）
- 操作按钮：加入 PEP、设为 Profile、设为 Transcriptome、上传 Transcriptome
- 已选资产可移除

**当前缺失**:
- [ ] **目录树浏览器集成** — 原始使用 `directory_browser.html` 浏览本地文件系统
- [ ] **"上传 Transcriptome" 按钮** — 原始有文件上传功能
- [ ] **资产篮子视觉样式** — 原始有更丰富的路径输入+目录树集成

### 4.3 阶段 2: SourceInspection vs 原始阶段 03

**原始功能**:
- API 检测：扫描 PEP 目录和 Profile 文件
- 检测结果：样本数、链类型、PEP 文件数、Profile 列
- Profile 格式预览表、PEP 格式预览表
- 检测结果自动填充后续配置的建议值

**当前缺失**:
- [ ] **真实 API 调用** — 当前使用 `handleInspect` 生成模拟数据
- [ ] **需要接入**: `POST /api/script-hub/<selected_module>/inspect`

### 4.4 阶段 3: ModuleConfig vs 原始阶段 04-05

**原始功能**:
- 12 个分析模块的卡片网格（从 `/api/script-hub/modules` 加载）
- 每个模块有：图标、描述、推荐状态徽章
- **模块特定的完整配置 UI**（见下方详细列表）

**当前缺失**:
- [ ] **modules 空数组 bug** — 如上所述
- [ ] **加载真实模块列表** — 从 `listJobModules()` API

### 4.5 模块特定配置字段对照表

以下是原始 ScriptHub 阶段 05 中每个模块的配置字段。React 表单组件必须实现相同的字段。

#### db-alignment（数据库比对）

```
cdr3Column: dropdown (from file columns)
copyColumn: dropdown (from file columns)
profilePath: text input
profileSheet: dropdown (Excel sheet selector)
categoryMode: dropdown (single | cross)
categories: multi-select chips from field values
pathologyMode: radio (all | allowlist)
pathologyValues: textarea (when allowlist mode)
```

#### charts（综合图表：heatmap + treemap + chord）

```
Step 1: auto-detect scan summary (readonly)
Step 2: chain selection — clickable chips (IGH/IGK/IGL/TRA/TRB/TRD/TRG)
         with Select All / Invert / Clear buttons
Step 3: sample selection — clickable chips + Confirm Samples flow
Step 4: field mapping — CDR3 column, Copy column, V column, J column (dropdowns)
         + preview table
Step 5: content selection — checkboxes: Similarity Heatmap, Treemap, Chord
```

#### boxplot（箱线图）

```
datapointPath: dropdown (from project assets)
groupToggle: switch (default on)
groupFields: multi-select dropdown
fieldOrder: sortable chips (drag to reorder)
```

#### pep-analysis（PEP 共享分析）

```
pepDataDir: text (readonly, auto-detected)
selectedChains: clickable chips (detected chains)
profilePath: dropdown
groupFields: two-panel selector (field list + value preview)
pvalueThreshold: number (default 0.05)
minSampleThreshold: number (default 3)

Pipeline steps:
  Step 2-4: mandatory (locked, red left border)
  Step 5: usage frequency heatmap (checkbox, default on)
  Step 6: CDR3 classification stats (checkbox, default on)
  Step 7: permutation heatmap (checkbox, default on)
  Step 8: visualization heatmap (checkbox, default on)
  Toolbar: Select All Optional / Clear Optional buttons
```

#### pgen-analysis（Pgen/SoNNia）

```
pepDataDir: text (readonly, auto-detected)
profilePath: text (readonly)
selectedChains: clickable chips (TRD/TRG disabled)
sampleColumn: dropdown (default "sample")
categoryColumn: dropdown
species: dropdown (human | mouse)
SoNNia dependency: status indicator
```

#### topclone（Top Clone）

```
pepDataPath: text (readonly)
datapointPath: text (readonly)
modeToggle: switch (per-sample mode)
topN: number (default 10)
selectedChains: clickable chips
groupField: dropdown
```

#### umap（UMAP 降维）

```
nNeighbors: number (default 6)
minDist: number (default 0.01)
paramBegin: dropdown (from profile columns)
paramOver: dropdown (from profile columns)
```

#### volcano（火山图）

```
inputMode: dropdown (VJ usage | expression matrix)
pvalueThreshold: number (default 0.05)
dataDir: text (readonly, VJ usage mode) OR
expressionPath: text (readonly, expression mode)
groupPrefix: text (default "tpm_")
logFcThreshold: number (default 1)
comparisons: textarea (one per line)
```

#### go-kegg-enrichment（GO/KEGG 富集）

```
expressionPath: text (readonly)
groupPrefix: text (default "tpm_")
logFcThreshold: number (default 1)
pvalueThreshold: number (default 0.05)
comparisons: textarea (one per line)
pAdjustMethod: dropdown (none | BH | bonferroni)
showCategoryCount: number (default 20)
gseaToggle: switch (default on)
simplifyToggle: switch (default on)
R dependency: notice indicator
```

#### ml-analysis（随机森林分类）

```
mode: dropdown (Profile feature range | VJ usage feature range)
profilePath: text (readonly)
usagePath: text (readonly)
sampleColumn: dropdown
labelColumn: dropdown
filterColumn: dropdown
filterValue: text
paramBegin: dropdown
paramOver: dropdown
featureThreshold: number (default 0.003)
cvSplits: number (default 3)
rocCvSplits: number (default 7)
```

#### mait-nkt（MAIT/NKT 分析）

```
traSource: dropdown (Upload TRA file | PEP analysis result)
traPath: text (readonly)
sourceJobId: text (optional)
groupField: dropdown
groupOrder: text (optional, comma-separated)
```

#### profile（Profile 分析）

```
datapointPath: dropdown
classificationBegin: dropdown (from profile columns)
classificationOver: dropdown (from profile columns)
paramBegin: dropdown
paramOver: dropdown
grouptypeFields: multi-select
pvalueThreshold: number (default 0.05)
```

### 4.6 阶段 4: Execution vs 原始阶段 05 (运行)

**原始功能**:
- "检测数据" 按钮 → 调用 inspect API
- 运行摘要芯片（module, project, config keys, task name）
- "运行 [模块名]" 按钮 → 提交任务
- 全屏加载覆盖层：进度条 + 阶段名 + 详情文本 + 执行日志

**当前缺失**:
- [ ] **加载覆盖层** — 原始 `sh-loading-overlay` 含 animated progress bar + 日志
- [ ] **"检测数据" 分离按钮** — 原始将 Inspect 和 Run 作为两步分开

### 4.7 阶段 5: Results vs 原始阶段 06

**原始功能**:
- 成功/失败状态摘要
- 操作按钮：Open Viewer（新标签）、Download ZIP、Metadata
- 执行日志（深色主题等宽字体）
- 进度覆盖层在完成时自动消失

**当前状态**: ✅ 基本完整（ResultViewer + 下载按钮 + 元数据）

---

## 5. 独立分析工具

### 5.1 StatisticalComparison (`/analysis/statistical`)

**原始页面**: `templates/analysis/statistical_comparison.html`
**原始 JS**: 内联脚本 (~400 行)

**当前状态**: ⚠️ 使用模拟数据

**待完善**:
- [ ] **文件来源切换** — 原始有"上传新文件" / "已上传文件"模式切换。当前仅支持上传
- [ ] **从项目选择文件** — 原始可选择项目后从已上传文件列表中选择
- [ ] **列选择方式** — 原始是 `<select>` 下拉框（从文件列动态填充），当前是 `<input>` 文本输入
- [ ] **分组顺序** — 原始有 groupOrder 文本输入
- [ ] **图表标题** — 原始有 chartTitle 文本输入
- [ ] **P 值校正模式** — 原始有 correctionMode 下拉（per_dataset / global）
- [ ] **描述性统计表** — 原始显示 N/Mean/Std/Median/Min/Max
- [ ] **下载图表按钮** — 原始有
- [ ] **模拟数据替换** — 多文件摘要表当前使用 `Math.random()` 生成假数据

**API 对齐**:

| 操作 | 原始 API | 当前 API | 状态 |
|------|----------|----------|------|
| 解析列 | `POST /api/statistical/parse-columns` | 未调用 | ⚠️ 需接入 |
| 单文件 | `POST /api/statistical/analyze-direct` | `submitJob` | ⚠️ 需对齐 |
| 多文件 | `POST /api/statistical/analyze-batch` | `submitJob` | ⚠️ 需对齐 |

### 5.2 PdfExtractor (`/analysis/pdf-extractor`)

**原始页面**: `templates/analysis/pdf_extractor.html`

**当前状态**: ⚠️ 使用模拟表格预览

**待完善**:
- [ ] **已上传文件选择** — 原始有已上传 PDF 文件列表（带复选框），当前仅支持上传新文件
- [ ] **表格生成图表** — 原始有"生成图表"区域（样本选择 + 生成按钮），当前无
- [ ] **复制到剪贴板** — 原始有 copy 按钮，当前无
- [ ] **提取说明文本** — 原始有信息面板说明提取内容（同型百分比等）
- [ ] **图像索引默认值** — 原始默认 "15, -1"，当前默认空
- [ ] **新建项目按钮** — 原始在选择器旁有，当前无
- [ ] **模拟数据替换** — 表格预览当前使用硬编码模拟行

### 5.3 PptTools (`/analysis/ppt-tools`)

**原始页面**: `templates/analysis/ppt_heatmap.html`
**原始 JS**: `static/js/ppt_replace.js`

**当前状态**: ⚠️ 功能大幅简化 vs 原始

**待完善**:
- [ ] **多项目比较模式** — 原始有"单图替换"和"多项目对比"双模式
- [ ] **图片来源选择** — 原始有从分析任务下拉选择或手动输入路径
- [ ] **幻灯片缩略图** — 原始显示 PPT 结构预览含幻灯片缩略图
- [ ] **源图像标签页** — 原始有 4 个标签页（共享分析 / 网络图 / UpSet / 树图）
- [ ] **边框配置面板** — 原始有边框切换+宽度滑块
- [ ] **替换历史面板** — 原始有
- [ ] **映射预览模态框** — 原始有源→目标映射预览
- [ ] **下载设置模态框** — 原始有时间戳切换+摘要幻灯片切换+文件名预览
- [ ] **模拟槽位检测** — 当前硬编码 3 个假槽位，需接入 `POST /api/ppt/scan-images`

---

## 6. 基础设施与导航

### 6.1 Sidebar (`src/shared/components/Sidebar.tsx`)

**原始**: `templates/components/sidebar.html`

**待完善**:
- [ ] **"数据上传" 导航项** — 原始管理侧边栏有独立上传链接，当前无
- [ ] **"工具" 分隔符** — 原始在统计检验和 PDF/PPT 之间有"工具"分隔标签
- [ ] **标签文本对齐** — 原始 "PDF 表格提取" vs 当前 "PDF Extraction"；原始 "PPT 图表替换" vs 当前 "PPT Tools"

### 6.2 全局组件

**待新建**:
- [ ] **LoadingOverlay** — 全屏进度覆盖层（含进度条 + 阶段文本 + 执行日志），用于 ScriptHub 执行阶段
- [ ] **FieldMapper** — 通用的字段映射组件（从文件列到分析器字段），用于 UnifiedAnalysis 和 ScriptHub
- [ ] **ChainSelector** — 可点击芯片的链选择器组件，用于多个分析模块
- [ ] **TwoPanelSelector** — 双面板分类选择器（字段列表 + 值预览），用于 db-alignment 等模块
- [ ] **PipelineStepSelector** — 管道步骤可视化组件（强制/可选步骤 + 彩色左边框），用于 pep-analysis

---

## 7. 实施优先级

### P0 — 阻塞性 bug（立即修复）

| # | 问题 | 文件 |
|---|------|------|
| 1 | ScriptHub modules={[]} 导致模块选择无法使用 | `ScriptHubWizard.tsx` |
| 2 | 模拟数据替换为真实 API（inspect、表格预览、槽位检测） | 多个文件 |

### P1 — 核心功能补全（本周）

| # | 页面 | 缺失功能 |
|---|------|----------|
| 3 | ProjectDetail | 样本标签页 + 分组方案 CRUD + 资产标签页搜索 |
| 4 | SampleRegistry | 高级筛选 6 字段 + 表格列补全 + 编辑表单补全 |
| 5 | ScriptHub 阶段 3 | 12 个模块配置表单对齐原始字段定义 |
| 6 | UnifiedAnalysis | 方案选择器 + 字段映射表 + 参数配置 |
| 7 | StatisticalComparison | 文件来源切换 + 列解析 + 模拟数据替换 |

### P2 — UI 增强（下周）

| # | 页面 | 缺失功能 |
|---|------|----------|
| 9 | ManagementDashboard | 工作流指导区块 + "前往分析" 按钮 |
| 10 | ProjectLibrary | 表格视图模式 + "含 PEP" 统计 |
| 11 | Settings | 颜色方案补全 + 导出格式补全 + 清除数据按钮 |
| 12 | JobMonitor | 子任务切换 + 删除按钮 + 执行历史 + JSON 查看 |
| 13 | PdfExtractor | 已上传文件选择 + 图表生成 + 剪贴板复制 |
| 14 | PptTools | 多项目对比 + 幻灯片预览 + 边框配置 + 下载设置 |

### P3 — 全局基础设施

| # | 组件 | 用途 |
|---|------|------|
| 15 | LoadingOverlay | ScriptHub/PipelineComparison 执行阶段的进度覆盖层 |
| 16 | FieldMapper | UnifiedAnalysis 和 ScriptHub 的通用字段映射 |
| 17 | ChainSelector | 可点击芯片的链选择器 |
| 18 | TwoPanelSelector | 分类字段双面板选择器 |
| 19 | PipelineStepSelector | pep-analysis 管道步骤可视化 |

---

## 附录 A：原始 API 端点 — 前端调用对照表

| 原始 API 端点 | 方法 | 前端调用位置 | 状态 |
|---------------|------|-------------|------|
| `/api/projects` | GET | ManagementDashboard, ProjectLibrary, ScriptHub stage1 | ✅ |
| `/api/projects` | POST | ProjectLibrary, ProjectForm | ✅ |
| `/api/projects/{id}` | GET | ProjectDetail | ✅ |
| `/api/projects/{id}` | PATCH | ProjectDetail Settings tab | ✅ |
| `/api/projects/{id}/assets` | GET/POST/DELETE | ProjectDetail Assets tab | ✅ |
| `/api/projects/{id}/results` | GET | ProjectDetail Results tab | ✅ |
| `/api/projects/{id}/group-specs` | GET/POST/DELETE | ProjectDetail Group Specs tab | ⚠️ 只读 |
| `/api/projects/samples` | GET | SampleRegistry | ✅ |
| `/api/projects/samples/{id}` | PUT | SampleRegistry edit | ✅ |
| `/api/projects/samples/export` | GET | SampleRegistry export | ✅ |
| `/api/jobs` | GET | JobMonitor, ManagementDashboard | ✅ |
| `/api/jobs` | POST | ScriptHub stage4, all analysis pages | ✅ |
| `/api/jobs/modules` | GET | ScriptHub stage3 | ⚠️ 未正确集成 |
| `/api/jobs/{id}` | GET | JobMonitor detail | ✅ |
| `/api/jobs/{id}/results` | GET | ScriptHub stage5, JobMonitor | ✅ |
| `/api/jobs/{id}/events` | SSE | ScriptHub stage4, JobMonitor | ✅ |
| `/api/jobs/{id}/cancel` | POST | JobMonitor, ScriptHub stage4 | ✅ |
| `/api/analysis/schemes` | GET | UnifiedAnalysis | ⚠️ 未调用 |
| `/api/analysis/schemes/{id}` | GET | UnifiedAnalysis | ⚠️ 未调用 |
| `/api/analysis/execute-unified` | POST | UnifiedAnalysis | ⚠️ 需对齐 |
| `/api/script-hub/modules` | GET | ScriptHub stage3 | ⚠️ 需接入 |
| `/api/script-hub/{module}/inspect` | POST | ScriptHub stage2 | ⚠️ 使用模拟数据 |
| `/api/script-hub/{module}/run` | POST | ScriptHub stage4 | ⚠️ 需对齐 |
| `/api/statistical/parse-columns` | POST | StatisticalComparison | ⚠️ 未调用 |
| `/api/statistical/analyze-direct` | POST | StatisticalComparison single | ⚠️ 需对齐 |
| `/api/statistical/analyze-batch` | POST | StatisticalComparison multi | ⚠️ 需对齐 |
| `/api/auto-heatmap/scan-folder` | GET | — (PipelineComparison 已移除) | — |
| `/api/auto-heatmap/generate-pipeline-report` | POST | — (PipelineComparison 已移除) | — |
| `/api/ppt/scan-images` | POST | PptTools | ⚠️ 使用模拟数据 |
| `/api/ppt/load-image` | POST | PptTools config | ⚠️ 未调用 |
| `/api/ppt/render-slides` | POST | PptTools generate | ⚠️ 需对齐 |

## 附录 B：文件对照索引

| 原始 Flask 模板 | 当前 React 页面 | 完善度 |
|-----------------|-----------------|--------|
| `management.html` | `ManagementDashboard.tsx` | 85% |
| `projects.html` | `ProjectLibrary.tsx` | 90% |
| `project_detail.html` | `ProjectDetail.tsx` | 80% |
| `samples.html` | `SampleRegistry.tsx` | 75% |
| `settings.html` | `Settings.tsx` | 85% |
| `simple_analysis.html` | `UnifiedAnalysis.tsx` | 60% |
| `script_hub.html` | `ScriptHubWizard.tsx` + 6 stages | 40% |
| `script_hub_jobs.html` | `JobMonitor.tsx` | 80% |
| `pipeline_comparison.html` | — 已移除 | — |
| `statistical_comparison.html` | `StatisticalComparison.tsx` | 55% |
| `pdf_extractor.html` | `PdfExtractor.tsx` | 55% |
| `ppt_heatmap.html` | `PptTools.tsx` | 35% |
| `analysis/results.html` | 无独立页面（内联 ResultViewer） | 30% |
