# reference/vvv 与 djangoProject 数据库管理逻辑整合计划

## 目标范围

本计划只关注旧项目中的数据库管理、项目管理、样本管理、文件/资产管理、下载导出相关逻辑。

不整合旧分析脚本，不新增分析模块，不迁移 `anal_pipeline` 分析流程。

参考来源：

- `_reference/vvv`
  - Vue2 前端项目管理页
  - Vue2 样本检索页
  - 上传 datapoint / pep / sample summary / group specification 的交互
  - 项目处理文件下载、样本研究数据下载

- `_reference/djangoProject`
  - Django REST API
  - MySQL 用户表
  - MongoDB 项目、样本、datapoint、pep 数据管理逻辑
  - 文件上传、解压、入库、导出 zip

## 旧系统数据库管理结构

### MongoDB

旧 Django 使用 MongoDB 保存项目与样本数据：

- 项目库：`project`
- 项目集合：`project_detail`
- 样本集合：`sample_describe`
- 项目级数据库：以项目名为 database
- 项目内集合：
  - `datapoint`
  - `groupSpecification`
  - `<sample>__<CHAIN>_<projectName>`

相关文件：

- `_reference/djangoProject/appone/views/appProject.py`
- `_reference/djangoProject/appone/views/project.py`
- `_reference/djangoProject/appone/views/sample_browser.py`
- `_reference/djangoProject/appone/constant.py`

## 当前项目已有对应能力

当前项目已经具备一部分替代能力：

- 项目管理：
  - `flask_app/routes/api_projects.py`
  - `flask_app/services/project_service.py`

- 项目 assets：
  - `flask_app/services/project_asset_service.py`
  - `frontend/src/features/assets/`

- 样本注册表：
  - `flask_app/services/sample_registry_service.py`
  - `frontend/src/shared/api/samples.ts`

- 项目详情页：
  - `frontend/src/features/projects/`
  - `frontend/src/app/Dashboard.tsx`

- 用户/登录：
  - `flask_app/routes/auth.py`
  - `backend-api/app/api/auth.py`

## 当前主要缺口

### 1. 旧项目状态字段未完整对应

旧项目表中有这些状态字段：

- `is_datapoint`
- `is_pep`
- `is_GroupSpecification`
- `is_processed`

当前项目 assets 已经能表达是否上传了 profile/pep/transcriptome，但 UI 和 API 中未完全对齐旧状态语义。

建议：

- 在项目详情或项目列表中增加 asset 状态摘要。
- 不一定新增数据库字段，优先从 asset set 动态计算：
  - 是否有 datapoint/profile
  - 是否有 pep
  - 是否有 sample summary
  - 是否有 group specification
  - 是否有 results

### 2. groupSpecification 管理逻辑需要补齐

旧 Vue 支持动态添加：

- group 字段名
- group value 顺序，逗号分隔

旧 Django 保存到项目数据库的 `groupSpecification` 集合。

当前已有 group spec：

- `flask_app/services/group_spec_service.py`
- `flask_app/routes/api_projects.py`
- `frontend/src/shared/api/groupSpecs.ts`

建议：

- 对齐旧 `addGroupSpecification` 的结构兼容。
- 前端在项目详情中提供 group field + group order 的编辑 UI。
- 支持从 profile/sample summary 自动读取字段和值。
- 保存时统一进入当前 `ProjectGroupSpec` / group spec 服务，不恢复旧 Mongo collection 模型。

### 3. sample summary 表导入与样本检索字段需要补齐

旧 `sampleView.vue` 支持以下筛选字段：

- `id`
- `name`
- `sequence_id`
- `project_name`
- `institution`
- `spices`
- `chain_flag`
- `is_healthy`
- `illness`
- `is_Pe`
- `contain_method`
- `iso_tag`

旧后端：

- `page_research`
- `download_research_data`
- `get_field_list_by_parm`
- `edit_sample_data`
- `download_standard_sample_table`

建议：

- 检查当前 `SampleRecord` / sample registry 是否完整保留这些字段。
- 若字段不存在，用 JSON metadata 兼容，不强行扩表过多列。
- 前端样本页补齐多字段筛选。
- 增加 distinct value API，对齐旧 `get_field_list_by_parm`。
- 编辑样本时允许更新 metadata 字段。

