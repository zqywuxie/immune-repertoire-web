# 免疫浸润脚本来源与平台适配

来源：用户原始目录 `E:/Desktop/project/immune_pipeline/pipeline`。
仅纳入 `07.immuneInfiltration/02.plot_deconv_composition.R`、`03.plot_deconv_group_comparison.R`、`plot_deconv_helpers.R` 和 `common/configuration/config.R`，不包含业务数据。

平台适配：编号按文字读取以保留前导零；纵轴使用中文；替换一处青色配色。执行参数使用 150 dpi、关闭逐细胞拆图，输出组成总图、比较总图和统计表。统计定义沿用原始脚本：全局最小值平移加 1e-6 后按行归一化；原始分数双侧 Wilcoxon（exact=FALSE），全部细胞/组对统一 BH 校正。箱线图星号基于原始 p 值，校正结果见 q_value 列。

入口为 `flask_app/services/infiltration_service.py`，输入必须来自当前项目选定数据集；不从文件名推断分组或相对/绝对模式。原始参考目录无需挂载到服务器，所需脚本随应用镜像发布。

部署沿用根目录 `.env` 和 `deploy.sh`。完整分析镜像需要 data.table、ggplot2、patchwork、jsonlite，构建阶段会检查；样本级 GO-BP 分析另需 GSVA、AnnotationDbi、org.Hs.eg.db、GO.db。数据库、上传和结果继续使用既有持久卷。


## 细胞相关性（C1）

`04.plot_cell_consistency.R` 提取自原始 `plot_deconv_consistency_core.R` 的 C1 结束位置，保留秩转换、组别回归残差相关、原脚本残差 Pearson 检验、细胞对 BH 校正及扇形热图。保留 pooled Spearman 补充矩阵与统计表。p 值沿用原脚本实现，不能另称采用了扣除组别参数自由度的新检验。

平台补充前导零保留、输入数值类型参数、中文标题、150 dpi 和蓝红配色。至少两个细胞、每组至少三个样本，秩残差无变化的列在运行前拒绝。该入口不执行 C2 跨模态一致性或分组内补充热图。

新增 R 依赖 ComplexHeatmap、circlize，安装定义和构建检查已同步。既有依赖镜像需要更新一次；以后代码部署继续复用更新后的镜像。本地验收镜像为 `immune-analysis-runtime:3.20-consistency`，应用镜像为 `immune-platform-api:consistency-local`。服务器使用前需导入或按 `docker/app/Dockerfile.runtime` 构建新的依赖镜像，并将 `.env` 的 `ANALYSIS_RUNTIME_IMAGE` 设置为相应标签；本轮没有部署服务器。


## 亚类与浸润组间方向比较（C2）

`05.plot_directional_concordance.R` 取自原始一致性核心脚本的配置、输入及 C2 组间方向分支，独立于 C1 和样本配对分支。支持原脚本中的 IGHM、IGHD、IGHA1、IGHA2、IGHG3、IGHG4、IGHGP、IGHE 指标，由用户选择。使用本次浸润样本在样本表中对应的指标记录；额外样本不参与并显示数量。参与指标缺失或非法时拒绝，不沿用原脚本静默补零。

组间中位数差、单侧 Wilcoxon 组合的方向联合 p 值及每个组对内的 BH 校正保持原计算方式。原图例将联合值误写为 max raw p，现已按代码中的 joint_p 标注；零中位数差不再标作方向一致。CSV 增加 Group1/Group2，输出文件使用比较编号，避免中文分组名被替换后覆盖。科研字段名保持原样，交互和图例使用中文。

本入口不读取或推断样本配对清单，不执行样本级跨模态相关性，也不新增 BCR 克隆分析流程。复用 C1 的运行环境依赖，无需再次增加依赖。

## 浸润与亚类配对相关性（C2 样本级）

`06.plot_paired_concordance.R` 独立执行原始 C2 样本级分支。输入为项目登记的样本指标表和浸润结果，用户明确指定一对一配对，支持两侧编号不同、原始行顺序不同；同编号填写也需要主动点击。未配对记录排除，重复或未知编号拒绝。每组至少三个配对，至少两个分组。分组取自配对后的指标表，不推断分组。

任务保存 `sample_manifest.csv`，保留两侧编号及分组，前导零不丢失。提交任务与队列实际执行前均按显式配对重新校验，不要求两份输入存在同名编号交集。缺失指标和组别校正后无变化的列在运行前拒绝。

统计沿用原脚本的秩转换、组别回归残差 Pearson 相关与检验，全部亚类与细胞组合统一 BH 校正；同时输出 pooled Spearman 补充结果。这里的 p 值不应解释为额外扣除了组别参数自由度的偏相关检验。复用既有一致性分析依赖镜像。

## GO-BP 与浸润组间方向比较（D1）

`07.plot_pathway_direction.R` 提取原始 `05.plot_deconv_pathway_concordance.R` 的 D1 分支，不运行需要表达矩阵和基因集合的 D1-Sample/D2。来源为当前项目同数据集登记的完整 GO-BP GSEA 表，固定原脚本十项通路，组对及方向必须明确匹配。实际使用的完整表会复制到输出目录。

原脚本 D1-Sample 使用表达矩阵及 Bioconductor 的 `GSVA`、`AnnotationDbi`、`org.Hs.eg.db`、`GO.db`，由独立的下一节入口处理。D2 除表达矩阵外，还需配置 `references.hallmark_database` 指向具有 `gs_name` 和人类基因符号列的 MSigDB Hallmark RDS；当前没有该参考文件，也未接入 D2。

使用原始 NES 方向、细胞组间中位数差及单侧 Wilcoxon 联合检验，全部通路与细胞组合统一 BH 校正。零中位数差改为无方向差异且 joint_p=1，避免把没有方向的结果标作一致或相反；联合证据图例按真实 joint_p 标注。保留前导零，使用中文图例、蓝红配色和 150 dpi。结果表记录 Group1/Group2。

D1 已接入独立配置、任务与结果，前端配置和本地真实 R/API 回归通过。真实 Redis 队列链路已在此前验收。

## GO-BP ssGSEA 与浸润样本级相关性（D1-Sample）

`08.plot_go_sample_concordance.R` 使用原始脚本定义的十项固定 GO-BP 通路及 `org.Hs.eg.db` 的 GOALL 注释，在 `log2(expression + 1)` 上计算 GSVA ssGSEA。用户从三类当前项目数据中明确选择两个比较组；只纳入转录组、浸润结果和样本指标表共同匹配的样本，至少 10 个且每组至少 2 个。转录组额外样本会计数，不自动插补。

通路分数和浸润分数分别秩转换并回归去除组别效应，按组内置换浸润秩残差估计 p 值，所有通路/细胞组合统一 BH 校正。结果包含 GO 基因覆盖率、ssGSEA 分数、相关统计表、方法说明及图。临时筛选表达矩阵在任务结束后删除，不复制进结果目录；R 端使用内部列别名，避免数值样本编号被读取器重命名，原始前导零编号仍用于匹配。

容器回归覆盖真实 GOALL 注释、GSVA 2.x ssGSEA、组内置换、p/q 范围、图表生成、表达值检查、项目数据集注册与任务提交。挂载只读原始 pipeline 对同一合成表达矩阵逐项比较通路分数、rho、10,000 次置换 p 值及 BH q 值，结果与原脚本在 1e-12 容差内一致。Hallmark D2 仍需项目提供经许可且格式符合要求的 MSigDB 参考数据后再接入。
