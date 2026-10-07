> 2026-10-07新增数据集说明表；普通更新、依赖镜像更新、版本记录及回退见[升级与回退](operations/release-upgrade-rollback.md)。

# Docker 运行与部署

在项目根目录操作。依赖安装、测试、构建和分析均在 Linux 容器内执行。


## 分析基础镜像：构建一次，日常复用

完整环境改为两层：`Dockerfile.runtime` 只安装 Python/R/系统依赖；`Dockerfile.analysis` 只复制业务代码并验证环境。日常先执行 `bash init-env.sh` 拉取代码并准备配置，编辑 `.env` 后再运行 `bash deploy.sh` 构建应用和前端，不重新安装 R/Python 依赖。首次部署前必须准备下面的基础镜像；仅导入 Bioconductor 原始镜像不够。

### 1. 本地构建与导出（项目根目录）

服务器 `uname -m` 为 `x86_64` 时使用 `linux/amd64`；为 `aarch64` 时改为 `linux/arm64`，并在该架构完成依赖验证。

```bash
git pull --ff-only origin main
docker build --platform linux/amd64 --progress plain -f docker/app/Dockerfile.runtime -t immune-analysis-runtime:3.20-ml .
docker save -o immune-analysis-runtime-3.20-ml.tar immune-analysis-runtime:3.20-ml
scp immune-analysis-runtime-3.20-ml.tar zhengqinyun@服务器IP:/colddata/SCigblast/platform/
```

归档放在仓库外或上传后移走，避免部署的未跟踪文件检查阻止拉取。在 Windows PowerShell 可将导出路径直接设为 `E:\Desktop\immune-analysis-runtime-3.20-ml.tar`。首次构建仍需要下载并安装依赖，成功后才执行导出；已完成的旧构建层可复用。

### 2. 服务器导入并配置

```bash
docker load -i /colddata/SCigblast/platform/immune-analysis-runtime-3.20-ml.tar
cd /colddata/SCigblast/platform/immune-repertoire-web
bash init-env.sh
nano .env
```

确认 `.env` 使用：

```dotenv
ANALYSIS_RUNTIME_IMAGE=immune-analysis-runtime:3.20-ml
APP_DOCKERFILE=docker/app/Dockerfile.analysis
ANALYSIS_FLAVOR=full
```
已有部署的 .env 不会被 init-env.sh 覆盖；若仍设置 immune-analysis-runtime:3.20-v1，请在导入新版运行时镜像后手动改为 immune-analysis-runtime:3.20-ml。应用镜像构建会比对基础镜像内记录的 Python/R 依赖清单，不匹配时会停止构建，避免产生依赖状态不明的应用镜像。

保留已设置的数据路径、UID/GID、端口和密钥，然后执行 `bash deploy.sh`。应用镜像从本机导入的基础镜像构建；不要启用 `--pull` 强制向远端查找这个本地标签。前端 npm 构建、数据库等其他镜像仍可能需要网络，并非完全离线部署。

### 3. 后续更新

普通业务代码或分析脚本变化：服务器依次执行 `bash init-env.sh`、编辑 `.env`、`bash deploy.sh`。Python 依赖清单、R 安装脚本或 `Dockerfile.runtime` 变化：先重新构建基础镜像，使用新标签（例如 `3.20-v2`）导出上传，服务器导入并修改 `ANALYSIS_RUNTIME_IMAGE`，再部署。应用构建会比对环境快照，依赖不一致时停止并提示，不能跳过检查。旧基础镜像保留供回退。

2026-09-23 起 D1-Sample 依赖的 GSVA 已加入 R 依赖安装清单及完整运行时检查。当前本地镜像 `immune-analysis-runtime:3.20-pathway` 已构建并通过完整运行时检查；GSVA 2.0.7 ssGSEA 合成矩阵调用通过。镜像约 9.19 GB，比之前的 3.20 运行时约增加 0.30 GB。服务器部署前须导入该镜像并将 `.env` 的 `ANALYSIS_RUNTIME_IMAGE` 更新为同一标签。该运行时依赖准备完成不等于 D1-Sample 面板已接入平台。

构建基础镜像时可通过 `--build-arg BIOCONDUCTOR_IMAGE=可信地址` 改变原始 Bioconductor 来源；日常应用构建只使用 `ANALYSIS_RUNTIME_IMAGE`。

## 启动

Linux 服务器在项目根目录执行以下命令，配置生成所需 Python 仅在容器内运行。使用当前用户写入文件，避免生成宿主机 root 所有的配置：

```bash
rtk docker run --rm --user "$(id -u):$(id -g)" --mount "type=bind,source=$PWD,target=/workspace" python:3.11-slim-bookworm python /workspace/docker/init_env.py
rtk docker compose --env-file .env -f compose.docker.yml up -d --build --wait
```

初始化以独占创建方式写入 `.env`，Linux 文件权限为 `600`；重复执行保留已有配置和密钥，不自动迁移旧配置。新配置与 Compose 默认均选择完整分析镜像。现有精简环境可显式设置 `ANALYSIS_FLAVOR=core` 和 `APP_DOCKERFILE=docker/app/Dockerfile`。以上命令需要 Docker 和本项目约定的 `rtk` 命令，不需要宿主机 Python、R 或 Node。

访问 http://127.0.0.1:8080 。当前 `FLASK_CONFIG=internal` 为内部共享工作台，直接进入，无需登录或注册；既有账号及项目归属保留。需认证的部署使用 `container` 或 `production` 模式。`.env` 不纳入 Git。

