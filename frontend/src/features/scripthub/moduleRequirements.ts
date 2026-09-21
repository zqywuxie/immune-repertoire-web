import type { JobModule } from "../../shared/types/domain";

export type RequiredAsset = "pep" | "profile" | "transcriptome" | "deconvolution";

export type SourceAvailabilityContext = {
  pepPaths?: string[];
  profilePath?: string;
  transcriptomePath?: string;
  deconvolutionPath?: string;
  artifactModules?: string[];
};

type RequirementRule = {
  all?: RequiredAsset[];
  any?: RequiredAsset[];
};

const ASSET_LABELS: Record<RequiredAsset, string> = {
  deconvolution: "免疫浸润结果",
  pep: "克隆序列表",
  profile: "样本指标表",
  transcriptome: "转录组",
};

const MODULE_REQUIREMENTS: Record<string, RequirementRule> = {
  "immune-infiltration": {all:["profile","deconvolution"]},
  "db-alignment": { all: ["pep", "profile"] },
  profile: { all: ["profile"] },
  boxplot: { all: ["profile"] },
  "pep-analysis": { all: ["pep", "profile"] },
  charts: { all: ["pep"] },
  "pgen-analysis": { all: ["pep", "profile"] },
  topclone: { all: ["pep", "profile"] },
  umap: { all: ["profile"] },
  volcano: { any: ["transcriptome", "pep"] },
  "go-kegg-enrichment": { all: ["transcriptome"] },
  umapin: { all: ["pep"] },
  "ml-analysis": { all: ["profile"] },
  "mait-nkt": { all: ["pep"] },
};

export function hasAnySelectableModule(
  modules: JobModule[],
  sourceContext?: SourceAvailabilityContext,
) {
  return modules.some((module) => getModuleAvailability(module, sourceContext).selectable);
}

export function getModuleRequiredAssets(moduleKey: string): RequiredAsset[] {
  const rule = MODULE_REQUIREMENTS[moduleKey];
  return [...(rule?.all || []), ...(rule?.any || [])];
}

export function getModuleAvailability(
  module: JobModule | undefined,
  sourceContext?: SourceAvailabilityContext,
) {
  if (!module) {
    return { selectable: false, reason: "未找到此分析模块。", missing: [] as RequiredAsset[] };
  }
  if (module.status === "unavailable") {
    return { selectable: false, reason: module.unavailable_reason || "此模块当前不可用。", missing: [] as RequiredAsset[] };
  }

  if (sourceContext?.artifactModules?.includes(module.key)) return {selectable:true,reason:"",missing:[] as RequiredAsset[]};
  const rule = MODULE_REQUIREMENTS[module.key];
  if (!rule) {
    return { selectable: true, reason: "", missing: [] as RequiredAsset[] };
  }

  const available = new Set<RequiredAsset>();
  if ((sourceContext?.pepPaths || []).length > 0) available.add("pep");
  if (sourceContext?.profilePath) available.add("profile");
  if (sourceContext?.deconvolutionPath) available.add("deconvolution");
  if (sourceContext?.transcriptomePath) available.add("transcriptome");

  const missingAll = (rule.all || []).filter((item) => !available.has(item));
  const hasAny = !rule.any?.length || rule.any.some((item) => available.has(item));
  const missingAny = hasAny ? [] : rule.any || [];
  const missing = uniqueRequirements([...missingAll, ...missingAny]);

  if (missing.length === 0) {
    return { selectable: true, reason: "", missing };
  }

  const allText = missingAll.length ? missingAll.map(assetLabel).join(" + ") : "";
  const anyText = missingAny.length ? missingAny.map(assetLabel).join(" 或 ") : "";
  const reasonParts = [allText, anyText].filter(Boolean);
  return {
    selectable: false,
    reason: `当前数据集需要补充 ${reasonParts.join(" 和 ")} 数据。`,
    missing,
  };
}

export function isModuleSelectable(module: JobModule | undefined, sourceContext?: SourceAvailabilityContext) {
  return getModuleAvailability(module, sourceContext).selectable;
}

export function assetLabel(asset: RequiredAsset): string {
  return ASSET_LABELS[asset];
}

function uniqueRequirements(value: RequiredAsset[]) {
  return Array.from(new Set(value));
}
