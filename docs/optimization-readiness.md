# 平台优化验收记录

更新时间：2026-09-12。项目位置：`E:\Desktop\project\immune-repertoire-web`。

## 本轮交付

| 优先级 | 内容 | 已实现与验证 |
|---|---|---|
| P0 | 设置生效 | 接入真实配置接口，按用户及工作区保存；分析方案图表使用保存的尺寸、字体和 DPI。模块自身显式参数优先。 |
| P0 | 分析流程 | 修复 Profile 上传、资产定位、字段与分组检查；统一分析及统计比较使用真实任务和结果；参考脚本覆盖范围见下表。 |
| P0 | 任务可追踪 | 历史任务查询、取消错误提示、结果读取重试、任务地址恢复；修复轮询随渲染重复启动及旧请求覆盖新选择。 |
| P1 | 中文界面与交互 | 白灰底色、蓝色强调；项目创建、空状态、状态提示、分析向导和移动端布局调整。科学术语保留原名。 |
| P1 | PDF / PPT | PDF 上传后真实提取图片与 B 细胞同型表；PPT 解析真实替换目标，上传图片后生成可下载文件。PDF 页面不承诺通用 OCR 或任意表格识别。 |
| P1 | 导出和入门 | 结果增加分析记录 JSON，保留任务参数及输出；`/guide` 提供中文操作说明和明确标为合成数据的 CSV 示例。 |
| P2 | 存储维护 | 设置页显示当前用户已登记上传/项目资产的数量及字节数；维护脚本只清理指定的过期缓存，跳过数据及目录联接。该统计不是磁盘总用量。 |
| 发布前基础 | 访问控制与配置 | 加入路径、结果、任务及 PPT 会话归属检查；生产配置要求强 SECRET_KEY、登录与安全 Cookie；提供 SQLite 一致性备份及恢复验证。尚未部署公网。 |

## 参考脚本 1–10 覆盖

| 目录 | 当前平台覆盖 |
|---|---|
| 01 Profile | Profile 指标、箱线图、分组统计 |
| 02 immunoglobulin | B 细胞同型方案；CSR 专项流程尚未接入 |
| 03 UCDR3 | PEP 共享、TopClone、MAIT/NKT、Pgen 入口 |
| 04 DB | 数据库比对 |
| 05 Gene | V/J 使用情况、火山图 |
| 06 Transcriptome | GO/KEGG 富集入口 |
| 07 immuneInfiltration | 尚未接入网页分析 |
| 08 Cluster | 尚未接入网页分析 |
| 09 ML | 机器学习分析 |
| 10 Umap | UMAP / UMAPin |

上述是入口和流程覆盖，不代表所有科研算法已独立验证。完整 Docker 镜像已启用 SoNNia 和 R/Bioconductor；Pgen 经实际报告生成及下载验收，GO/KEGG 经真实小型计算验收。

本次可找到的参考材料位于 `E:\Desktop\project\immune-repertoire-web-data\_reference\anal_pipeline`。原先指定的 `E:\Desktop\project\immune\_pipeline\pipeline` 当前不存在。现有 Cibersort 目录只有绘图脚本；尚未找到 CSR、07 浸润核心及 08 聚类对应完整脚本和输入约定，因此这些模块仍未完成，不使用替代算法冒充原流程。

## Docker 验收结果

- 前端 20 个测试文件、67 项通过，TypeScript 和生产构建通过。
- 后端和 worker 全量 196 项测试通过，无跳过；实际任务与迁移验证见 Docker 部署说明。
- 六服务架构运行：web、api、worker、MySQL、MongoDB、Redis。
- MySQL/MongoDB 与已登记文件完成迁移，原库已备份恢复核对；详见[迁移数据与验证](docker-deployment.md)。
- API 重启保留排队任务；取消和重试经真实 worker 验证；Script Hub Pgen 报告成功下载。
- 之前的 PDF/PPT、账号隔离、设置、统计与移动端交互回归保留。本轮没有公网发布。

## 存储维护

在项目根目录运行，只查看清单：

```powershell
rtk docker compose --env-file .env.docker -f compose.docker.yml exec api python -B scripts/storage_maintenance.py --root /app
```

清理超过 7 天的已识别缓存：

```powershell
rtk docker compose --env-file .env.docker -f compose.docker.yml exec api python -B scripts/storage_maintenance.py --root /app --clean-caches --older-than-days 7
```

本轮执行结果：可扫描的普通文件约 8.76 MiB，已识别缓存约 1.93 MiB，没有符合 7 天条件的缓存被删除。跳过 9 个受保护入口，11 个入口因访问限制等原因未完整扫描。这不是整个项目及外部数据目录总大小；大型原始数据、结果、参考库、依赖目录和目录联接均未据此删除。早前的临时缓存清理与历史文档归档已完成。

## SQLite 备份及恢复

实际使用 SQLite 时，将以下路径替换成当前数据库位置和一个尚不存在的备份文件：

```powershell
rtk docker compose --env-file .env.docker -f compose.docker.yml exec api python -B scripts/backup_sqlite.py --database <当前数据库绝对路径> --output <新备份文件绝对路径>
```

脚本通过 SQLite 在线备份接口生成副本，并执行完整性检查；拒绝覆盖已存在的目标。恢复时停服，将经检查的备份放入新的数据库位置，设置 `DATABASE_URL` 指向该位置后启动并检查项目、任务记录。测试已验证合成数据库的备份可重新打开并保留记录；没有操作或声称恢复了真实生产数据库。

数据库备份不包含上传文件、项目资产、分析结果及参考库。应将 `E:\Desktop\project\immune-repertoire-web-data` 中实际使用的数据与数据库一同制定备份安排。MySQL 使用其自身的备份恢复工具，不能使用本 SQLite 脚本。

## 公网部署边界

代码已加入生产配置约束，但本轮没有公网部署、真实多用户并发压测或完整安全审计。部署应使用 `FLASK_CONFIG=production`、长度至少 32 的独立 `SECRET_KEY`、启用登录，并由 HTTPS 入口提供服务；安全 Cookie 需要 HTTPS。不要直接将开发服务器用于公网。

Redis 队列及完整分析依赖已落地。07/08 和 CSR 仍缺少对应源脚本；公网域名、证书与服务器尚未提供。大样本性能基准、全量参考脚本数值对照和异常断点恢复属于后续独立验收，不能以小型运行测试替代。
