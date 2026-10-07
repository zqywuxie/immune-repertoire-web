export const analysisCategories = [
  { id: "overview", title: "组库概览与多样性", description: "了解测序规模、链组成及样本指标差异。" },
  { id: "clones", title: "克隆特征与共享", description: "查看优势克隆、共享 CDR3 与样本间关系。" },
  { id: "genes", title: "V/J 基因特征", description: "探索基因配对及组间使用差异。" },
  { id: "annotation", title: "注释与生成概率", description: "结合参考数据库与生成模型解释克隆特征。" },
  { id: "transcriptome", title: "转录组与通路", description: "从表达差异进一步探索功能通路。" },
  { id: "modeling", title: "降维与建模", description: "探索样本结构与特征的分类能力。" },
] as const;
export type AnalysisTool = {
  id: string; category: typeof analysisCategories[number]["id"]; title: string;
  description: string; input: string; output: string;
  module?: string; scheme?: string; preset?: Record<string, unknown>;
};
export const analysisTools: AnalysisTool[] = [
  {id:"infiltration-pathway",category:"transcriptome",title:"GO-BP 与浸润方向比较",description:"复用完整富集结果，比较通路与细胞分数的组间变化方向。",input:"浸润结果、样本表与已完成的 GO-BP 富集",output:"通路方向图 · 联合检验表 · 来源快照",module:"immune-infiltration-pathway"},
  {id:"infiltration-sample-pathway",category:"transcriptome",title:"GO-BP 与浸润样本级相关性",description:"从转录组计算固定 GO-BP 样本分数，再与同一样本浸润分数做组别校正相关。",input:"转录组表达矩阵、免疫浸润结果与样本指标表",output:"ssGSEA 分数 · 组内置换统计 · 相关图",module:"immune-infiltration-sample-pathway"},
  {id:"infiltration-paired",category:"transcriptome",title:"浸润与亚类配对相关性",description:"确认一对一样本配对，查看组别校正后的跨数据相关性。",input:"含亚类指标的样本表与浸润结果",output:"配对相关图 · 统计表 · 配对清单",module:"immune-infiltration-paired"},
  {id:"infiltration-concordance",category:"transcriptome",title:"浸润与亚类方向比较",description:"比较亚类指标与细胞分数的组间变化方向，查看联合检验与校正结果。",input:"含亚类指标的样本表与浸润结果",output:"方向比较图 · 统计表",module:"immune-infiltration-concordance"},
  {id:"infiltration-consistency",category:"transcriptome",title:"免疫浸润细胞相关性",description:"去除组别效应，查看细胞分数共同变化及校正统计。",input:"免疫浸润结果与样本指标表",output:"扇形相关图 · 相关矩阵 · 统计表",module:"immune-infiltration-consistency"},
  {id:"infiltration",category:"transcriptome",title:"免疫浸润组成与比较",description:"查看细胞组成及组间分数差异，导出原始数值和校正统计。",input:"免疫浸润结果与样本指标表",output:"组成图 · 箱线图 · 统计表",module:"immune-infiltration"},
  { id:"reads", category:"overview", title:"测序读段与链组成", description:"比较各样本 TCR / IG 链的 读段数量与占比。", input:"样本指标表", output:"条形图 · 数据表", scheme:"sequencing_reads_chart" },
  { id:"profile", category:"overview", title:"组库指标与分组比较", description:"选择样本指标，查看组间分布与统计比较。", input:"样本指标表", output:"箱线图 · 统计表", module:"profile" },
  { id:"profile-composition", category:"overview", title:"受体链与免疫球蛋白亚类构成", description:"按样本查看 TCR/IG 链比例和免疫球蛋白亚类构成，并核对每个样本归一化前后的总量。", input:"含链比例或免疫球蛋白亚类比例的样本指标表", output:"样本构成图 · 比例明细 · 质量表", module:"profile", preset:{analysis_type:"composition",subclass_measure:"reads"} },
  { id:"profile-csr", category:"overview", title:"免疫球蛋白类别转换矩阵", description:"比较不同组别的 CSR 类别比例与组间差异，导出中位数、检验结果和数据质量表。", input:"含 CSR_ratio、CSR1 或 CSR0 指标的样本指标表", output:"类别矩阵图 · Mann–Whitney 检验 · Kruskal 检验", module:"profile", preset:{analysis_type:"csr",csr_measure:"auto"} },
  { id:"topclone", category:"clones", title:"优势克隆分析", description:"按 前若干位、链及分组比较优势克隆。", input:"克隆序列表与样本指标表", output:"克隆图表 · 明细", module:"topclone" },
  { id:"igh-subclass-topclone", category:"clones", title:"IGH 亚类优势克隆", description:"按免疫球蛋白亚类计算 Top 10/20/50/100 克隆比例，并比较组间变化。", input:"IGH 克隆序列表、含样本分组的指标表", output:"亚类比例表 · 差异热图 · 检验统计", module:"topclone", preset:{analysis_type:"igh_subclass_topclone"} },
  { id:"sharing", category:"clones", title:"CDR3 共享分析", description:"计算共享特征，并生成 V/J 基因使用 等后续分析数据。", input:"克隆序列表与样本指标表", output:"共享矩阵 · V/J 基因使用", module:"pep-analysis" },
  { id:"similarity", category:"clones", title:"样本相似性热力图", description:"通过组库热力图查看样本间关系。", input:"克隆序列表", output:"热力图 · 报告", module:"charts", preset:{selected_modules:["heatmap"]} },
  { id:"clone-distribution", category:"clones", title:"克隆分布树图", description:"以矩形树图展示样本的克隆组成。", input:"克隆序列表", output:"树图 · 报告", module:"charts", preset:{selected_modules:["treemap"]} },
  { id:"vj-pairing", category:"genes", title:"V/J 基因配对", description:"通过弦图查看 V/J 基因配对关系。", input:"克隆序列表", output:"弦图 · 报告", module:"charts", preset:{selected_modules:["chord"]} },
  { id:"vj-difference", category:"genes", title:"V/J 使用差异", description:"比较已生成的 V/J 基因使用 数据；请先完成 CDR3 共享分析。", input:"已完成的 V/J 基因使用结果", output:"火山图 · 差异表", module:"volcano", preset:{input_mode:"usage"} },
  { id:"db-alignment", category:"annotation", title:"数据库比对", description:"将 CDR3 与参考数据库比对，查看匹配注释。", input:"克隆序列表与样本指标表", output:"注释报告 · 明细", module:"db-alignment" },
  { id:"pgen", category:"annotation", title:"克隆生成概率", description:"估计 CDR3 的生成概率并比较分组分布。", input:"克隆序列表与样本指标表", output:"概率明细 · 分布图", module:"pgen-analysis" },
  { id:"mait-nkt", category:"annotation", title:"MAIT / NKT 特征", description:"基于 TRA 数据查看 MAIT / NKT 相关特征。", input:"样本指标表与受体 α 链数据", output:"特征图表 · 明细", module:"mait-nkt" },
  { id:"expression", category:"transcriptome", title:"转录组差异分析", description:"配置表达比较与阈值，查看差异特征。", input:"转录组表达表", output:"火山图 · 差异表", module:"volcano", preset:{input_mode:"expression"} },
  { id:"go-kegg", category:"transcriptome", title:"GO / KEGG 富集", description:"从表达比较探索 GO 功能与 KEGG 通路。", input:"转录组表达表", output:"富集图 · 通路表", module:"go-kegg-enrichment" },
  { id:"umap", category:"modeling", title:"统一多模态 UMAP", description:"组合样本指标与 V/J 使用结果，筛选组间特征并查看投影和 PERMANOVA。", input:"样本指标表；可选 V/J 使用结果", output:"投影图 · 坐标 · 统计表", module:"umap" },
  { id:"umapin", category:"modeling", title:"UMAP 特征降维", description:"探索克隆序列衍生特征；需先生成相应 基因使用缓存。", input:"已生成的 V/J 特征结果", output:"降维图 · 数据表", module:"umapin" },
  { id:"ml", category:"modeling", title:"机器学习", description:"选择标签与特征，运行已有分类模型并查看评估。", input:"样本指标表与标签；可选 V/J 特征", output:"模型指标 · ROC", module:"ml-analysis" },
];
export const toolPath = (tool: AnalysisTool) => `/analysis/tools/${tool.id}`;
