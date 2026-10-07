export const assetTypeLabels: Record<string, string> = {
  pep: "克隆序列表", profile: "样本指标表", datapoint: "样本指标表", transcriptome: "转录组",
  deconvolution: "免疫细胞浸润", cibersort: "免疫细胞浸润", processed_result: "分析结果",
  project_file: "项目附件", sample_summary: "样本登记表", group_spec: "分组方案",
  cached_usage: "基因使用结果", cached_step34: "中间结果", raw_archive: "原始归档",
};
export const validationLabels: Record<string, string> = {
  valid: "校验通过", pending: "等待校验", invalid: "校验未通过", needs_mapping: "待确认映射",
  failed: "校验失败", needs_refresh: "旧校验报告，请重新校验识别样本", unknown: "尚未校验",
};
