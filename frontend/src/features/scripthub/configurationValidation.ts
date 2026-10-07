import { analysisLabel } from "../../shared/utils/analysisLabels";

export function validateAnalysisPayload(module: string, payload: Record<string, unknown>, usesBatchResult = false) {
  if (["immune-infiltration","immune-infiltration-consistency","immune-infiltration-concordance","immune-infiltration-paired","immune-infiltration-pathway","immune-infiltration-sample-pathway"].includes(module) && (!payload.group_field || !["relative","absolute","other"].includes(String(payload.score_type)) || payload.infiltration_checked !== true)) throw new Error("请核对免疫浸润分析范围，并完成输入检查。");
  if ((module === "volcano" || (module === "go-kegg-enrichment" && payload.input_mode !== "deg")) && Array.isArray(payload.comparisons) && payload.comparisons.length === 0) throw new Error("请至少选择一个组间比较。");
  if (module === "profile" && (!payload.param_begin || !payload.param_over)) {
    throw new Error("请选择要比较的指标范围。");
  }
  const actualSamples = module.startsWith("immune-infiltration") ? (module === "immune-infiltration-paired" ? undefined : payload.selected_infiltration_samples) : module === "go-kegg-enrichment" && payload.input_mode === "deg" ? undefined :
    module === "go-kegg-enrichment" || (module === "volcano" && payload.input_mode === "expression") ? payload.selected_expression_samples : payload.selected_samples;
  if (Array.isArray(actualSamples) && !actualSamples.filter(Boolean).length) {
    throw new Error(`[${analysisLabel(module)}] 请至少选择一个样本，或点击“全部样本”。`);
  }
  const groupError = validateGroupFields(module, payload);
  if (groupError) throw new Error(`[${analysisLabel(module)}] ${groupError}`);
  const groupValueError = validateGroupValues(module, payload);
  if (groupValueError) throw new Error(`[${analysisLabel(module)}] ${groupValueError}`);
  const groupedSampleError = validateGroupedSamples(module, payload);
  if (groupedSampleError) throw new Error(`[${analysisLabel(module)}] ${groupedSampleError}`);
  const cacheError = usesBatchResult ? "" : validateCacheInputs(module, payload);
  if (cacheError) throw new Error(`[${analysisLabel(module)}] ${cacheError}`);
  if (module === "ml-analysis" && normalizeMlMode(payload.mode) !== "vj"
      && (!String(payload.param_begin || "").trim() || !String(payload.param_over || "").trim())) {
    throw new Error("请选择样本指标的起始列和结束列。");
  }
  if (module === "charts") {
    const selectedSamples = Array.isArray(payload.samples) ? payload.samples.filter(Boolean) : [];
    const selectedChains = Array.isArray(payload.selected_chains) ? payload.selected_chains.filter(Boolean) : [];
    if (!selectedSamples.length) {
      throw new Error("请至少选择一个用于绘图的样本。");
    }
    if (!selectedChains.length) {
      throw new Error("请至少选择一个用于绘图的链类型。");
    }
  }
}

function validateGroupFields(module: string, payload: Record<string, unknown>) {
  const groupRequirements: Record<string, string[]> = {
    "db-alignment": ["categories"],
    profile: ["grouptype_fields", "grouping_begin"],
    "pep-analysis": ["group_fields", "grouptype_fields"],
    "pgen-analysis": ["distribution_category_col", "group_field"],
    topclone: ["group_field"],
    umap: ["group_field", "classification_begin"],
    umapin: ["category_col"],
    "ml-analysis": ["label_col"],
    "mait-nkt": ["group_field"],
  };
  const keys = groupRequirements[module] || [];
  if (!keys.length) return "";
  const hasGroupField = keys.some((key) => {
    const value = payload[key];
    if (Array.isArray(value)) return value.some((item) => String(item || "").trim());
    return String(value || "").trim();
  });
  return hasGroupField ? "" : "请选择分组字段";
}

function validateGroupValues(module: string, payload: Record<string, unknown>) {
  const modulesRequiringGroupValues = new Set([
    "db-alignment",
    "profile",
    "pep-analysis",
    "pgen-analysis",
    "topclone",
    "umap",
    "ml-analysis",
    "mait-nkt",
  ]);
  if (!modulesRequiringGroupValues.has(module)) return "";
  const valueMap = payload.selected_group_values;
  if (!valueMap || typeof valueMap !== "object" || Array.isArray(valueMap)) {
    return "请选择分组值";
  }
  const hasValue = Object.values(valueMap as Record<string, unknown>).some((item) =>
    Array.isArray(item) && item.some((value) => String(value || "").trim()),
  );
  return hasValue ? "" : "请选择分组值";
}

