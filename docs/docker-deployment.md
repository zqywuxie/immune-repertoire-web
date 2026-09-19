# Docker 运行与部署

在项目根目录操作。依赖安装、测试、构建和分析均在 Linux 容器内执行。


## 分析基础镜像：构建一次，日常复用

完整环境改为两层：`Dockerfile.runtime` 只安装 Python/R/系统依赖；`Dockerfile.analysis` 只复制业务代码并验证环境。日常先执行 `bash init-env.sh` 拉取代码并准备配置，编辑 `.env` 后再运行 `bash deploy.sh` 构建应用和前端，不重新安装 R/Python 依赖。首次部署前必须准备下面的基础镜像；仅导入 Bioconductor 原始镜像不够。

### 1. 本地构建与导出（项目根目录）

服务器 `uname -m` 为 `x86_64` 时使用 `linux/amd64`；为 `aarch64` 时改为 `linux/arm64`，并在该架构完成依赖验证。

```bash
git pull --ff-only origin main
docker build --platform linux/amd64 --progress plain -f docker/app/Dockerfile.runtime -t immune-analysis-runtime:3.20-v1 .
docker save -o immune-analysis-runtime-3.20-v1.tar immune-analysis-runtime:3.20-v1
scp immune-analysis-runtime-3.20-v1.tar zhengqinyun@服务器IP:/colddata/SCigblast/platform/
```

归档放在仓库外或上传后移走，避免部署的未跟踪文件检查阻止拉取。在 Windows PowerShell 可将导出路径直接设为 `E:\Desktop\immune-analysis-runtime-3.20-v1.tar`。首次构建仍需要下载并安装依赖，成功后才执行导出；已完成的旧构建层可复用。

### 2. 服务器导入并配置

```bash
docker load -i /colddata/SCigblast/platform/immune-analysis-runtime-3.20-v1.tar
cd /colddata/SCigblast/platform/immune-repertoire-web
bash init-env.sh
nano .env
```

确认 `.env` 使用：

```dotenv
ANALYSIS_RUNTIME_IMAGE=immune-analysis-runtime:3.20-v1
APP_DOCKERFILE=docker/app/Dockerfile.analysis
ANALYSIS_FLAVOR=full
```

保留已设置的数据路径、UID/GID、端口和密钥，然后执行 `bash deploy.sh`。应用镜像从本机导入的基础镜像构建；不要启用 `--pull` 强制向远端查找这个本地标签。前端 npm 构建、数据库等其他镜像仍可能需要网络，并非完全离线部署。

### 3. 后续更新

普通业务代码或分析脚本变化：服务器依次执行 `bash init-env.sh`、编辑 `.env`、`bash deploy.sh`。Python 依赖清单、R 安装脚本或 `Dockerfile.runtime` 变化：先重新构建基础镜像，使用新标签（例如 `3.20-v2`）导出上传，服务器导入并修改 `ANALYSIS_RUNTIME_IMAGE`，再部署。应用构建会比对环境快照，依赖不一致时停止并提示，不能跳过检查。旧基础镜像保留供回退。

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

Compose 对应用和工作进程设置资源上限，均可在 `.env.docker` 调整：

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| API_CPUS / API_MEMORY_LIMIT | 2 / 2g | 单个接口容器的 CPU 配额与内存上限 |
| WORKER_CPUS / WORKER_MEMORY_LIMIT | 4 / 8g | 每个分析工作进程容器的资源上限 |
| ANALYSIS_NUM_THREADS | 1 | OpenMP、OpenBLAS、MKL、NumExpr 的默认数值计算线程数 |
| ANALYSIS_TIMEOUT_SECONDS | 7200 | 队列任务超时秒数 |
| WORKER_STOP_GRACE_PERIOD | 2m | 停止容器时等待工作进程退出的最长时间 |

这些是可调的初始上限，不是已测得的最低服务器配置。数据库、文件缓存和宿主机也需内存空间。
一个 RQ 工作进程同时执行一个顶层任务；增加工作进程容器数量时，应按数量计算总资源预算。
默认数值线程数限制内部并行，避免多个任务各自开启大量线程；不改变统计检验定义。
显式设置线程数的模块仍需结合实际运行参数检查。

超过内存上限可能被系统终止；任务超时或停止宽限结束不提供算法断点续算。长任务升级前应先等待任务结束。
现有配置文件不会被初始化器覆盖，可手工加入以上配置后重新创建对应容器使其生效。
本节新增上限尚未应用到现有运行服务，需完成新镜像验收后统一发布。


### Linux 全量冷备份与恢复

工具 `docker/operations/cold_backup.py` 备份五个数据卷和 `.env.docker`，保留文件所有权。
备份包含数据库凭据，应存放在受限目录。工具检查归档可读性，不代替数据库启动恢复验收。
执行前停止接收新任务，等待队列和运行任务清空，再停止全部服务；工具自身不会停止服务。
以下命令在仓库根目录执行，适用于默认项目名 `immune-platform`、默认完整镜像和 Linux Bash。
自定义项目名时必须替换卷名，并先用 `docker volume inspect` 确认源卷存在，避免备份新建空卷。

