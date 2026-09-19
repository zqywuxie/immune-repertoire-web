# 用户、项目与分析流程改造记录

日期：2026-09-19。所有测试、应用构建及分析验证均在 Docker 中执行。

## 本次实现

- 主业务导航收敛为分析中心、任务与结果，项目创建与四类输入上传嵌入分析中心。移除 BCR 和无关工具路由入口，保留必要项目详情。
- 真实注册、登录、退出和账号页；密码使用已有哈希机制。认证修改要求会话校验令牌；跨站写操作被拒绝。退出和账号切换清除前端请求缓存及项目数据状态。
- 项目、任务、资产、预览及下载校验真实账号。管理员在普通业务页面同样按自身账号隔离。
- 上传 PEP、Profile、转录组和细胞浸润表后记录文件版本、状态、结构及校验摘要。Redis 模式在后台校验；待校验文件不会在分析配置阶段重复扫描。版本不变复用摘要，平台外修改要求重新上传。
- 复用 User、Project、ProjectAsset、AnalysisJob，未引入平行用户表或任务框架。任务响应补充分析名称、完成时间、输出目录与结果文件清单。
- 新输入按“账号/项目/assets/类型”存放，正式结果按“账号/项目/分析类型_日期_时间__随机标识”存放。同秒运行使用原子建目录避免覆盖。
- 测序量分析复用已校验项目资产，生成实际图片、表格、JSON 和压缩包。组合图表登记子结果及父任务归档。缓存复用请求保留独立记录和引用清单，避免复制大结果；引用中的原结果文件受清理保护。
- 新部署登录默认开启。上传、结果、原应用数据分开挂载；APP_UID/APP_GID 对应服务器实际用户，逻辑账号不改变 Linux 文件所有者。

## 关键文件

| 位置 | 改动 |
| --- | --- |
| flask_app/routes/api_auth.py、services/user_scope.py | 会话认证与用户范围 |
| frontend/src/shared/context/AuthContext.tsx、shared/api/client.ts | 真实身份及缓存隔离 |
| frontend/src/app/App.tsx、shared/components/Sidebar.tsx | 两项业务导航及认证路由 |
| frontend/src/features/projects/AnalysisProjectPanel.tsx | 项目选择、创建及上传 |
| flask_app/services/input_validation_cache.py、input_quality.py | 文件版本、后台校验和摘要复用 |
| flask_app/services/project_storage_paths.py | 安全目录、原子分配、复用记录 |
| flask_app/services/generic_result_storage.py | 旧分析 JSON/图表落盘及结果资产 |
| flask_app/services/project_asset_service.py、result_path_resolver.py | 资产登记及历史结果解析 |
| flask_app/routes/api_jobs.py | 项目校验及被引用结果保护 |
| compose.docker.yml、docker/init_env.py、.env.example | 独立挂载与认证默认配置 |

## 验证范围

前端 33 个测试文件、106 项测试通过，TypeScript/Vite 生产构建通过。后端已通过注册登录、账号隔离、上传缓存、队列、任务结果、旧分析 API 及 Docker 启动的针对性回归。

合成小数据验证了注册→项目→Profile 上传→真实分析→结果预览/下载，以及另一个账号被拒绝访问；测序量分析连续两次运行产生不同目录。另验证热图实际报告、压缩包、缓存引用目录及删除保护。PEP→UMAP 的真实下游流程在独立容器通过。

容器 Chromium 验证注册、两项导航、项目创建、上传校验、账号页和退出；390px 窄屏无横向溢出。前后端镜像构建通过，依赖指纹一致，未重新安装 R/Python 分析环境。

## 部署与边界

执行步骤见 ../docker-deployment.md 的多用户升级章节。既有 .env 和生产数据均未修改，未执行服务器部署。旧资产沿用数据库中的原始路径，不自动搬迁；user_id 为空的项目需先核对归属，不能自动交给新注册账号。

校验缓存针对平台管理的上传版本；旧外部路径引用没有不可变版本，仍需检查其实际内容。一次真实分析读取输入用于计算属于正常行为，不属于配置页重复校验。

本次没有改动科学算法和统计定义，也未逐一重跑所有大型 R 富集/Pgen/机器学习数据集。上线前应使用项目认可的小型基准数据核对各算法的数值结果。既有报告中的部分科学英文标签保留，新增交互文案为中文。


## 工作流与记录机制

