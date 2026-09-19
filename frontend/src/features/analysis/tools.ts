export const analysisCategories = [
  { id: "overview", title: "组库概览与多样性", description: "了解测序规模、链组成及样本指标差异。" },
  { id: "clones", title: "克隆特征与共享", description: "查看优势克隆、共享 CDR3 与样本间关系。" },
  { id: "genes", title: "V/J 基因特征", description: "探索基因配对及组间使用差异。" },
  { id: "bcr", title: "BCR 与体细胞突变", description: "比较 IG 链指标、SHM 与 B 细胞成熟状态。" },
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
  { id:"reads", category:"overview", title:"测序读段与链组成", description:"比较各样本 TCR / IG 链的 读段数量与占比。", input:"样本指标表", output:"条形图 · 数据表", scheme:"sequencing_reads_chart" },
  { id:"profile", category:"overview", title:"组库指标与分组比较", description:"选择样本指标，查看组间分布与统计比较。", input:"样本指标表", output:"箱线图 · 统计表", module:"profile" },
  { id:"topclone", category:"clones", title:"优势克隆分析", description:"按 前若干位、链及分组比较优势克隆。", input:"克隆序列表与样本指标表", output:"克隆图表 · 明细", module:"topclone" },
  { id:"sharing", category:"clones", title:"CDR3 共享分析", description:"计算共享特征，并生成 V/J 基因使用 等后续分析数据。", input:"克隆序列表与样本指标表", output:"共享矩阵 · V/J 基因使用", module:"pep-analysis" },
  { id:"similarity", category:"clones", title:"样本相似性热力图", description:"通过组库热力图查看样本间关系。", input:"克隆序列表", output:"热力图 · 报告", module:"charts", preset:{selected_modules:["heatmap"]} },
  { id:"clone-distribution", category:"clones", title:"克隆分布树图", description:"以矩形树图展示样本的克隆组成。", input:"克隆序列表", output:"树图 · 报告", module:"charts", preset:{selected_modules:["treemap"]} },
  { id:"vj-pairing", category:"genes", title:"V/J 基因配对", description:"通过弦图查看 V/J 基因配对关系。", input:"克隆序列表", output:"弦图 · 报告", module:"charts", preset:{selected_modules:["chord"]} },
  { id:"vj-difference", category:"genes", title:"V/J 使用差异", description:"比较已生成的 V/J 基因使用 数据；请先完成 CDR3 共享分析。", input:"克隆序列表与 V/J 基因使用缓存", output:"火山图 · 差异表", module:"volcano", preset:{input_mode:"usage"} },
  { id:"ig-metrics", category:"bcr", title:"IG 链指标", description:"比较 IGH、IGK、IGL 的 读段数、UCDR3 及多样性指标。", input:"IG 指标表", output:"指标图表 · 数据表", scheme:"ig_metrics" },
  { id:"shm", category:"bcr", title:"SHM 分析", description:"展示已计算的体细胞高频突变指标与分布。", input:"SHM 指标表", output:"SHM 图表 · 数据表", scheme:"shm_analysis" },
  { id:"bcell", category:"bcr", title:"B 细胞成熟状态", description:"比较基于 读段数 / 克隆的成熟状态指标。", input:"B 细胞指标表", output:"比例图 · 数据表", scheme:"ig_other_isotype" },
  { id:"db-alignment", category:"annotation", title:"数据库比对", description:"将 CDR3 与参考数据库比对，查看匹配注释。", input:"克隆序列表与样本指标表", output:"注释报告 · 明细", module:"db-alignment" },
  { id:"pgen", category:"annotation", title:"克隆生成概率", description:"估计 CDR3 的生成概率并比较分组分布。", input:"克隆序列表与样本指标表", output:"概率明细 · 分布图", module:"pgen-analysis" },
  { id:"mait-nkt", category:"annotation", title:"MAIT / NKT 特征", description:"基于 TRA 数据查看 MAIT / NKT 相关特征。", input:"克隆序列表或受体 α 链数据", output:"特征图表 · 明细", module:"mait-nkt" },
  { id:"expression", category:"transcriptome", title:"转录组差异分析", description:"配置表达比较与阈值，查看差异特征。", input:"转录组表达表", output:"火山图 · 差异表", module:"volcano", preset:{input_mode:"expression"} },
  { id:"go-kegg", category:"transcriptome", title:"GO / KEGG 富集", description:"从表达比较探索 GO 功能与 KEGG 通路。", input:"转录组表达表", output:"富集图 · 通路表", module:"go-kegg-enrichment" },
  { id:"umap", category:"modeling", title:"UMAP 样本降维", description:"基于样本指标查看样本结构。", input:"样本指标表", output:"降维图 · 坐标表", module:"umap" },
  { id:"umapin", category:"modeling", title:"UMAP 特征降维", description:"探索克隆序列衍生特征；需先生成相应 基因使用缓存。", input:"克隆序列表与特征缓存", output:"降维图 · 数据表", module:"umapin" },
  { id:"ml", category:"modeling", title:"机器学习", description:"选择标签与特征，运行已有分类模型并查看评估。", input:"样本指标或基因使用特征", output:"模型指标 · ROC", module:"ml-analysis" },
];
export const toolPath = (tool: AnalysisTool) => `/analysis/tools/${tool.id}`;
