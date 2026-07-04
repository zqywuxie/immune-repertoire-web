# 项目必需分析数据与 Task Results Viewer 重构计划

## 背景

当前项目详情页的 Assets 上传逻辑将 `PEP paths + Profile + Transcriptome` 作为一个 dataset/set 注册：

- PEP：通过服务器路径注册，支持多个路径。
- Profile：通过文件上传。
- Transcriptome：通过文件上传，当前已标注 optional。

用户新要求：

1. 对于一个项目，必需分析数据为：
   - `PEP 路径`
   - `Profile`
2. `转录组 Transcriptome` 是可选分析数据。
3. 项目还可能包含与分析无关的“项目相关文件”，也要支持上传，并能在项目详情中查看。
4. Task/Job 右侧 `Results` tab 不再嵌入展示 viewer 界面，只保留通过 viewer 按钮跳转查看。

本计划只覆盖数据管理与 task UI 行为，不新增注册/登录功能，不改分析算法。

## 当前涉及文件

### 项目详情与资产管理

- `frontend/src/pages/management/ProjectDetail.tsx`
  - 项目详情 tabs：Overview / Assets / Results / Samples / Group Specs / Settings。
  - Assets tab 当前渲染 `AssetUpload` 与 `AssetTable`。
  - Results tab 当前渲染分析结果 `AssetTable`。

- `frontend/src/features/assets/AssetUpload.tsx`
  - 当前负责注册 data set。
  - `SetEntry` 包含：
    - `pepPaths`
    - `profileFile`
    - `transcriptomeFile`
  - `handleUpload` 当前只要任意一种输入存在即可提交。

- `frontend/src/features/assets/AssetTable.tsx`
  - 当前资产列表已支持：
    - 多选
    - 批量下载
    - 删除
    - Set 过滤
    - PEP 完整路径展示

- `frontend/src/features/assets/assetSets.ts`
  - `buildAssetSets()` 当前只把 pep/profile/datapoint/transcriptome/expression 识别为 input asset。
  - 项目附属文件不应进入分析 dataset/set。

- `frontend/src/shared/api/projects.ts`
  - `uploadProjectAssets()` 支持传入 `assetType` 与 `assetSet`。
  - 可以复用上传通道新增 `project_file` 类型。

- `backend-api/app/api/assets.py`
  - FastAPI 资产上传接口 `/api/projects/{project_id}/assets` 支持任意 `asset_type`。
  - 注册路径接口 `/api/projects/{project_id}/assets/register` 支持任意 `asset_type`。
  - 因此新增项目文件优先只需前端传 `asset_type=project_file`，后端保持兼容即可。

### Task / Job 右侧结果展示

- `frontend/src/features/jobs/JobDetailPanel.tsx`
  - 当前右侧 panel 有 `Config / Progress / Results` 三个 tab。
  - Results tab 会调用 `getJobResults(jobId)`，然后直接渲染 `<ResultViewer outputs={...} />`。
  - 这会在 task 右侧嵌入 html/image/csv/pdf 等 viewer。

- `frontend/src/features/jobs/JobResultPanel.tsx`
  - 也是结果展示 panel，含模块筛选、结果筛选、`OutputCard` 嵌入预览。
  - 如果 task 右侧也使用它，后续也应避免嵌入 viewer。

- `frontend/src/features/results/ResultViewer.tsx`
  - 通用嵌入式结果 viewer。
  - 当前支持 html iframe、image、pdf、csv/json 下载/预览。
  - 本次不删除该组件，只是不在 task 右侧使用。

## 推荐实施方案

### 一、拆分 Assets 页的两类上传

在 `ProjectDetail.tsx` 的 Assets tab 中拆成两个明确区域：

1. `Analysis Data Sets`
   - 使用重构后的 `AssetUpload`。
   - 只负责分析 set：
     - 必填：PEP paths
     - 必填：Profile
     - 可选：Transcriptome