```bash
rtk docker volume inspect immune-platform_app_data immune-platform_app_tmp immune-platform_mysql_data immune-platform_mongo_data immune-platform_redis_data
rtk proxy mkdir -p -m 700 backups
rtk docker compose --env-file .env -f compose.docker.yml stop
rtk docker run --rm --network none --user 0:0 \
  --mount type=bind,src="$PWD/docker/operations",dst=/operations,readonly \
  --mount type=bind,src="$PWD/.env.docker",dst=/config/.env.docker,readonly \
  --mount type=bind,src="$PWD/backups",dst=/backups \
  --mount type=volume,src=immune-platform_app_data,dst=/volumes/app_data,readonly \
  --mount type=volume,src=immune-platform_app_tmp,dst=/volumes/app_tmp,readonly \
  --mount type=volume,src=immune-platform_mysql_data,dst=/volumes/mysql_data,readonly \
  --mount type=volume,src=immune-platform_mongo_data,dst=/volumes/mongo_data,readonly \
  --mount type=volume,src=immune-platform_redis_data,dst=/volumes/redis_data,readonly \
  immune-platform-api:full python /operations/cold_backup.py backup --archive /backups/platform.tar.gz
rtk docker compose --env-file .env -f compose.docker.yml up -d --no-build --wait
```

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
  --mount type=volume,src=immune-restore_app_tmp,dst=/volumes/app_tmp \
  --mount type=volume,src=immune-restore_mysql_data,dst=/volumes/mysql_data \
  --mount type=volume,src=immune-restore_mongo_data,dst=/volumes/mongo_data \
  --mount type=volume,src=immune-restore_redis_data,dst=/volumes/redis_data \
  immune-platform-api:full python /operations/cold_backup.py restore --archive /backups/platform.tar.gz
```

工具拒绝非空目标卷、非空配置目录、越界归档路径和越界链接。归档解包成功后，
先将恢复配置中的 HTTP_PORT 改为未占用端口，再用 `-p immune-restore`、
`--env-file restore-config/.env.docker` 启动同一 Compose，避免与原服务冲突。
验收必须包括数据库健康、项目与资产完整性、历史文件下载及一次小型分析。
已使用隔离 Linux 容器完成 MySQL 8.0、MongoDB 7.0、Redis 7 的合成数据冷备份与恢复：
停库后备份五卷，恢复到空卷，再启动三个数据库并读回原记录，同时检查应用文件和配置。
MySQL 的 mysql.sock 运行时符号链接不进入备份，由数据库启动时重建。
回归编排脚本为 `docker/tests/test-cold-restore.ps1`，宿主机只管理 Docker，不安装分析运行环境。
这项验证未覆盖恢复后的平台登录/内部入口、实际项目资产关系及完整分析任务，仍需应用级恢复验收。


### 上传请求大小

`.env.docker` 的 `UPLOAD_MAX_MB` 为正整数，单位为兆字节（1024² 字节），默认 100。
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

冷备份工具内部保留 `config/.env.docker` 归档名称以兼容旧备份。备份时把当前 `.env` 挂载到容器 `/config/.env.docker`；恢复出的 `.env.docker` 核对后作为部署 `.env` 使用。


## 应用文件所有者与数据根目录

`APP_UID` / `APP_GID` 必须填写服务器 `id -u zhengqinyun` / `id -g zhengqinyun` 的实际结果；Linux 文件所有权由数字编号决定。初始化器在使用 `--user` 的容器中记录对应编号；已有配置不会重写。`APP_STORAGE_USER` 标识服务器文件所有者，不能替代 UID/GID；业务子目录使用应用账号用户名。

`APP_DATA_DIR` 可设为宿主机绝对目录，省略时保留原有 app_data 卷。更改该变量不会自动搬迁旧卷，请先完成数据备份和恢复。已有文件权限迁移前停止 API 和工作进程，再运行权限初始化并启动：

```bash
docker compose --env-file .env -f compose.docker.yml stop api worker
docker compose --env-file .env -f compose.docker.yml --profile operations run --rm --no-deps volume-init
docker compose --env-file .env -f compose.docker.yml up -d --wait
```

权限初始化只对应用数据和临时目录设置指定用户所有权，跳过符号链接，不修改数据库自身的数据卷用户。必须先构建包含最新权限初始化代码的应用镜像。独立上传/结果根目录及账号/项目/分析时间目录规则见本文多用户升级章节。


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

新上传：`APP_UPLOAD_DIR/用户名/项目ID/assets/数据类型/文件`；新核心分析结果：`APP_RESULTS_DIR/用户名/项目ID/分析类型_年月日_时分秒__唯一标识/`。上传、结果和原应用数据使用独立挂载；原数据路径继续保留，历史资产按数据库记录读取，不自动搬动或改归属。

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

本地现有 `.env` 已补齐缺失的四项，未改变其他密钥。该文件不提交 Git，因此服务器仍需自行配置。该账号与 APP_STORAGE_USER（Linux 文件所有者）独立；普通业务界面仍按自己的项目范围访问。


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