### 4. 旧 research data zip 下载未完整对应

旧 `downloadresearchdata` 逻辑不是简单导出样本表，而是：

1. 按筛选条件找到样本。
2. 导出样本 metadata。
3. 找到对应项目数据库中的 datapoint。
4. 找到样本相关的 chain collection。
5. 打包成 zip 返回。

当前项目主要是 CSV 导出。

建议新增：

- 后端 API：
  - `POST /api/samples/export-research-zip`
  - 或挂在现有 `api_projects.py` 下

- 服务方法：
  - `sample_registry_service.export_research_zip(...)`

- 导出内容：
  - `sample_metadata.csv`
  - `datapoint.csv` 或 profile/datapoint asset
  - 匹配样本的 PEP 文件
  - `manifest.json`

- 前端：
  - 样本列表增加 `Download research ZIP`
  - 使用当前筛选条件导出

### 5. datapoint / pep 上传与 asset set 语义需要统一

旧 Vue 项目页支持：

- 上传 datapoint
- 上传 pep
- 上传 sample summary
- 上传 group 顺序

旧 Django 将 pep zip/gz 解压后按 sample + chain 写 Mongo collection。

当前项目已经改为 asset 文件管理。

建议：

- 不恢复 sample-chain Mongo collection。
- 保持文件资产为主。
- 在 asset set 中明确 asset type：
  - `profile` 或 `datapoint`
  - `pep`
  - `sample_summary`
  - `group_spec`
  - `transcriptome`

- 上传 pep zip/gz 时：
  - 解压到项目 asset set 目录
  - 记录 manifest
  - 扫描 sample、chain、列名
  - 供前端显示完整路径和状态

### 6. 项目下载处理文件逻辑需要对应当前 results

旧接口：

- `GET /downloadprocessfile/?projectName=...`

旧行为：

- 打包 `PROJECT_FILE/<projectName>` 目录。

当前项目结果分散在：

- ScriptHub results
- job results
- project assets

建议：

- 增加项目级导出 API：
  - `GET /api/projects/<project_id>/export`

- 支持选择导出内容：
  - assets
  - results
  - sample summary
  - group specs
  - manifest

- 默认生成 zip，不暴露服务器真实路径。

## 推荐实施阶段

## 2026-07-03 当前完善进展

本次已优先落地低风险的数据库管理能力，不涉及分析模块，也不加入注册功能。

已完成：

- 项目 assets 状态摘要：
  - 后端通过当前 `project_assets` 动态计算，不新增旧式状态字段。
  - 返回 `asset_status`：
    - `has_profile`
    - `has_datapoint`
    - `has_pep`
    - `has_sample_summary`
    - `has_group_spec`
    - `has_results`
    - `asset_set_count`
  - 同步补齐 `asset_counts`、`result_count`、`group_spec_count`。

- 项目级导出：
  - 新增 `GET /api/projects/{project_id}/export`。
  - 支持选择导出：
    - assets
    - results
    - group specs
    - manifest
  - 导出的 `manifest.json` 不写真实服务器路径，只保留资产 ID、类型、文件名、大小、asset set 和公开 metadata。
  - ZIP 内部按 `assets/`、`results/`、`group_specs/` 分类。

- 前端项目管理增强：
  - 项目卡片展示 Profile、PEP、Sample、Group、Results 状态 badge。
  - 项目 Database 页面提供导出选项和 `Export Project` 下载入口。

涉及文件：

- `backend-api/app/repositories/assets.py`
- `backend-api/app/services/asset_service.py`
- `backend-api/app/services/project_service.py`
- `backend-api/app/services/project_export_service.py`
- `backend-api/app/api/projects.py`
- `backend-api/app/schemas/domain.py`
- `frontend/src/shared/api/projects.ts`
- `frontend/src/features/projects/ProjectCard.tsx`
- `frontend/src/app/Database.tsx`

验证：

```bash
python -m py_compile backend-api/app/repositories/assets.py backend-api/app/services/asset_service.py backend-api/app/services/project_service.py backend-api/app/services/project_export_service.py backend-api/app/api/projects.py backend-api/app/schemas/domain.py
cd frontend && npm run typecheck
cd backend-api && pytest tests/test_repositories.py -q
```

结果：