分析：注册/登录 → 选择或新建项目 → 上传四类输入 → 查看校验状态 → 选择分析及必要上游结果 → 创建所属账号和项目的 AnalysisJob → worker 执行 → 登记实际结果文件和 processed_result 资产 → 任务与结果中预览/下载。历史任务不以相同参数覆盖；重试生成独立任务。

校验：上传时保存文件及版本 → 建立待校验状态 → 后台读取和保存摘要 → 配置阶段检查版本与文件快照 → 复用摘要或等待后台完成。发生新版本或校验器版本变化时重新校验；检测到平台外修改则要求重新上传。正式计算仍读取实际输入。

鉴权采用既有 Flask-Login 服务端签名会话，密码哈希沿用 User 模型；不新增自行管理的浏览器令牌体系。所有用户身份来自后端会话，项目与资产归属由 SQL 记录校验。旧 Analysis 表继续服务原分析实现，统一任务目录使用既有 AnalysisJob，未新增数据库表。

建议部署前先核对 APP_UID/APP_GID、上传/结果挂载及历史项目账号归属；部署后用两个测试账号验收一次上传、分析和下载，再导入真实业务数据。外部路径历史输入如需同样的稳定校验缓存，应重新上传为平台管理的文件版本。

## 完整逐文件修改清单