2. `Project Files`
   - 新增轻量组件，例如：
     - `frontend/src/features/assets/ProjectFileUpload.tsx`
   - 用于上传项目相关文件。
   - 上传类型统一使用：
     - `asset_type = "project_file"`
   - 不传 `assetSet`，或 metadata 中标记：
     - `asset_scope: "project_file"`
   - 在项目详情中单独展示，不参与 ScriptHub dataset 检索。

### 二、调整分析 set 的必填校验

修改 `AssetUpload.tsx`：

- `validSets` 校验从“任意一种输入存在”改为：
  - 新建 set：
    - `pepPaths.length > 0`
    - `profileFile !== null`
  - 更新 existing set：
    - 当前 set 已有 PEP 或本次新增 PEP
    - 当前 set 已有 Profile 或本次上传 Profile
  - Transcriptome 仅作为可选字段。

推荐新增 helper：

```ts
function hasRequiredAnalysisData(set: SetEntry) {
  const hasPep = set.existingPepPaths.length > 0 || set.pepPaths.length > 0;
  const hasProfile = Boolean(set.existingProfilePath || set.profileFile);
  return hasPep && hasProfile;
}
```

UI 提示：

- PEP Paths 标记 `required`。
- Profile File 标记 `required`。
- Transcriptome 标记 `optional`。
- 提交按钮 disabled 时显示空状态或提示：
  - `Analysis set requires at least one PEP path and one Profile file.`
  - `分析数据集需要至少一个 PEP 路径和一个 Profile 文件。`

### 三、项目文件上传与查看

新增 `ProjectFileUpload.tsx`：

- 使用已有 `FileDropZone`。
- 支持多个文件上传。
- 调用：

```ts
uploadProjectAssets(projectId, {
  assetType: "project_file",
  files,
  replaceExisting: false,
});
```

在 `ProjectDetail.tsx` 中分类：

```ts
const analysisAssetList = assets.filter(isAnalysisInputAsset);
const projectFileList = assets.filter((a) => a.asset_type === "project_file");
```

Assets tab 展示建议：

- 上半部分：`Analysis Data Sets`
  - `AssetUpload`
  - `AssetTable` 展示 pep/profile/transcriptome
  - 保留 set filter

- 下半部分：`Project Files`
  - `ProjectFileUpload`
  - `AssetTable` 展示 project_file
  - 不显示 set filter
  - 保留 preview/download/delete

### 四、避免项目文件进入 ScriptHub assets set

修改或确认 `assetSets.ts`：

- `isInputAsset()` 不应把 `project_file` 识别为分析 input。
- 当前实现只包含 pep/profile/datapoint/transcriptome/expression，因此项目文件默认不会进入 set。
- 若后续 backend 返回 `asset_type=file/document/attachment`，建议明确排除：

```ts
if (["project_file", "attachment", "document"].includes(type)) return false;
```

### 五、Task 右侧 Results tab 去掉嵌入 viewer

修改 `JobDetailPanel.tsx`：

- 保留 `Results` tab，但不渲染 `<ResultViewer />`。
- Results tab 只展示：
  - job 状态
  - 输出数量
  - 一个 `Open Viewer` 按钮
  - 一个或多个 `Download ZIP` / `Download output` 按钮
  - registered assets 下载入口可保留为普通链接

推荐逻辑：

```ts
const viewerOutput =
  outputs.find((o) => o.kind === "html") ||
  outputs.find((o) => /viewer|report/i.test(o.label || "")) ||
  outputs[0];
```

按钮行为：

- `Open Viewer`
  - 打开 `viewerOutput.url`
  - `target="_blank"`
  - 不在右侧 panel 中 iframe 展示

- `Download ZIP`
  - 优先打开 kind 为 zip 的 output
  - 多个 zip 时展示多个按钮或下拉

需要删除/不再使用：

```tsx
<ResultViewer outputs={resultsState.result.outputs || []} />
```

### 六、JobResultPanel 的一致性处理

