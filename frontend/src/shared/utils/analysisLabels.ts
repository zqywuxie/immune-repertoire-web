export const analysisLabels: Record<string,string> = {
  "immune-infiltration-consistency": "免疫浸润细胞相关性",
  "immune-infiltration-concordance": "浸润与亚类方向比较",
  "immune-infiltration-pathway": "GO-BP 与浸润方向比较",
  "immune-infiltration-sample-pathway": "GO-BP 与浸润样本级相关性",
  "immune-infiltration-paired": "浸润与亚类配对相关性",
  "immune-infiltration":"免疫浸润组成与比较",
  "profile": "组库指标与分组比较",
  "profile-composition": "受体链与免疫球蛋白亚类构成",
  "profile-csr": "免疫球蛋白类别转换矩阵",
  "igh-subclass-topclone": "IGH 亚类优势克隆",
  "boxplot": "分组箱线图",
  "pep-analysis": "克隆共享分析",
  "topclone": "优势克隆分析",
  "db-alignment": "数据库比对",
  "pgen-analysis": "生成概率分析",
  "umap": "统一多模态 UMAP",
  "umapin": "特征降维",
  "volcano": "差异分析",
  "go-kegg-enrichment": "基因功能与通路富集",
  "ml-analysis": "机器学习",
  "mait-nkt": "特征细胞分析",
  "charts": "组库图表",
  "charts.combined": "组库图表",
  "treemap.generate": "克隆分布树图",
  "chord.generate": "基因配对弦图",
  "statistical.analyze": "统计分析",
  "statistical.boxplot": "统计箱线图",
  "statistical.analyze-multiple": "多指标统计",
  "statistical.summary-boxplot": "汇总箱线图",
  "statistical.analyze-batch": "批量统计",
  "statistical.analyze-direct": "直接统计",
  "auto-heatmap.generate-heatmap": "组库热力图",
  "auto-heatmap.generate-pipeline-report": "分析流程报告",
  "auto-heatmap.generate-heatmap-report": "热力图报告",
  "auto-heatmap.export-shared-cdr3": "共享克隆序列导出",
  "ppt.scan-images": "扫描报告图片",
  "ppt.load-image": "读取报告图片",
  "ppt.render-slides": "生成演示文稿",
  "ppt-comparison.scan-heatmaps": "扫描比较热力图",
  "ppt-comparison.generate": "生成比较报告",
  "analysis.execute": "数据分析",
  "analysis-batch": "组合分析",
  "analysis.batch": "批量数据分析",
  "analysis.execute-unified": "指标方案分析",
  "script-hub": "组合分析"
};
export const analysisLabel = (key?: string | null) => key ? analysisLabels[key] || (/[\u4e00-\u9fff]/.test(key) ? key : "其他分析") : "分析结果";


const defaultJobTexts: Record<string,string> = {
  "inspect assets":"检查指标输入", "profile analysis":"指标分组分析",
  "boxplot analysis":"分组箱线图分析", "boxplot analysis (ungrouped)":"不分组箱线图分析",
  "boxplot summary":"指标汇总图", "boxplot completed":"箱线图已完成",
  queued:"等待执行",running:"执行中",completed:"已完成",failed:"失败",cancelled:"已取消",interrupted:"已中断",
  "task started":"任务已开始执行。",
  "task created and waiting to start":"任务已创建，等待开始。", "task completed":"任务已完成。",
  "job cancelled by user.":"用户已取消任务。", "job cancelled before start.":"任务已在开始前取消。",
  "job cancellation requested.":"已请求取消任务。",
};
export function jobTextLabel(text?: string | null): string {
  if (!text) return "";
  const mapped = defaultJobTexts[text.trim().toLowerCase()];
  if (mapped) return mapped;
  return text
    .replace(/^Reading datapoint from (.+)$/, "正在读取样本指标表：$1")
    .replace(/^Starting with (\d+) columns$/, "已读取 $1 列，开始核对分组与指标。")
    .replace(/^Processing (.+)$/, "正在分析：$1")
    .replace(/^Rendering summary (.+)$/, "正在绘制汇总图：$1")
    .replace(/^(?:Profile|Boxplot) generated (\d+) plots$/i, "指标分析已完成，生成 $1 张图。")
    .replace(/^Generated (\d+) plot\(s\)/, "已生成 $1 张图。")
    .replace(/ — (\d+) comparison\(s\) skipped \(groups need ≥2 data points\)$/, "已跳过 $1 项比较：每组至少需要 2 个有效数据点。");
}
