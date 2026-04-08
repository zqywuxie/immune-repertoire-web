# SSH Linux 远端数据源开发文档

## 1. 目标范围

本方案只针对一类场景：

- 需要通过 SSH 登录的 Linux 服务器
- 通过 SFTP 浏览远端目录
- 选择远端目录后同步到本地缓存
- 再复用现有分析模块执行分析

不包含以下范围：

- SMB / NAS / FTP
- Windows 共享盘
- 浏览器直接连接远端服务器
- 在远端服务器原地执行分析
- 允许用户手工输入任意 SSH 主机并即时连接


## 2. 当前问题

当前项目中的分析模块本质上都依赖本地路径：

- 前端输入 `base_path`
- 后端直接使用本地文件系统扫描目录
- 结果写入本地 `RESULTS_FOLDER`

这适合：

- 本机目录
- 已挂载到本机的共享目录

这不适合：

- 只能通过 SSH/SFTP 访问的 Linux 目录


## 3. 核心设计

采用固定流程：

`SSH/SFTP 浏览远端目录 -> 同步到本地缓存 -> 复用现有分析模块`

这个设计的核心价值：

1. 现有分析模块几乎不用重写
2. 远端访问逻辑和分析逻辑彻底分离
3. 风险远低于“直接在远端文件系统上运行分析”


## 4. 一期目标

第一期只做最小可用版本：

1. 支持配置 SSH Linux 数据源
2. 支持测试 SSH 连接
3. 支持浏览远端 Linux 目录
4. 支持选择远端目录并同步到本地缓存
5. 支持把缓存目录接入现有分析模块
6. 第一批先接：
   - Chord Diagram
   - Similarity Heatmap


## 5. 二期目标

后续再扩展：

1. 接入 Treemap
2. 接入 Pipeline Comparison
3. 支持私钥登录
4. 支持缓存复用
5. 支持缓存清理
6. 支持数据源权限分级


## 6. 总体架构

```text
前端分析页面
  -> 选择数据来源：本地 / SSH Linux
  -> 选择 SSH 数据源
  -> 浏览远端目录
  -> 选择目录
  -> 发起同步任务

后端远端数据模块
  -> SSH 数据源配置管理
  -> SFTP 目录浏览
  -> 远端目录同步到本地缓存
  -> 返回 local_cache_path

现有分析模块
  -> 使用 local_cache_path 继续执行
```


## 7. 为什么不直接在远端运行分析

因为当前项目大量依赖本地文件系统接口：

- `Path`
- `os.walk`
- `open`
- `gzip.open`
- 文件表头预览
- 多文件递归扫描

如果直接把这些分析逻辑改成基于 SFTP provider，改动会扩散到：

- `auto_heatmap_service.py`
- `api_auto_heatmap.py`
- `treemap_report_service.py`
- `chord_report_service.py`
- pipeline comparison 相关服务

这会显著增加开发风险和维护成本。


## 8. 推荐接入点

建议新增以下模块：

- `flask_app/routes/api_remote_sources.py`
- `flask_app/services/remote_data_source_service.py`
- `flask_app/services/ssh_file_provider.py`
- `flask_app/services/remote_sync_service.py`

这些模块的职责很明确：

- `remote_data_source_service.py`
  管理 SSH Linux 数据源配置

- `ssh_file_provider.py`
  负责 SSH/SFTP 连接、目录浏览、文件下载

- `remote_sync_service.py`
  负责将远端目录同步到本地缓存并跟踪任务进度

- `api_remote_sources.py`
  为前端提供统一的远端数据源 API


## 9. 数据源模型

建议采用以下结构：

```json
{
  "id": "linux_server_a",
  "name": "Linux Server A",
  "type": "ssh_linux",
  "host": "10.10.10.5",
  "port": 22,
  "username": "analysis_user",
  "auth_type": "password",
  "password": "server-side-only",
  "private_key_path": "",
  "root_path": "/data/repertoire",
  "enabled": true
}
```

说明：

- `type` 固定为 `ssh_linux`
- `root_path` 是允许浏览的根目录
- 密码或私钥只保存在服务端


## 10. 本地缓存设计

### 10.1 新增配置

建议在 `flask_app/config.py` 增加：

```python
REMOTE_CACHE_FOLDER = BASE_DIR / 'data' / 'remote_cache'
```

### 10.2 缓存目录结构

建议：

```text
flask_app/data/remote_cache/
  <source_id>/
    <yyyyMMdd>/
      <sync_job_id>/
        ...
```

### 10.3 一期缓存策略

第一期只做简单策略：

1. 每次同步单独生成一个缓存目录
2. 保留远端目录相对结构
3. 不做缓存复用

后续可以增加：

1. 相同目录复用缓存
2. 自动清理历史缓存
3. 缓存大小限制


## 11. 安全边界

必须遵守以下规则：

1. 用户不能在前端输入任意主机地址
2. 用户只能选择后端预配置好的 SSH Linux 数据源
3. 浏览路径必须位于该数据源的 `root_path` 之下
4. 不在前端存储密码或私钥
5. 日志中不得输出敏感凭据


## 12. 同步规则

### 12.1 支持同步的文件类型

- `.csv`
- `.csv.gz`
- `.tsv`
- `.tsv.gz`
- `.txt`
- `.txt.gz`

### 12.2 跳过目录

- `.git`
- `__pycache__`
- `node_modules`
- `.pytest_cache`
- `.vscode`
- `.idea`

### 12.3 同步方式