如果 `JobResultPanel.tsx` 仍在 task/history 右侧被使用，则同步调整：

- 增加 prop：

```ts
previewMode?: "embedded" | "links";
```

- task 右侧传 `previewMode="links"`。
- `links` 模式只展示按钮列表，不渲染 `OutputCard`。

如果当前 task 右侧只使用 `JobDetailPanel.tsx`，则本次可以先只改 `JobDetailPanel.tsx`，保留 `JobResultPanel` 给独立结果页面使用。

### 七、后端兼容性

本次原则上不需要后端 schema 变更：

- FastAPI `/api/projects/{project_id}/assets` 已支持任意 `asset_type`。
- Flask legacy `/api/projects/<project_id>/assets` 也保留资产列表能力。
- 新增项目文件用 `project_file` 类型即可。

建议补充后端约束但不强制：

- 上传 `asset_type=project_file` 时不要写入 `asset_set`。
- 如果前端传了 `asset_set`，后端仍接受，保持兼容。

## 修改文件清单

建议修改：

1. `frontend/src/features/assets/AssetUpload.tsx`
   - 分析 set 必填校验：PEP + Profile。
   - Transcriptome 保持 optional。
   - 提交提示与按钮 disabled 逻辑优化。

2. `frontend/src/features/assets/ProjectFileUpload.tsx`
   - 新增项目文件上传组件。

3. `frontend/src/pages/management/ProjectDetail.tsx`
   - Assets tab 拆为 Analysis Data Sets 和 Project Files。
   - 分别过滤 assets 并展示不同表格。

4. `frontend/src/features/assets/assetSets.ts`
   - 明确排除 `project_file` / attachment 类资产，不进入分析 set。

5. `frontend/src/features/jobs/JobDetailPanel.tsx`
   - Results tab 去掉嵌入 `ResultViewer`。
   - 改为 viewer/download 按钮跳转。

按需修改：

6. `frontend/src/features/jobs/JobResultPanel.tsx`
   - 如果 task 右侧仍使用它，则增加 links-only 模式。

7. `frontend/src/__tests__/...`
   - 新增或更新资产上传与 job detail panel 测试。

## 验证方式

### 前端类型检查

```bash
cd frontend
npm run typecheck
```

### 单元测试建议

新增或更新测试：

1. `AssetUpload`
   - 只有 PEP 时不能提交。
   - 只有 Profile 时不能提交。
   - PEP + Profile 可以提交。
   - PEP + Profile + Transcriptome 可以提交。
   - existing set 已有 PEP/Profile 时允许补充 Transcriptome。

2. `ProjectDetail`
   - `project_file` 出现在 Project Files 区域。
   - `project_file` 不出现在 Analysis Data Sets 表格。

3. `JobDetailPanel`
   - Results tab 不渲染 iframe/image viewer。
   - 有 html output 时显示 `Open Viewer`。
   - 有 zip output 时显示下载按钮。

### 手工验收

1. 进入项目详情 Assets。
2. 新建 Set：
   - 不填 PEP/Profile 时按钮不可提交。
   - 只填 Transcriptome 时不可提交。
   - 填 PEP + Profile 后可提交。
3. 上传项目相关文件：
   - 文件出现在 Project Files。
   - 可以 preview/download/delete。
   - 不进入 ScriptHub 资产 set。
4. 进入 Tasks，点击一个已完成 job。
5. 右侧 Results tab：
   - 不嵌入 viewer。
   - 点击 Viewer 按钮跳转新页面/新标签查看。
   - ZIP 或其他输出可下载。

## 风险与兼容

- 不改变已有 pep/profile/transcriptome 的 asset_type。
- `project_file` 是新增类型，旧数据不受影响。
- ScriptHub set 依旧由 `assetSets.ts` 的 input asset 判断控制，项目文件不会污染分析数据。
- Task 右侧只改变展示方式，不改变结果生成、metadata、viewer 路由。