`compose.docker.yml` 使用独立项目名 `immune-platform`，包含 web、api、worker、MySQL、MongoDB、Redis 六个服务。仅网页端口绑定本机，数据库和任务队列在容器网络内访问。`docker-compose.yml` 是旧环境配置。

## 分析镜像

当前 `.env` 选择完整分析镜像：

```dotenv
ANALYSIS_FLAVOR=full
APP_DOCKERFILE=docker/app/Dockerfile.analysis
```

完整镜像含 Python 3.12、R 4.4 / Bioconductor 3.20、SoNNia 0.3.1、TensorFlow 2.16.2、clusterProfiler、org.Hs.eg.db、enrichplot、DOSE，以及 UMAP、PDF/PPT、中文字体、Java 和 LibreOffice。基础镜像省去 SoNNia 与 R 分析依赖。

```bash
rtk docker compose --env-file .env -f compose.docker.yml exec api python docker/app/check_runtime.py --full
```

本次完整镜像约 8.88 GB，科学计算与文档处理依赖占主要部分；源码构建上下文约 5.84 MB。真实数据、宿主机依赖和凭据均被 `.dockerignore` 排除。镜像大小与数据卷用量分别计算，不应通过删除参考数据库来缩减镜像。

## 任务运行

Docker 默认 `JOB_QUEUE=redis`，由独立 RQ worker 执行统一分析、Script Hub、Treemap 和 Chord。API 重启不清空排队任务。数据库原子状态转换防止同一任务重复执行；已取消的排队任务跳过计算。失败、取消或中断的任务可在界面重试，创建新任务并保留原记录。旧任务没有完整参数时需重新从向导提交。

组合分析的图表子任务在当前 worker 内执行，避免单 worker 等待自身队列。计算期间的取消在模块检查点生效；强制终止容器不等于算法断点续算。工作进程异常通过 RQ 失败处理记录状态，默认单任务超时 7200 秒。重试从头计算。

任务 payload 保存实际 Python 和依赖版本，分析记录 JSON 可一并导出。Pgen 固定 seed=42、单个 OLGA 计算进程；Linux 直接使用官方模型名，避免触发旧 Windows 路径兼容分支。

## 容器内验证

后端测试使用独立临时文件系统，避免写入已迁移的数据卷：

```bash
rtk docker compose --env-file .env -f compose.docker.yml run --rm frontend-test
rtk docker run --rm --network immune-platform_default --tmpfs /app/flask_app/data:uid=10001,gid=10001 --tmpfs /app/tmp:uid=10001,gid=10001 -e FLASK_CONFIG=testing -e JOB_QUEUE=threadpool -e REDIS_URL=redis://redis:6379/15 immune-platform-api:full python -B -m pytest flask_app/tests/ analysis_workers/tests/ -q --disable-warnings
```

修改测试或源码后先重建对应镜像。前端执行 TypeScript 检查、Vite 生产构建及 Vitest。

## 数据迁移与备份

2026-09-12 已将旧库和已登记资产迁入独立 Docker 卷：

| 内容 | 验证结果 |
|---|---|
| MySQL | 1 个账号、2 个项目、27 项资产、52 条历史任务、1 条用户配置 |
| MongoDB | 25 条结果、1 条分析缓存；rawdata 为空 |
| 文件 | 58,985 个文件，共 21,098,194,349 字节，含结果、关联输入、参考库和用户数据 |
| 路径 | MySQL 转换 747 个绝对路径，另修复管理员 Windows 相对主目录；MongoDB 转换 1517 处路径 |
| 下载 | 27 项已登记资产路径均存在；6 项文件资产经 Nginx/API 下载验证，其余为目录资产 |

原始宿主机数据与原数据库卷保留。旧 MySQL 和 MongoDB 在停止状态下复制，恢复到独立工作卷后读取核对。备份卷为 `immune-platform_legacy_backup_20260912`，包含物理备份、Mongo 文档备份、迁移清单和计数。恢复验证容器名称以 `immune-legacy-` 开头，验收后停止。

迁移工具位于 `docker/operations/`。MySQL 工具只向空目标表导入，Mongo 工具只向空目标集合导入；不要对当前已迁移数据库再次执行导入。数据库中的旧运行中任务转为中断状态，不伪造完成结果。未登记的历史输出仍保留在原外置数据目录。

`app_data` 保存业务文件；`app_tmp` 保存临时会话；MySQL、MongoDB、Redis 分别持久化。停止服务使用 `down`，不要附加 `--volumes`。数据库备份与业务文件必须共同保留。此处备份是迁移时间点快照，后续新增数据需重新备份。

## 公网配置

公网 HTTPS 入口前，将 `FLASK_CONFIG=production`，使用独立强 SECRET_KEY，并配置域名和 HTTPS 反向代理；production 使用 Secure Cookie。可保持 HTTP_BIND=127.0.0.1，由同机代理转发至 HTTP_PORT=8080。需要关闭自助注册时设置 `AUTH_REGISTER_ENABLED=false`。

当前运行地址仅本机可访问。未提供公网域名、证书或服务器，因此未执行公网发布。CSR、07 浸润、08 聚类仍须补齐对应算法脚本与输入约定，详见[优化验收记录](optimization-readiness.md)。

## 实际分析验收