| 文件 | 本次修改 |
| --- | --- |
| `.env.example` | 新增认证默认配置及上传、结果根目录示例。 |
| `backend-api/app/core/auth.py` | 未配置服务令牌时拒绝请求，避免默认匿名放行。 |
| `compose.docker.yml` | 启用认证默认值，API/worker/权限初始化共享独立上传与结果挂载。 |
| `docker/app/Dockerfile.analysis` | 预建用户上传及结果目录，继续复用版本化运行环境。 |
| `docker/init_env.py` | 生成新配置时默认使用认证容器模式，保留已有配置。 |
| `docs/architecture/current-system.md` | 更新实际入口、认证和存储边界。 |
| `docs/architecture/user-project-implementation.md` | 汇总实现、逐文件清单、验证及边界。 |
| `docs/docker-deployment.md` | 补充升级配置、UID/GID、独立挂载及旧数据归属核对。 |
| `flask_app/app.py` | 注册认证 API，限制跨站写入，校验活跃账号并返回真实身份。 |
| `flask_app/config.py` | 支持结果根目录、项目数据根目录及分析时区配置。 |
| `flask_app/models/database.py` | 为现有任务响应补充分析、完成时间、输出目录和文件字段。 |
| `flask_app/routes/api/files.py` | 文件列表兼容项目 Profile 资产；旧上传接口绑定所属项目目录。 |
| `flask_app/routes/api_analysis.py` | 兼容已校验项目资产输入，校验文件与项目一致。 |
| `flask_app/routes/api_auth.py` | 实现会话选项、注册、登录和退出及 CSRF 令牌校验。 |
| `flask_app/routes/api_auto_heatmap.py` | 图表任务保留项目归属，结果登记为项目资产并校验任务访问。 |
| `flask_app/routes/api_chord.py` | 图表任务保留项目归属，结果登记为项目资产并校验任务访问。 |
| `flask_app/routes/api_jobs.py` | 提交校验项目归属，缓存请求保留任务，清理保护被引用结果。 |
| `flask_app/routes/api_script_hub/_common.py` | 结果登记失败向上传播，完成后附文件清单，复用生成独立引用目录。 |
| `flask_app/routes/api_script_hub/boxplot.py` | 分析服务从所属任务解析用户项目结果根目录。 |
| `flask_app/routes/api_script_hub/enrichment.py` | 分析服务从所属任务解析用户项目结果根目录。 |
| `flask_app/routes/api_script_hub/modules_config.py` | 配置检查复用上传摘要，分析服务使用任务项目目录。 |
| `flask_app/routes/api_script_hub/profile_analysis.py` | 分析服务从所属任务解析用户项目结果根目录。 |
| `flask_app/routes/api_script_hub/tasks_results.py` | 任务及结果访问去除管理员和测试模式的隐式越权。 |
| `flask_app/routes/api_treemap.py` | 图表任务保留项目归属，结果登记为项目资产并校验任务访问。 |
| `flask_app/routes/auth.py` | 旧 GET 入口跳转新页面，去除旧表单注册和 GET 退出。 |
| `flask_app/services/api_job_runner.py` | 校验后台所属用户，组合图表传递项目并处理结果登记错误。 |
| `flask_app/services/background_job_service.py` | 旧通用分析在完成前落盘并注册结果。 |
| `flask_app/services/boxplot_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/chord_report_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/db_alignment_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/generic_result_storage.py` | 保存测序量和组合分析结果、报告、压缩包及项目资产。 |
| `flask_app/services/go_kegg_enrichment_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/input_preparation.py` | 整理后的输入使用项目目录并记录不可变版本。 |
| `flask_app/services/input_quality.py` | 保存样本/结构摘要，校验 PEP 必需字段和拷贝数，复用文件缓存。 |
| `flask_app/services/input_validation_cache.py` | 按版本及文件快照缓存校验，支持后台队列并避免重复扫描。 |
| `flask_app/services/mait_nkt_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/ml_analysis_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/path_access_service.py` | 识别账号项目/结果目录，移除管理员额外全局路径访问。 |
| `flask_app/services/pep_analysis_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/persistent_queue.py` | 恢复真实任务身份并传递项目上下文。 |
| `flask_app/services/pgen_analysis_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/project_asset_service.py` | 上传记录版本并调度校验，按独立任务登记实际结果文件。 |
| `flask_app/services/project_service.py` | 按账号检查项目重名，使用统一项目数据目录。 |
| `flask_app/services/project_storage_paths.py` | 安全路径构造、原子分配、图表登记和复用引用记录。 |
| `flask_app/services/result_path_resolver.py` | 按所属资产解析新目录，保留旧目录及生成中的报告解析。 |
| `flask_app/services/script_hub_job_service.py` | Redis 部署持久化失败时显式报错，不退回进程内记录。 |
| `flask_app/services/similarity_heatmap_report_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/topclone_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/treemap_report_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/umap_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/umapin_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/services/user_scope.py` | 统一用户范围，管理员普通业务访问同样受账号限制。 |
| `flask_app/services/volcano_service.py` | 使用统一原子结果目录分配，保留现有分析算法和文件格式。 |
| `flask_app/tests/test_pipeline_comparison_api.py` | 明确测试所需内部匿名模式，适配新结果目录及测试隔离。 |
| `flask_app/tests/test_project_asset_service.py` | 明确测试所需内部匿名模式，适配新结果目录及测试隔离。 |
| `flask_app/tests/test_script_hub_api.py` | 明确测试所需内部匿名模式，适配新结果目录及测试隔离。 |
| `flask_app/tests/test_session_auth.py` | 新增真实账号、跨用户拒绝、Profile/测序量/热图落盘及复用引用回归。 |
| `flask_app/tests/test_upload_validation_cache.py` | 新增上传校验复用、外部修改拒绝、PEP 内容及待校验不重复扫描回归。 |
| `frontend/src/__tests__/AccountCache.test.ts` | 验证身份切换后在途旧请求不会污染缓存。 |
| `frontend/src/__tests__/AnalysisToolFlow.test.tsx` | 更新 BCR 已从工具目录移除的预期。 |
| `frontend/src/app/App.tsx` | 收敛业务路由，新增注册/账号页，按账号重建数据上下文。 |
| `frontend/src/features/analysis/tools.ts` | 移除 BCR 类别及工具入口。 |
| `frontend/src/features/assets/InputValidationStatus.tsx` | 显示上传文件校验结果并轮询待完成状态。 |
| `frontend/src/features/projects/AnalysisProjectPanel.tsx` | 嵌入项目选择、新建和上传面板。 |
| `frontend/src/pages/analysis/AnalysisCenter.tsx` | 加入项目面板，移除无关工具区。 |
| `frontend/src/pages/analysis/UnifiedAnalysis.tsx` | 移除重复文件上传，复用已校验项目表。 |
| `frontend/src/pages/auth/Account.tsx` | 显示真实账号及邮箱。 |
| `frontend/src/pages/auth/Login.tsx` | 使用真实认证，提供注册入口及中文反馈。 |
| `frontend/src/pages/auth/Register.tsx` | 新增中文注册表单和注册后身份刷新。 |
| `frontend/src/shared/api/auth.ts` | 接入后端认证和 CSRF 令牌，切换账号清缓存。 |
| `frontend/src/shared/api/client.ts` | 支持请求头，防止旧在途请求重新污染缓存。 |
| `frontend/src/shared/components/Sidebar.tsx` | 只保留两项业务导航，加入账号和真实退出操作。 |
| `frontend/src/shared/context/AuthContext.tsx` | 去除伪造身份回退，传播实际登录退出错误。 |