function validateGroupedSamples(module: string, payload: Record<string, unknown>) {
  const modulesRequiringGroupSamples = new Set([
    "db-alignment",
    "profile",
    "pep-analysis",
    "pgen-analysis",
    "topclone",
    "umap",
    "ml-analysis",
    "mait-nkt",
  ]);
  if (!modulesRequiringGroupSamples.has(module)) return "";
  const valueMap = payload.selected_samples_by_group;
  if (!valueMap || typeof valueMap !== "object" || Array.isArray(valueMap)) {
    return "请在每个分组中选择样本";
  }
  const selectedGroups = payload.selected_group_values;
  if (!selectedGroups || typeof selectedGroups !== "object" || Array.isArray(selectedGroups)) {
    return "请在每个分组中选择样本";
  }
  for (const [field, values] of Object.entries(selectedGroups as Record<string, unknown>)) {
    if (!Array.isArray(values)) continue;
    const groups = (valueMap as Record<string, unknown>)[field];
    if (!groups || typeof groups !== "object" || Array.isArray(groups)) {
      return `请为 ${field} 选择样本`;
    }
    for (const groupValue of values) {
      const key = String(groupValue || "").trim();
      if (!key) continue;
      const samples = (groups as Record<string, unknown>)[key];
      if (!Array.isArray(samples) || !samples.some((sample) => String(sample || "").trim())) {
        return `请为 ${field} = ${key} 选择样本`;
      }
    }
  }
  return "";
}

function normalizeMlMode(value: unknown) {
  const mode = String(value || "profile").trim().toLowerCase().replaceAll("-", "_").replaceAll("+", "_");
  if (["vj", "vj_usage", "usage"].includes(mode)) return "vj";
  if (["profile_vj", "profile_usage", "profile_vj_usage"].includes(mode)) return "profile_vj";
  return "profile";
}

function validateCacheInputs(module: string, payload: Record<string, unknown>) {
  if (module === "ml-analysis" && payload.ml_inspect_ok === false) {
    return "请完成机器学习的标签、样本与候选特征检查";
  }
  const hasArtifact = Boolean(String(payload.upstream_artifact_id || "").trim());
  if (module === "ml-analysis" && normalizeMlMode(payload.mode) !== "profile"
      && !hasArtifact && !String(payload.usage_path || "").trim()) {
    return "请选择 V/J 基因使用特征来源";
  }

  if (module === "umap" && payload.analysis_mode === "unified") {
    const configurations = Array.isArray(payload.configurations) ? payload.configurations : [];
    const needsVj = configurations.some((value) => String(value).split("+").includes("vj"));
    if (needsVj && !hasArtifact && !String(payload.vj_usage_path || "").trim()) return "请选择 V/J 使用结果，或在本批次中先运行生成该结果的分析";
  }
  if (module === "go-kegg-enrichment" && payload.input_mode === "deg" && !hasArtifact) return "请选择来源差异表达结果";
  if (module === "volcano" && String(payload.input_mode || "") === "usage" && payload.usage_inspect_ok === false) {
    return "请选择可用 V/J 使用结果，并完成样本与分组检查";
  }
  if (module === "volcano" && String(payload.input_mode || "") === "usage" && !hasArtifact && !String(payload.data_dir || "").trim()) {
    return "请选择克隆 V/J 基因使用缓存";
  }
  if (module === "umapin" && payload.umapin_inspect_ok === false) {
    return "请选择可用特征结果，并完成特征与样本检查";
  }
  if (module === "umapin" && !hasArtifact && !String(payload.data_path || "").trim()) {
    return "请选择克隆特征降维缓存";
  }
  if (module === "mait-nkt") {
    const source = String(payload.tra_source || "upload");
    if (source === "pep_analysis" && !hasArtifact && !String(payload.tra_path || payload.source_job_id || "").trim()) {
      return "请选择受体 α 链缓存";
    }
    if (source === "upload" && !String(payload.tra_path || "").trim()) {
      return "请选择受体 α 链数据文件";
    }
    if (payload.mait_nkt_inspect_ok === false) {
      return "特征检查失败，请先选择有效的受体 α 链数据来源";
    }
  }
  return "";
}


export type ConfigurationReviewItem = {module:string; label:string; issue:string; possibleSource?:string};

export function configurationIssue(module:string, payload:Record<string,unknown>, usesBatchResult=false):string {
  try {
    validateAnalysisPayload(module,payload,usesBatchResult);
    return "";
  } catch(error) {
    return error instanceof Error ? error.message : "请核对分析参数。";
  }
}