- 完整 API 镜像、前端生产镜像构建成功，六个服务健康。
- 前端 20 个测试文件、67 项通过；后端及 worker 全量 196 项通过，无跳过。PDF 模块也单独执行回归，避免依赖测试导入顺序。
- API 重启后，排队统一分析正常完成；已取消任务未开始计算；重试新任务完成。单 worker 的组合 Chord 实际计算完成。
- 单独重建 API 容器后，Nginx 自动重新解析 Docker DNS，网页容器未重启，宿主机 `/api/health` 返回 healthy。
- 8 路并发、40 次已登录项目读取全部成功，中位耗时约 257 ms，P95 约 392 ms；这是本机小型读接口基准，不代表大规模分析容量。
- 迁移传输临时归档已清理 41,389,384,704 字节；原文件、迁入卷和数据库备份仍保留。
- Script Hub Pgen 经独立 worker 运行，下载结果中的测试序列概率为 `1.9603935768649733e-7`，与官方默认 humanTRB 模型直接计算一致。
- clusterProfiler 实际 GO 富集返回 1619 条、KEGG 返回 167 条结果；这是小型测试基因列表的运行验收，非研究结论。KEGG 计算使用在线注释服务。

参考：[Docker Compose 构建配置](https://docs.docker.com/reference/compose-file/build/)、[Bioconductor 官方容器](https://bioconductor.org/help/docker/)。


## 2026-09-12 中断恢复补充

- RQ 工作子进程异常退出时，失败回调会同步结束所属组合任务的未完成子任务和后代任务；已完成结果、无关任务及保存的重试参数保持不变。
- 独立测试容器使用合成 SQLite 记录和唯一 RQ 队列，向工作子进程发送 SIGKILL，验证父任务与子任务均变为 interrupted。此验收覆盖工作子进程退出，不等同于整台主机断电后的即时恢复。
- 最终修复镜像内 11 项任务队列回归测试通过。本次复用原完整分析镜像的依赖层，构建源码修复层并更新 API/worker；依赖声明未变，完整 Dockerfile 包含相同源码修复。
- Docker 恢复后曾启用 containerd 存储，原经典存储镜像和容器暂不可见；已确认原镜像仍在磁盘并恢复经典存储。设置备份保存在 Docker 配置目录的 settings-store.before-classic-restore-20260912.json。

两种镜像存储相互独立，切换后旧镜像可能隐藏，参见 [Docker 官方说明](https://docs.docker.com/desktop/features/containerd/)。先核对存储模式和数据卷，再决定是否重建环境。

## 2026-09-13 内部工作台模式

`internal` 关闭登录注册，忽略浏览器原登录会话，允许内部共享访问已有项目；不改变数据库中的用户归属。文件访问限于 `ALLOWED_BASE_PATHS`，默认容器业务数据和临时目录。网页端口继续绑定 `127.0.0.1`，不自动开放公网。`production` 仍要求登录和强密钥。此阶段未完成最终 Linux 服务器部署改造，执行记录见 `docs/superpowers/project-input-workflow-progress.md`。


### 工作进程健康检查与日志轮转

当前源码中，工作进程按容器主机名注册为 `analysis-<hostname>`。Compose 调用
`python -m analysis_workers.healthcheck` 检查该进程的队列、状态、心跳和进程存活；
不能用其他容器中的正常工作进程代替本容器的健康状态。空闲进程允许 RQ 默认
心跳周期及 60 秒宽限，容器失败判定另受 Compose 检查间隔与重试次数影响。
更新此配置必须同时更新包含新 worker_main 和 healthcheck 的应用镜像。

常驻服务使用 Docker `local` 日志驱动，单份 `20m`、最多 `5` 份；
此限制只控制容器标准输出日志，不清理分析结果或应用写入数据卷的文件。
配置在容器重新创建时生效。本轮只完成源码和隔离测试，尚未重新创建现有服务。


### 普通用户运行与已有数据卷升级

应用镜像和工作进程使用固定 UID/GID `10001:10001`，家目录为 `/home/immune`。
新建命名卷继承镜像中数据目录的所有权；Linux 显式绑定目录需要让此用户能够读写。
不要把整个源码目录或参考资料改为所有用户可写。

从旧 root 镜像升级时，先完成数据库和文件备份、等待分析任务结束，再执行：

```bash
rtk docker compose --env-file .env -f compose.docker.yml build api
rtk docker compose --env-file .env -f compose.docker.yml stop api worker
rtk docker compose --env-file .env -f compose.docker.yml --profile operations run --rm --no-deps volume-init
rtk docker compose --env-file .env -f compose.docker.yml up -d --no-build --wait api worker web
```

`volume-init` 只处理 `/app/flask_app/data` 与 `/app/tmp` 两个应用卷，调整文件所有权并补齐
所有者读写权限；跳过符号链接及其外部目标，不修改数据库服务的数据卷。
这一步需要包含 `init_volume_permissions.py` 的新镜像。大卷迁移可能耗时较长，完成后再启动应用。
若使用宿主机绑定目录，文件所有权会反映为 UID/GID 10001；备份恢复时也需保持或重新初始化该权限。

运行验证：

```bash
rtk docker compose --env-file .env -f compose.docker.yml exec api python -c "import os; assert os.geteuid() == 10001; print('应用用户验证通过')"
rtk docker compose --env-file .env -f compose.docker.yml exec worker python -m analysis_workers.healthcheck
```

本节为新版本部署流程；不能仅凭修改 Dockerfile 或已有镜像的用户覆盖测试宣称新镜像已经构建发布。


### 分析资源与并发

Compose 对应用和工作进程设置资源上限，均可在 `.env` 调整：

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| API_CPUS / API_MEMORY_LIMIT | 2 / 2g | 单个接口容器的 CPU 配额与内存上限 |
| WORKER_CPUS / WORKER_MEMORY_LIMIT | 4 / 8g | 每个分析工作进程容器的资源上限 |
| ANALYSIS_NUM_THREADS | 1 | OpenMP、OpenBLAS、MKL、NumExpr 的默认数值计算线程数 |
| ANALYSIS_TIMEOUT_SECONDS | 7200 | 未单独配置模块时使用的队列任务超时秒数 |
| ANALYSIS_TIMEOUTS_JSON | 空 | 可选 JSON 对象，按 `AnalysisJob.module` 精确覆盖超时，单位为秒 |
| WORKER_STOP_GRACE_PERIOD | 2m | 停止容器时等待工作进程退出的最长时间 |

例如在 `.env` 中设置 `ANALYSIS_TIMEOUTS_JSON='{"analysis-batch":14400,"ml-analysis":14400,"topclone":3600}'`，可分别给组合任务、机器学习和优势克隆分析设置超时；未列出的模块继续使用 `ANALYSIS_TIMEOUT_SECONDS`。JSON 必须为正整数秒数，配置格式错误会在任务入队时明确报错。

这些是可调的初始上限，不是已测得的最低服务器配置。数据库、文件缓存和宿主机也需内存空间。
一个 RQ 工作进程同时执行一个顶层任务；增加工作进程容器数量时，应按数量计算总资源预算。
默认数值线程数限制内部并行，避免多个任务各自开启大量线程；不改变统计检验定义。
显式设置线程数的模块仍需结合实际运行参数检查。

超过内存上限可能被系统终止；任务超时或停止宽限结束不提供算法断点续算。长任务升级前应先等待任务结束。
现有配置文件不会被初始化器覆盖，可手工加入以上配置后重新创建对应容器使其生效。
本节新增上限尚未应用到现有运行服务，需完成新镜像验收后统一发布。


### Linux 全量冷备份与恢复

工具 `docker/operations/cold_backup.py` 备份七个数据卷和 `.env`，保留文件所有权和文件修改时间的纳秒精度；包含应用数据、独立上传目录、独立结果目录、临时卷及三种数据库卷。
备份包含数据库凭据，应存放在受限目录。发布归档前完整读取压缩流并执行与恢复一致的清单、路径和链接检查；不合格归档不会发布。工具校验不代替数据库启动恢复验收。
执行前停止接收新任务，等待队列和运行任务清空，再停止全部服务；工具自身不会停止服务。
以下命令在仓库根目录执行，适用于默认项目名 `immune-platform`、默认完整镜像和 Linux Bash。
自定义项目名时必须替换卷名，并先用 `docker volume inspect` 确认源卷存在，避免备份新建空卷。

```bash
rtk docker volume inspect immune-platform_app_data immune-platform_app_uploads immune-platform_app_results immune-platform_app_tmp immune-platform_mysql_data immune-platform_mongo_data immune-platform_redis_data
rtk proxy mkdir -p -m 700 backups
rtk docker compose --env-file .env -f compose.docker.yml stop
rtk docker run --rm --network none --user 0:0 \
  --mount type=bind,src="$PWD/docker/operations",dst=/operations,readonly \
  --mount type=bind,src="$PWD/.env",dst=/config/.env,readonly \
  --mount type=bind,src="$PWD/backups",dst=/backups \
  --mount type=volume,src=immune-platform_app_data,dst=/volumes/app_data,readonly \
  --mount type=volume,src=immune-platform_app_uploads,dst=/volumes/app_uploads,readonly \
  --mount type=volume,src=immune-platform_app_results,dst=/volumes/app_results,readonly \
  --mount type=volume,src=immune-platform_app_tmp,dst=/volumes/app_tmp,readonly \
  --mount type=volume,src=immune-platform_mysql_data,dst=/volumes/mysql_data,readonly \
  --mount type=volume,src=immune-platform_mongo_data,dst=/volumes/mongo_data,readonly \
  --mount type=volume,src=immune-platform_redis_data,dst=/volumes/redis_data,readonly \
  immune-platform-api:latest python /operations/cold_backup.py backup --archive /backups/platform.tar.gz
rtk docker compose --env-file .env -f compose.docker.yml up -d --no-build --wait
```

以上挂载命令适用于 `.env` 未设置 `APP_DATA_DIR`、`APP_UPLOAD_DIR`、`APP_RESULTS_DIR` 的默认命名卷。若使用绝对宿主机目录，备份时将各实际目录以只读 bind mount 挂载到对应的 `/volumes/app_data`、`/volumes/app_uploads`、`/volumes/app_results`；恢复时挂载到新建的目标目录。不要只备份 `app_data`，独立上传和结果目录也包含用户文件及分析产物。

每次使用新的备份文件名；工具拒绝覆盖既有归档。执行备份失败也应检查原因后恢复原服务。
同时保存对应源代码版本、镜像标识和数据库镜像，恢复先使用同版本，不同时进行数据库升级。

恢复演练使用全新的卷及空配置目录，不挂载现有业务卷：

```bash
rtk proxy mkdir -p -m 700 restore-config
rtk docker run --rm --network none --user 0:0 \
  --mount type=bind,src="$PWD/docker/operations",dst=/operations,readonly \
  --mount type=bind,src="$PWD/restore-config",dst=/config \
  --mount type=bind,src="$PWD/backups",dst=/backups,readonly \
  --mount type=volume,src=immune-restore_app_data,dst=/volumes/app_data \
  --mount type=volume,src=immune-restore_app_uploads,dst=/volumes/app_uploads \
  --mount type=volume,src=immune-restore_app_results,dst=/volumes/app_results \
  --mount type=volume,src=immune-restore_app_tmp,dst=/volumes/app_tmp \
  --mount type=volume,src=immune-restore_mysql_data,dst=/volumes/mysql_data \
  --mount type=volume,src=immune-restore_mongo_data,dst=/volumes/mongo_data \
  --mount type=volume,src=immune-restore_redis_data,dst=/volumes/redis_data \
  immune-platform-api:latest python /operations/cold_backup.py restore --archive /backups/platform.tar.gz
```

恢复的 `.env` 会保留备份主机上的配置。若恢复目标使用新宿主机目录，先编辑 `restore-config/.env` 中三个 `APP_*_DIR` 指向对应恢复目录，再启动 Compose。旧格式五卷备份缺少独立上传和结果卷，工具会拒绝将其当作完整平台备份恢复。

工具拒绝非空目标卷、非空配置目录、越界归档路径和越界链接。归档解包成功后，
先将恢复配置中的 HTTP_PORT 改为未占用端口，再用 `-p immune-restore`、
`--env-file restore-config/.env` 启动同一 Compose，避免与原服务冲突。
验收必须包括数据库健康、项目与资产完整性、历史文件下载及一次小型分析。
已使用隔离 Linux 容器完成 MySQL 8.0、MongoDB 7.0、Redis 7 的合成数据冷备份与恢复：
停库后备份七卷，恢复到空卷，再启动三个数据库并读回原记录，同时检查应用文件和配置。
MySQL 的 mysql.sock 运行时符号链接不进入备份，由数据库启动时重建。
2026-09-21 补充了应用级恢复演练：正常停止 MySQL 后备份并恢复数据，使用非 root 应用用户读回项目、任务并下载登记的结果文件。此次补充演练未覆盖完整分析重跑及 MongoDB、Redis 的应用级恢复。


### 上传请求大小

`.env` 的 `UPLOAD_MAX_MB` 为正整数，单位为兆字节（1024² 字节），默认 100。
Nginx 与 Flask 共用该配置；修改后重新创建 web、api 和 worker 容器。
例如设置 `UPLOAD_MAX_MB=1024` 允许最大 1 GiB 的整个请求，包含所有文件和表单开销，
不是每个文件分别享有此额度。前置代理如有自己的限制，也需要同步设置。
超限返回中文 JSON 错误。提高上限前应核对磁盘空间及分析内存预算；此设置不提供断点续传。


### 工作进程异常结束后的任务状态

`ANALYSIS_QUEUE_MAINTENANCE_SECONDS` 控制工作进程的队列维护间隔，默认 60 秒。
进程整体被强制结束时，失败回调可能来不及执行。存活或重新启动的工作进程通过 RQ 维护
识别心跳已过期的任务；平台单任务查询随后依据队列终态补记“分析中断”，并结束未完成子任务。
心跳过期与维护调度均需要时间，不能把该间隔当作恢复时间承诺；没有运行的工作进程时维护不会执行。
Redis 暂时断连或队列记录缺失不直接判定任务失败。此机制不提供算法断点续算，重试会创建新任务。


### 当前本机部署记录（2026-09-14）

当前使用 `ANALYSIS_FLAVOR=workflow-candidate` 与 `WEB_IMAGE_TAG=workflow-candidate`。
前端镜像由 WEB_IMAGE_TAG 选择，默认 latest；API 和 worker 继续共用 ANALYSIS_FLAVOR。
六个服务已通过健康检查，应用卷已迁移为 UID/GID 10001。
更新前冷备份、镜像摘要和运行验收范围见 [工作流执行记录](superpowers/project-input-workflow-progress.md)。
该记录仅证明当前机器上的 Linux 容器运行，不代替目标服务器验收。


## Linux 一键更新部署

首次部署先克隆仓库并进入目录，之后每次更新只需执行脚本。默认更新当前分支；也可以传入分支名核对，脚本不会自动切换分支。

```bash
git clone git@github.com:zqywuxie/immune-repertoire-web.git
cd immune-repertoire-web
bash init-env.sh
nano .env
bash deploy.sh
```

`init-env.sh` 先检查工作区，再执行 `git pull --ff-only origin 当前分支`，随后重新执行更新后的初始化脚本。即使 `.env` 已存在也会先更新代码，然后完整保留配置和密钥。编辑并确认参数后才运行 `deploy.sh`，部署阶段不再拉取代码。`deploy.sh` 只读取 `.env`，缺失时退出；随后校验 Compose、构建 api/web，最后启动服务并等待健康检查。任何一步失败即停止，不执行清库、删除数据卷或强制覆盖 Git 修改。

默认入口为服务器本机 `127.0.0.1:8080`。内部免登录模式请通过受控内网、隧道或代理访问；绑定地址和端口在 `.env` 中配置。服务器需要 Git、Docker Engine 和支持 `up --wait` 的 Compose 插件，以及仓库读取权限。首次构建需访问 Python/R 软件仓库；主机不安装应用依赖。更新会重建容器，请避开分析任务执行时段；已有 root 数据卷恢复后，按本文权限迁移步骤处理。业务数据需单独恢复，Git 不包含数据库、上传、结果和参考库。


## 端口与配置（Linux）

部署配置统一使用 `.env`，可提交的无密钥参考为 `.env.example`。已有 `.env` 不被脚本覆盖；没有 `.env` 但存在 `.env.docker` 时，显式运行 `init-env.sh` 才会复制旧配置并保留原件；部署脚本不执行迁移。此前使用宿主机配置的用户应先备份原 `.env`，再从 `.env.docker` 迁移，避免混用旧数据库端口。

首次运行前可先生成配置并检查准备使用的端口：

```bash
sudo ss -lntp 'sport = :18080'
bash init-env.sh
nano .env
```

将 `HTTP_PORT` 改为确认空闲的端口，例如 `18080`，再执行 `bash deploy.sh`。默认 `HTTP_BIND=127.0.0.1` 供本机代理访问；可信内网直连才改为 `0.0.0.0` 并配置防火墙。该检查是当时的监听快照，实际占用由 Docker 启动时报错确认。

冷备份读取容器 `/config/.env`，新归档保存为 `config/.env`，恢复为配置目录下的 `.env`。仅在读取旧格式三版归档时兼容 `config/.env.docker` 名称，恢复仍输出 `.env`；不要将当前配置挂到 `/config/.env.docker`。


## 应用文件所有者与数据根目录

`APP_UID` / `APP_GID` 必须填写服务器 `id -u zhengqinyun` / `id -g zhengqinyun` 的实际结果；Linux 文件所有权由数字编号决定。初始化器在使用 `--user` 的容器中记录对应编号；已有配置不会重写。`APP_STORAGE_USER` 决定内部共享模式的新文件目录名，默认 `zhengqinyun`；认证模式按项目所属应用账号用户名分目录。这个名称不能替代 UID/GID，也不改变项目的数据库归属。

`APP_DATA_DIR` 可设为宿主机绝对目录，省略时保留原有 app_data 卷。更改该变量不会自动搬迁旧卷，请先完成数据备份和恢复。已有文件权限迁移前停止 API 和工作进程，再运行权限初始化并启动：

```bash
docker compose --env-file .env -f compose.docker.yml stop api worker
docker compose --env-file .env -f compose.docker.yml --profile operations run --rm --no-deps volume-init
docker compose --env-file .env -f compose.docker.yml up -d --wait
```

权限初始化覆盖应用数据、临时目录，以及 `PROJECT_DATA_ROOT`、`RESULTS_DIR`、`USER_DATA_ROOT`、`UPLOAD_FOLDER` 中显式配置的容器绝对路径；跳过符号链接，不修改数据库服务数据卷。API、worker 和初始化容器必须使用同一挂载与 UID/GID。应先构建新应用镜像，再初始化卷，再启动应用；镜像预填充的绘图缓存也需要按这个顺序设置所有权。绘图缓存位于 `/app/tmp/matplotlib`。


## Bioconductor 镜像代理返回 403

当报错地址为 `docker.m.daocloud.io/.../manifests/...` 时，失败来自服务器配置的 Docker Hub 镜像代理。`web build CANCELED` 是并行构建随 API 构建失败而取消，不代表前端编译错误。

分析基础镜像 Dockerfile.runtime 默认使用 `ghcr.io/bioconductor/bioconductor_docker:RELEASE_3_20`。已验证该标签的 amd64/arm64 清单可访问，保持原来的 Bioconductor 版本。无需更改全局 Docker 配置或重启其他项目。

```bash
bash init-env.sh
nano .env
bash deploy.sh
```

现在请按本文“分析基础镜像”步骤准备已安装依赖的环境；旧 `.env` 的 `BIOCONDUCTOR_IMAGE` 不再控制应用构建。需要指定原始基础来源时，通过构建 Dockerfile.runtime 的同名 build-arg 设置，镜像须保持兼容的 Bioconductor 3.20 / R 4.4 环境。此修改仅绕过该 Bioconductor 镜像的 Docker Hub 代理，其他镜像及软件仓库的网络访问仍以服务器实际连通性为准。


## 多用户版本升级（2026-09-19）

新部署默认启用登录注册，注册账号为普通用户。既有 `.env` 不会被生成器或部署脚本覆盖；升级前自行修改：

```dotenv
FLASK_CONFIG=container
AUTH_REGISTER_ENABLED=true
APP_UPLOAD_DIR=/colddata/SCigblast/platform/data
APP_RESULTS_DIR=/colddata/SCigblast/platform/results
```

如果通过 HTTPS 访问，使用 `FLASK_CONFIG=production`，确保浏览器发送安全会话 Cookie。保留既有密钥、数据库口令及 APP_DATA_DIR，不能重新生成替换已有配置。

Linux 上先运行 `id -u zhengqinyun` 和 `id -g zhengqinyun`，把真实编号填入 APP_UID、APP_GID。由该服务器账号创建上传与结果目录；应用登录账号只决定目录内部的逻辑归属，不改变 Linux 文件用户。

新上传：`APP_UPLOAD_DIR/用户名/年月日_时分秒__批次标识/数据类型/文件`；新核心分析结果：`APP_RESULTS_DIR/用户名/年月日_时分秒/分析类型/分析类型_UUID/`。项目归属由资产和任务记录保存，不将项目编号插入新的时间布局。上传、结果和原应用数据使用独立挂载；原数据路径继续保留，历史资产按数据库记录读取，不自动搬动或改归属。按类型删除清理已登记上传批次内的文件并回收空目录。删除整个项目依据该项目的资产和任务记录清理已登记上传、新结果的独立运行目录及旧项目目录，同时清理 Mongo 原始资产/结果/缓存记录和终态任务记录；存在未结束任务时拒绝删除。共享的用户名/时间父目录不会整段删除，未登记上传文件、外部登记输入以及其他项目或任务仍引用的结果保留。Script Hub 在分配运行目录时记录任务输出，失败后没有结果资产的残留也可按任务记录清理。

首次切换到新存储后，如目录未归属设定 UID/GID，可在构建新应用镜像后显式运行：

```bash
docker compose --env-file .env -f compose.docker.yml build api
docker compose --env-file .env -f compose.docker.yml --profile operations run --rm volume-init
bash deploy.sh
```

权限初始化跳过符号链接，不处理 MySQL、MongoDB 的独立数据库卷。依赖不变时继续使用既有版本化分析运行镜像。

历史 `user_id` 为空的项目不会自动分配给首个注册账号。启用认证前先通过数据库备份及只读归属清单确定映射；未确定归属的数据保持不可见。


只读核对历史归属时，在数据库客户端执行以下查询，不要直接批量改写 user_id：

```sql
SELECT p.id, p.name, p.user_id, u.username
FROM projects p LEFT JOIN users u ON u.id = p.user_id;
SELECT id, project_id, user_id, module, status
FROM analysis_jobs WHERE user_id IS NULL;
```

如果历史项目没有所属用户，应在明确项目与账号映射并完成备份后再迁移归属。当前升级不会猜测归属或删除历史目录。


## 部署时自动创建管理员

在服务器项目根目录 `.env` 配置：

```dotenv
BOOTSTRAP_ADMIN_ENABLED=true
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_EMAIL=admin@example.com
BOOTSTRAP_ADMIN_PASSWORD=请替换为至少6位的独立密码
```

`init-env.sh` 生成的新配置会包含随机管理员密码，不在终端打印。已有 `.env` 不被初始化脚本覆盖，升级时需自行补充以上四项。API 启动完成数据库初始化后创建管理员；重复部署不会重置密码、重新启用停用账号或把已有普通用户提升为管理员。用户名或邮箱冲突会使启动失败并显示不含密码的说明。首次成功后可设 `BOOTSTRAP_ADMIN_ENABLED=false`，管理员仍保留在数据库。

本地现有 `.env` 已补齐缺失的四项，未改变其他密钥。该文件不提交 Git，因此服务器仍需自行配置。该账号与 APP_STORAGE_USER（内部共享存储目录名）独立；普通业务界面仍按自己的项目范围访问。


## 并行分析与排队诊断

`.env` 中设置 `WORKER_CONCURRENCY=2`，默认启动两个独立 worker 容器，每个同时执行一个队列任务。修改后执行 `docker compose --env-file .env -f compose.docker.yml up -d --wait worker`；正常部署脚本也会应用该配置。不要另加 `--scale worker=...` 覆盖配置，值应为正整数。WORKER_CPUS / WORKER_MEMORY_LIMIT 是每个 worker 容器的上限。

worker 每次启动使用独立注册名称，避免异常退出留下的旧 Redis 注册阻止新进程启动；健康检查只检查本容器当前启动的 worker。任务页面区分等待名额、没有可用工作进程、队列暂停和 Redis 连接异常，不会将未开始的任务伪装为运行中。

若仍排队，执行以下只读检查：

```bash
docker compose --env-file .env -f compose.docker.yml ps worker
docker compose --env-file .env -f compose.docker.yml logs --tail=100 worker
```

已取消的任务不会自动重新执行，需要在任务页面重试。普通账号注册与部署管理员密码统一至少 6 位；已有密码不受影响。


首次从旧脚本切换：旧版 init-env.sh 尚不包含拉取逻辑，需要先执行一次 `git pull --ff-only origin main` 获取新版。此后固定使用：

```bash
bash init-env.sh
nano .env
bash deploy.sh
```

已有 `.env` 不会自动追加新变量；请对照更新后的 `.env.example` 补充所需参数。`deploy.sh [分支]` 保留兼容，分支参数只作校验，不触发拉取。


部署脚本现于构建完成后自动运行 volume-init，按 APP_UID/APP_GID 初始化应用数据、上传和结果挂载的所有权，再启动服务。该操作不修改数据库服务的数据卷，不跟随符号链接；权限修复失败时停止部署。新增宿主机挂载目录由 Docker 创建为 root 所有时，也会在此步骤修复。


### 更新前的活动任务检查

`init-env.sh` 拉取远端代码并保留已有 `.env`；编辑配置后再运行 `deploy.sh`。部署脚本在构建完成、替换服务前查询正在运行的 API 数据库；有等待或运行任务时退出。请在任务中心等待完成或取消，并在更新窗口暂停提交新任务。检查失败也会停止更新，避免把数据库连接异常当作空队列。此检查不是全站提交锁，更新窗口仍需协调使用者。

权限初始化仍检查所有应用目录，但仅对所有权或权限不符合配置的文件执行修改，已有正确权限的文件保持不变。数据库卷不在该初始化范围。

## 自动维护与更新（2026-09-21）

支持维护模式的运行版本会在检查活动任务前暂停新的 POST、PUT、PATCH、DELETE 请求，并等待已受理的写请求结束。GET 读取仍可用；后台任务继续执行。有活动任务时部署退出并解除本次维护，任务完成后重新运行部署即可。部署成功或失败都尝试解除本次维护；解除失败会打印包含本次令牌的恢复命令。

首次从不含维护模块的旧版本升级时仍需人工暂停提交；脚本会明确提示。后续更新自动保护该窗口。维护文件位于应用数据卷，不要在维护期间重启清理卷或人工删除锁文件。意外终止部署进程后，需按日志中的本次令牌解除维护。

备份工具现在保存 `.env`，兼容读取旧备份中的 `.env.docker` 并恢复为 `.env`。冷备份仍要求停止所有写入服务；维护模式不能替代数据库正常停机。


## 2026-10-03 存储与镜像验收

宿主机上传/结果目录变量是 `APP_UPLOAD_DIR` / `APP_RESULTS_DIR`；应用读取的 `PROJECT_DATA_ROOT` / `RESULTS_DIR` 必须是对应挂载的容器绝对路径。权限初始化、API 和 worker 使用同一环境变量、卷映射和数字 UID/GID，不能把 Windows 路径作为容器配置。

已在 Docker Linux 容器中使用独立命名卷、`/storage/上传 数据` 与 `/storage/分析 结果` 挂载，以及 UID 12345/GID 23456 完成四类上传、原生 RQ 差异表达、登记结果复用、下载和刷新恢复。应用镜像实际构建通过，复用已有 R/Bioconductor 依赖层。未挂载宿主机源码的重建容器能读取旧资产/结果、运行新任务、删除指定项目并保留同名用户下其他项目。测试卷只包含合成数据，不代表目标服务器的 UID/GID 或发行版已验证。

当前工作区中的 `compose.docker.yml`、`deploy.sh`、`init-env.sh`、`.env.example` 和 `.dockerignore` 已删除，本轮保留这些既有删除，不恢复文件。本文涉及这些入口的命令为历史部署流程说明，当前工作区不能直接执行；最终服务器部署仍需相应入口及挂载配置的完整验收。本轮构建使用约 7.15 MB 的临时过滤上下文，排除了数据和目录链接，没有将现有业务数据打入镜像。


## 2026-10-03 全平台冷恢复与任务续接验收

使用 MySQL 8.0、MongoDB 7.0、Redis 7 的独立 Linux 容器和七个合成数据卷完成了应用级恢复；API/worker 使用 UID 24501、GID 24502，上传和结果分别挂载到 `/storage/上传 数据`、`/storage/分析 结果`。停掉所有写入服务后备份，恢复到全新空卷；新容器没有挂载宿主应用源码，也未执行恢复后权限修复。

验收覆盖已登记的四类输入（11 个原始资产）、SQL 项目/任务/资产记录、Mongo 结果与派生产物缓存，以及 Redis 持久化等待任务。恢复前后历史 ZIP 逐字节一致（12343 字节），所有原始资产能通过 API 下载，11 个文件的数字所有权和纳秒修改时间保持一致。未启动 worker 时可从 Mongo 复用历史 PEP 结果；启动 worker 后原等待指标任务完成，并从恢复的 PEP 矩阵生成 8 个样本的原生 UMAP 坐标及可下载结果。最终运行/排队均为零。

首次演练发现两类阻塞：tarfile 浮点时间损失纳秒精度，以及 Linux 恢复后不可保留的 ctime 导致上传文件误报外部修改。备份/恢复现保留精确修改时间；上传文件状态变化时，只核对上传时已有的内容摘要，内容一致才更新快照并重新校验。后续正常读取仍复用校验缓存；相同大小和修改时间的内容替换仍拒绝。旧归档不能补回已丢失的纳秒精度，历史上传可经摘要核对继续使用，依赖精确时间的旧派生缓存可能需要重新生成。

本次为了验证队列恢复，特意在停止 worker 后保留一个未领取任务，确认无运行任务，再正常停库备份；这不改变日常备份前清空队列的建议，也不提供运行中算法断点续算。当前证据是本机 Docker 的 Linux 容器，不代表目标服务器的资源、整机重启或部署入口已验收。详细任务、镜像与回归记录见 [工作流执行记录](superpowers/project-input-workflow-progress.md)。

### 结果数据表排序的临时空间（2026-10-03）

CSV/TSV 的服务端排序逐行写入单次临时 SQLite 数据库，再返回请求的数据页。数值排序保留大整数/科学计数法原文；默认无排序时继续流式读取。临时库在成功或解析失败后自动清理，不登记为项目资产或永久缓存。

临时目录遵循容器 Python 的 `TMPDIR`（未设置时通常为 `/tmp`）。完整表排序需要额外磁盘空间；如将 `/tmp` 配成较小 tmpfs，应将 `TMPDIR` 指向容器内有足够空间且当前应用 UID/GID 可写的磁盘目录。额外空间包含匹配行数据库和 SQLite 排序暂存，不能只按网页每页行数估算。空间不可用时接口返回中文 503 提示，用户仍可恢复原始顺序或下载文件。服务器磁盘与并发容量需在目标部署环境实测。

### 网页报告与 PDF 文件预览（2026-10-03）

Script Hub 的 PDF 结果默认使用 Content-Disposition: inline，便于浏览器内嵌查看；需要强制附件时在结果文件链接添加 download=1。ZIP/TXT/LOG 继续作为附件。文件不存在返回 404，非法结果路径仍拒绝。反向代理应保留上游类型、文件长度、Range 与 Content-Disposition，不将 PDF 全部改成附件。

网页/PDF 预览先以 HEAD 检查本地文件；不支持 HEAD 的历史接口可回退 GET 元数据后取消正文。外部报告沿用浏览器原生查看，不额外要求跨域请求。浏览器不支持 PDF 或文件以附件返回时显示新标签页/下载入口；原生查看器渲染由浏览器负责。实际文件接口、原生 PDF 渲染与手机交互已在本机隔离 Linux 容器验证，目标服务器代理仍需按部署环境验收。


### 在非内网环境通过 SSH 访问

SSH 能连接服务器时，可以将服务器的网页端口转发到本机，不需要浏览器直连服务器内网地址。例如服务器平台端口为 `10322`，本机空闲端口为 `10323`：

```bash
ssh -N -L 127.0.0.1:10323:127.0.0.1:10322 remote_nanhua
```

保持 SSH 连接运行，在本机浏览器打开 `http://127.0.0.1:10323`。`remote_nanhua` 使用本机已有的 SSH 配置；右侧 `10322` 要与服务器实际网页端口一致，左侧 `10323` 只用于本机访问。上传镜像不会自动建立此隧道，也不会将网页服务公开到外网。
