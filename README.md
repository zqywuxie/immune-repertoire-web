# Immune Repertoire Web

基于 Flask 的免疫组库分析与报告生成项目，当前仓库主要围绕 `flask_app` 提供网页分析流程、结果导出和辅助脚本。

## 当前结构

```text
immune-repertoire-web/
├── flask_app/                         # 主应用
│   ├── app.py                         # Flask 启动入口
│   ├── config.py                      # 配置
│   ├── requirements.txt               # Python 依赖
│   ├── routes/                        # 页面和 API 路由
│   ├── services/                      # 分析、报表、渲染服务
│   ├── templates/                     # Jinja 页面模板
│   ├── static/                        # 前端脚本和样式资源
│   ├── models/                        # 数据模型
│   ├── migrations/                    # 数据库迁移
│   ├── data/                          # 运行期上传与结果目录
│   └── tests/                         # 测试
├── treemap/                           # 独立 treemap 脚本与示例
│   ├── generate_treemap_html.py       # 兼容保留的独立入口
│   ├── legacy_scripts/                # 历史批处理脚本
│   └── examples/                      # 示例数据与参考产物
├── aggregate_shared_analysis_report.py
├── pipeline_comparison_heatmap.py
└── standalone_heatmap_cli.py
```

## 主要功能

- 文件上传与管理
- 统一分析页面
- 相似度热图分析
- Treemap 分析与 HTML/PNG/ZIP 导出
- Pipeline 对比分析
- 统计比较分析
- PDF 提取
- PPT 热图替换

## 主要页面

- `/`：首页
- `/upload`：文件上传
- `/files`：文件管理
- `/analysis`：统一分析
- `/analysis/similarity-heatmap`：相似度热图
- `/analysis/treemap`：Treemap 分析
- `/analysis/pipeline-comparison`：Pipeline 对比
- `/analysis/statistical`：统计比较
- `/analysis/pdf-extractor`：PDF 提取
- `/analysis/ppt-heatmap`：PPT 热图替换

## 快速启动

### 1. 创建环境并安装依赖

```bash
cd flask_app
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 启动应用

在仓库根目录执行：

```bash
python flask_app/app.py
```

默认地址：

```text
http://127.0.0.1:5000
```

## Treemap 相关说明

- Flask 正式使用的 treemap 渲染逻辑位于 `flask_app/services/treemap_renderer.py`
- Treemap 报表生成逻辑位于 `flask_app/services/treemap_report_service.py`
- `treemap/generate_treemap_html.py` 仅作为兼容保留的独立脚本入口
- `treemap/legacy_scripts/` 下是历史批处理脚本，已改为复用 `flask_app` 内部渲染器

## 开发说明

- 运行期数据默认写入 `flask_app/data/`
- 测试缓存、临时运行目录和本地工具目录已加入 `.gitignore`
- 仓库中仍可能存在个别本地权限受限的测试临时目录，不影响正常开发和运行

## GitHub

远程仓库：

```text
git@github.com:zqywuxie/immune-repertoire-web.git
```