第一期建议：

1. 递归遍历远端目录
2. 只下载支持的分析文件
3. 忽略无关文件
4. 保持目录结构


## 13. 后端服务设计

### 13.1 `remote_data_source_service.py`

职责：

- 读取 SSH Linux 数据源配置
- 列出可用数据源
- 按 `source_id` 获取单个数据源
- 测试连接

建议接口：

```python
class RemoteDataSourceService:
    def list_sources(self) -> list[dict]: ...
    def get_source(self, source_id: str) -> dict: ...
    def test_connection(self, source_id: str) -> dict: ...
```

### 13.2 `ssh_file_provider.py`

职责：

- 建立 SSH/SFTP 连接
- 浏览远端 Linux 目录
- 判断文件/目录
- 下载文件

建议接口：

```python
class SSHFileProvider:
    def connect(self): ...
    def list_dir(self, remote_path: str) -> list[dict]: ...
    def exists(self, remote_path: str) -> bool: ...
    def is_dir(self, remote_path: str) -> bool: ...
    def walk_files(self, remote_root: str) -> list[str]: ...
    def download_file(self, remote_path: str, local_path: Path) -> None: ...
```

### 13.3 `remote_sync_service.py`

职责：

- 创建同步任务
- 把远端目录同步到本地缓存
- 提供任务状态查询

建议接口：

```python
class RemoteSyncService:
    def start_sync(self, source_id: str, remote_path: str) -> dict: ...
    def get_task(self, task_id: str) -> dict: ...
    def sync_directory(self, source_id: str, remote_path: str) -> Path: ...
```


## 14. API 设计

### 14.1 获取数据源列表

`GET /api/remote-sources`

返回：

```json
{
  "success": true,
  "sources": [
    {
      "id": "linux_server_a",
      "name": "Linux Server A",
      "type": "ssh_linux",
      "host": "10.10.10.5",
      "port": 22,
      "username": "analysis_user",
      "root_path": "/data/repertoire",
      "enabled": true
    }
  ]
}
```

### 14.2 测试连接

`POST /api/remote-sources/test`

请求：

```json
{
  "source_id": "linux_server_a"
}
```

### 14.3 浏览远端目录

`POST /api/remote-sources/browse`

请求：

```json
{
  "source_id": "linux_server_a",
  "path": "/data/repertoire"
}
```

返回：

```json
{
  "success": true,
  "current_path": "/data/repertoire",
  "entries": [
    {
      "name": "project_01",
      "path": "/data/repertoire/project_01",
      "is_dir": true,
      "size": 0,
      "modified_time": "2026-04-07 12:00:00"
    }
  ]
}
```

### 14.4 启动同步任务

`POST /api/remote-sources/sync`

请求：

```json
{
  "source_id": "linux_server_a",
  "remote_path": "/data/repertoire/project_01"
}
```

返回：

```json
{
  "success": true,
  "task_id": "remote_sync_abc123",
  "status_url": "/api/remote-sources/sync-task/remote_sync_abc123"
}
```

### 14.5 查询同步任务

`GET /api/remote-sources/sync-task/<task_id>`

返回：

```json
{
  "success": true,
  "task_id": "remote_sync_abc123",
  "status": "completed",
  "progress": 100,
  "stage": "completed",
  "detail": "同步完成",
  "result": {
    "source_id": "linux_server_a",
    "remote_path": "/data/repertoire/project_01",
    "local_cache_path": "E:/.../flask_app/data/remote_cache/linux_server_a/20260407/remote_sync_abc123"
  }
}
```


## 15. 前端设计

### 15.1 统一交互

分析页面增加“数据来源”：

- 本地路径
- SSH Linux

若选择 SSH Linux：

1. 选择服务器
2. 浏览远端目录
3. 选择目录
4. 发起同步
5. 同步成功后，将 `local_cache_path` 回填到现有分析流程

### 15.2 第一批接入页面

- Chord Diagram
- Similarity Heatmap

### 15.3 第二批接入页面

- Treemap
- Pipeline Comparison


## 16. 技术实现建议

建议使用：

- `paramiko`

原因：

1. 适合 SSH/SFTP
2. Python 生态成熟
3. 易于统一服务端连接管理


## 17. 推荐开发顺序

建议按这个顺序做：

1. 在 `config.py` 增加 `REMOTE_CACHE_FOLDER`
2. 实现 `remote_data_source_service.py`
3. 实现 `ssh_file_provider.py`
4. 实现 `remote_sync_service.py`
5. 新增 `api_remote_sources.py`
6. 在设置页增加 SSH Linux 数据源管理
7. 先把 Chord Diagram 接上
8. 再把 Similarity Heatmap 接上
9. 最后扩展到 Treemap 和 Pipeline Comparison


## 18. 验收标准

第一期通过标准：

1. 能列出 SSH Linux 数据源
2. 能成功测试 SSH 连通性
3. 能浏览远端 Linux 目录
4. 能选择目录并同步到本地缓存
5. 能返回可用的 `local_cache_path`
6. Chord Diagram 能基于该缓存目录正常分析
7. Similarity Heatmap 能基于该缓存目录正常分析


## 19. 结论

当前项目若要支持“通过 SSH 登录的 Linux 服务器中的数据选择和分析”，最稳妥的实现方式是：

`SSH/SFTP 浏览远端目录 -> 同步到本地缓存 -> 复用现有本地分析模块`

这个方案最符合当前代码结构，也最适合逐步上线。