- Python 编译通过。
- 前端 TypeScript 检查通过。
- `backend-api` 仓库层测试 `28 passed`。

### 阶段一：数据库结构与字段对齐审计

目标：确认当前项目是否完整承载旧数据管理字段。

检查文件：

- `flask_app/models/database.py`
- `flask_app/services/project_service.py`
- `flask_app/services/project_asset_service.py`
- `flask_app/services/sample_registry_service.py`
- `flask_app/services/group_spec_service.py`
- `flask_app/routes/api_projects.py`

输出：

- 字段映射表：
  - 旧字段
  - 当前字段
  - 是否缺失
  - 存储位置
  - 是否进入 metadata

### 阶段二：项目 assets 状态摘要

目标：在项目列表/详情中展示类似旧系统的上传状态。

后端：

- 在项目详情 API 中返回：
  - `has_profile`
  - `has_datapoint`
  - `has_pep`
  - `has_sample_summary`
  - `has_group_spec`
  - `has_results`
  - `asset_set_count`

前端：

- 项目卡片/项目详情展示状态。
- 不再显示旧式“是/否”硬编码，改为当前 UI badge。

### 阶段三：sample summary 与样本检索增强

目标：对齐旧 `sampleView.vue` 的样本筛选和编辑能力。

后端：

- 增强 sample registry 查询参数。
- 增加 distinct values 查询接口。
- 支持 metadata 字段编辑。

前端：

- 样本列表增加筛选项。
- 多选字段用下拉。
- 文本字段支持模糊搜索。
- 布尔字段显示为中文/英文可读 label。

### 阶段四：groupSpecification 管理

目标：对齐旧 `addGroupSpecification`，但存入当前 group spec 服务。

后端：

- 增加旧结构兼容解析：

```json
{
  "groupSpecification": {
    "treatment": ["control", "drug"],
    "disease": ["healthy", "case"]
  }
}
```

前端：

- 项目详情中增加 group order 编辑器。
- 支持从 profile 字段读取 group values。
- 支持拖拽排序。

### 阶段五：research data zip 导出

目标：对齐旧 `downloadresearchdata`。

后端：

- 新增 zip 导出服务。
- 根据当前筛选条件找到样本。
- 打包 sample metadata、profile/datapoint、PEP 文件和 manifest。

前端：

- 样本列表增加 `Download research ZIP`。
- 导出使用当前筛选条件。
- 下载前显示匹配样本数。

### 阶段六：项目级 export

目标：对齐旧 `downloadprocessfile`。

后端：

- 新增项目导出接口。
- 支持 assets/results/group specs/sample summary 组合导出。

前端：

- 项目详情增加 `Export project`。
- 支持勾选导出范围。

## 不做的事情

本计划明确不做：

- 不迁移旧分析模块。
- 不新增 CDR3 length / ECDF / Dominant Clone / Similar Clone 等分析。
- 不迁移 Deconv / CIBERSORT / GeneLink。
- 不恢复旧 Django 定时分析队列。
- 不恢复旧 Mongo sample-chain collection 作为主存储。
- 不整体迁移 Vue2 / Element UI 页面。
- 不加入注册功能。
- 不迁移邮箱验证码、用户注册、登录相关旧逻辑。

## 验证方式

### 后端

```bash
python -m py_compile flask_app/routes/api_projects.py flask_app/services/sample_registry_service.py flask_app/services/project_asset_service.py
pytest flask_app/tests/test_workspace_navigation.py
```

建议新增测试：

- 项目 assets 状态摘要
- sample summary 导入字段保留
- sample distinct values
- group spec 兼容旧结构
- research zip 导出内容
- project export zip 内容

### 前端

```bash
cd frontend
npm run typecheck
```

建议新增/更新测试：

- 项目卡片状态 badge
- 样本筛选表单
- group order 拖拽编辑
- research zip 下载按钮状态
- project export 弹窗

## 风险与约束

- 旧 Mongo collection 结构只能作为兼容参考，不作为当前主模型。
- 旧字段名不统一时，应放入 metadata 兼容，不要丢弃。
- 导出 zip 不应暴露服务器真实路径。
- 大文件导出需要异步或至少显示 loading，避免前端卡死。
- 项目 assets 与 sample registry 要保持引用关系，避免导出时找不到文件。
