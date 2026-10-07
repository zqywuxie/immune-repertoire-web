# 科学模块证据与复验入口

更新：2026-10-07。本表整理已经执行的证据，不把测试文件存在当作执行通过，也不把界面验收当作数值对照。本轮数据目录及结果摘要修改没有改变科学算法。

参考源为用户提供的 pipeline 01–10。历史验收实际只读挂载位置为 `E:/Desktop/project/immune_pipeline/pipeline`，容器使用 `REFERENCE_PIPELINE` 指定；用户最早提供的 `_pipeline/pipeline` 路径可能是兼容入口。复验前确认实际脚本，不另复制一套算法。原始脚本没有 Git 版本时以原验收的脚本文件及记录为准，不补造提交号。

## 证据层次

数值：同合成输入执行原脚本和平台方法，对照矩阵、统计量或明确允许的输出；服务：实际产生文件；RQ：真正工作进程执行及保存终态；浏览器：操作真实接口或明确标记的夹具；历史：任务快照、来源和下载保持。各层独立。

共同身份规则：样本编号为文本，保留 001；项目和数据集联合确定范围；映射后身份与原始编号有明确关系；分组/配对由实际方案确定；执行保存输入与参数快照。当前输入变更不会重写历史任务。科学 p/q 值不经过界面 Number 重排。

| 参考目录/模块 | 输入、方向及约定 | 数值与服务复验入口 | 已执行证据及边界 |
|---|---|---|---|
| 01.Profile 箱线图/组成 | Profile 按已确认样本与分组，选择实际指标列；不要求同时提供 PEP | `test_profile_boxplot_reference.py`、`test_profile_composition_service.py`、`test_profile_group_identifiers.py`、`test_profile_workflow.py` | Sep28 数值集67项包含此模块；Oct03报告控件/原始分组/不分组导出，Oct06真实上传→Profile→结果。不同图形仍以对应测试场景为准。 |
| 02.immunoglobulin CSR | 指标表中的亚类量，沿用原脚本缺失值和转换规则 | `test_profile_csr_service.py` | Sep28原CSR矩阵及统计对照；不以其他组成图代替CSR算法。 |
| 02.immunoglobulin IGH亚类优势克隆 | PEP加样本指标/分组，亚类与Top N按原约定 | `test_igh_subclass_topclone_service.py` | 原脚本完整表及效应统计对照；不是BCR全链工作流。 |
| 03.UCDR3 克隆共享/使用汇总 | PEP样本、链、频数和批次身份；保留原频率加权定义 | `test_pep_reference.py`、`test_pep_step2_reference.py`、`test_pep_step5_reference.py`、`test_pep_step6_reference.py`、`test_pep_step12_reference.py`、`test_pep_batch_rq.py` | Sep28多步骤数值；Oct01样本选择；Oct03真PEP→UMAP及原生RQ/历史下载；不宣称目录每个辅助脚本均独立接入。 |
| 03.UCDR3 优势克隆/特殊T细胞/Pgen | 各自链和样本规则，TRA来源仅供兼容特殊T细胞；Pgen模型依赖明确 | `test_topclone_reference.py`、`test_mait_nkt_reference.py`、`test_mait_nkt_rq.py`、`test_pgen_reference.py`、`test_pgen_batch_identity.py` | Sep28对照；Oct01真实Pgen模型，Oct02特殊T细胞上游组合；Oct03显式RQ集包含特殊T细胞。模型计算与分布聚合对照不同，不合并称每条序列概率逐项对照。 |
| 04.DB 数据库比对 | 指定PEP范围及VDJdb/McPAS/IEDB实际可用参考源；参考版本保存 | `test_db_alignment_service.py`、`test_db_alignment_selection.py` | Sep27/28参考比对集，Oct02批次选择及参考可用性，Oct03报告筛选；不编造未挂载参考数据的命中。 |
| 05.Gene V/J差异 | 原V/J产物、所选链与比较前后组，实际检验方向及阈值 | `test_vj_usage_volcano_reference.py`、`test_volcano_selection.py`、`test_volcano_selection_rq.py` | Sep28原检验数值；Oct03八样本服务输出及RQ、原文件下载；产物表头适用性另有精确检查。 |
| 06.Transcriptome 差异/GO/KEGG | 表达矩阵列为样本，基因行；差异表供富集，方向/阈值保留；KEGG按实际联网依赖 | `test_transcriptome_limma_reference.py`、`test_go_ora_reference.py`、`test_expression_selection_rq.py`、`test_enrichment_rq.py`、`test_gsea_full_export.py` | Sep28 limma/ORA数值；Oct03显式联网RQ 1项53.03秒，8样本差异→GO/KEGG含完整GO GSEA和ZIP；不承诺每次均有显著KEGG通路。 |
| 07.immuneInfiltration 已接入六面板 | CIBERSORT及面板实际需要的表达/通路、分组与配对；样本不自动猜测匹配 | `test_infiltration_reference.py`、`test_infiltration_rq.py`、`test_infiltration_pairing.py`、`test_infiltration_concordance.py`、`test_infiltration_pathway.py`、`test_infiltration_sample_pathway.py` | Sep28数值，Oct03六面板显式RQ集及真实选择/配对子集；目标服务器原生两个面板。缺Hallmark或原TCR signature合同不成立的能力维持不可用。 |
| 09.ML | Profile/VJ/联合矩阵、标签、样本和种子；平台嵌套验证口径明确 | `test_ml_reference.py`、`test_ml_nested_cv.py`、`test_ml_batch_rq.py` | Sep28共同输入矩阵对照9项；Oct03实际训练/RQ和浏览器参数检查。原脚本与平台评分口径不同，不做虚假的模型分数逐项等同。 |
| 10.Umap 统一及特征降维 | 确定特征/分类列、所选样本、链及种子；产物和执行器读取相同优先文件 | `test_unified_umap_service.py`、`test_unified_umap_rq.py`、`test_umapin_selection_rq.py`、`test_pep_downstream_workflow.py` | Sep28特征/统计/坐标对照，Oct03服务/RQ/真实候选浏览器；目标服务器UID1012实际8样本及有限坐标、CSV/ZIP，修复Numba缓存权限。 |

## 不扩展的范围与剩余验证

08.Cluster 全链、11.BCR、未成立的原TCR signature，以及缺失真实Hallmark资料的相关面板不在已验收能力内。不能用替代算法使按钮变为“可用”。本表没有将排除范围重新加入待办。

本轮已完成登记1k/10k/25k、UMAP64/256/1024样本×32特征及32/128/256MiB结果包的合成容量测量，见[容量基线](../operations/capacity-baseline.md)。这些档位不是所有模块或真实业务规模上限，原8样本回归仅证明对应功能闭环。共享主机整机重启验收已按用户2026-10-07要求取消，不作为剩余待办。若未来改动算法或输入单位，针对该模块重做原脚本对照、实际产物、RQ及历史复用；交互修改优先复验请求/身份/产物合同。

历史运行记录见 [工作流执行进度](project-input-workflow-progress.md)，重点章节：Sep27原始脚本81项、Sep28数值67项、Oct03集成及联网门禁、目标服务器隔离验收。当前整体优化新增证据见 [执行记录](overall-optimization-execution-20261007.md)。
