import type { InputQuality } from "../../features/scripthub/InputQualityPanel";
import { analysisLabel } from "../utils/analysisLabels";
import { analysisTools } from "../../features/analysis/tools";
import { apiClient } from "./client";
import { postAfterInputValidation } from "./submission";
import type { JobModule, JobOutput, JobSummary } from "../types/domain";
import type { JobResultsResponse, SubmitJobResponse } from "./jobs";

export interface ScriptHubInspectRequest {
  alignment_groups?: Array<Array<"pep" | "profile" | "transcriptome" | "deconvolution">>;
  input_types?: Array<"pep" | "profile" | "transcriptome" | "deconvolution">;
  project_id?: string;
  asset_set?: string;
  pep_paths: string[];
  profile_path?: string;
  transcriptome_path?: string;
  deconvolution_path?: string;
}

export interface ScriptHubPepPreview {
  path?: string;
  filename?: string;
  chain?: string;
  sample?: string;
}

export interface ScriptHubInspectResponse {
  inspected_input_types?: Array<"pep" | "profile" | "transcriptome" | "deconvolution">;
  input_quality?: InputQuality;
  success: boolean;
  pep_paths: string[];
  profile_path?: string;
  profile_candidates?: string[];
  profile_columns?: string[];
  registered_profile_paths?: string[];
  invalid_profile_paths?: string[];
  transcriptome_path?: string;
  deconvolution_path?: string;
  registered_transcriptome_paths?: string[];
  invalid_transcriptome_paths?: string[];
  group_fields?: string[];
  chains?: string[];
  chain_count?: number;
  sample_count?: number;
  samples?: string[];
  pep_file_count?: number;
  pep_columns?: string[];
  pep_files_preview?: ScriptHubPepPreview[];
  random_pep_preview_file?: ScriptHubPepPreview | null;
  warnings?: string[];
  message?: string;
}

export function inspectScriptHubDataSelection(payload: ScriptHubInspectRequest) {
  return apiClient.post<ScriptHubInspectResponse>("/api/script-hub/data-selection/inspect", payload);
}

export interface ScriptHubTablePreviewResponse {
  success: boolean;
  file_path: string;
  columns: string[];
  column_count: number;
  rows: unknown[][];
  row_count: number;
  message?: string;
}

export interface ScriptHubGroupValuesResponse {
  success: boolean;
  file_path: string;
  column: string;
  values: string[];
  sample_column?: string;
  samples_by_value?: Record<string, string[]>;
  sample_labels?: Record<string, string>;
  sample_ids?: Record<string, string>;
  count: number;
  message?: string;
}

export function readScriptHubTablePreview(filePath: string) {
  return apiClient.post<ScriptHubTablePreviewResponse>("/api/script-hub/read-table-preview", {
    file_path: filePath,
  });
}

export function readScriptHubGroupValues(filePath: string, column: string, batchField?: string, sampleColumn?: string) {
  return apiClient.post<ScriptHubGroupValuesResponse>("/api/script-hub/boxplot/group-values", {
    file_path: filePath,
    column,
    ...(batchField ? { batch_field: batchField } : {}),
    ...(sampleColumn ? { sample_col: sampleColumn } : {}),
  });
}

export interface PepCacheCandidate {
  id: string;
  artifact_id?: string;
  asset_set?: string;
  reason?: string;
  source_task_name?: string;
  asset_id?: string;
  job_id?: string;
  source?: string;
  source_module?: string;
  cache_type: "usage" | "vj_usage" | "umapin_table" | "tra_shared" | string;
  usage_type?: string;
  label?: string;
  path: string;
  path_summary?: string;
  file_count?: number;
  sample_count?: number;
  data_types?: string[];
  available_for?: string[];
  status?: "available" | "missing" | string;
  chains?: string[];
  group_field?: string;
  group_fields?: string[];
  created_at?: string;
}

export interface PepCacheCandidatesResponse {
  success: boolean;
  candidates: PepCacheCandidate[];
}

export function listPepCacheCandidates(projectId?: string, cacheType?: string, assetSet?: string, options?: {deduplicate?: boolean}) {
  return apiClient.get<PepCacheCandidatesResponse>(
    "/api/script-hub/pep-cache-candidates",
    { project_id: projectId, cache_type: cacheType, asset_set: assetSet },
    { skipCache: true, ...options },
  );
}

export interface ScriptHubModulesResponse {
  success: boolean;
  modules: JobModule[];
}

export interface ScriptHubTaskStatusResponse {
  success: boolean;
  job_id: string;
  task_id: string;
  module?: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
  cancel_requested?: boolean;
  progress?: number;
  stage?: string;
  detail?: string;
  error?: string;
  result?: Record<string, unknown>;
  payload?: Record<string, unknown>;
  config_json?: Record<string, unknown>;
  input_assets?: Array<Record<string, unknown>>;
  analysis_signature?: string;
  runtime?: Record<string, unknown>;
  history?: Array<Record<string, unknown>>;
  meta?: Record<string, unknown>;
  project_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

const SCRIPT_HUB_LEGACY_MODULES = new Set([
  "immune-infiltration",
  "immune-infiltration-pathway",
  "immune-infiltration-sample-pathway",
  "immune-infiltration-paired",
  "immune-infiltration-concordance",
  "immune-infiltration-consistency",
  "db-alignment",
  "boxplot",
  "profile",
  "topclone",
  "pep-analysis",
  "pgen-analysis",
  "umap",
  "volcano",
  "go-kegg-enrichment",
  "umapin",
  "ml-analysis",
  "mait-nkt",
]);

const MODULE_OUTPUT_KINDS: Record<string, string[]> = {
  "immune-infiltration-consistency": ["html","png","csv","zip"],
  "immune-infiltration-concordance": ["html","png","csv","zip"],
  "immune-infiltration-pathway": ["html","png","csv","zip"],
  "immune-infiltration-sample-pathway": ["html","png","csv","zip"],
  "immune-infiltration-paired": ["html","png","csv","zip"],
  "immune-infiltration": ["html","png","csv","zip"],
  "db-alignment": ["html", "json", "zip"],
  profile: ["html", "png", "csv", "zip"],
  boxplot: ["html", "png", "csv", "zip"],
  topclone: ["html", "png", "csv", "zip"],
  "pep-analysis": ["html", "png", "csv", "zip"],
  "pgen-analysis": ["html", "csv", "zip"],
  umap: ["html", "png", "csv", "zip"],
  volcano: ["html", "png", "csv", "zip"],
  "go-kegg-enrichment": ["html", "png", "csv", "zip"],
  umapin: ["html", "png", "csv", "zip"],
  "ml-analysis": ["html", "png", "csv", "zip"],
  "mait-nkt": ["html", "png", "csv", "zip"],
};

const MODULE_UI_ENTRIES: Record<string, string> = {
  "immune-infiltration": "ScriptHubInfiltrationConfig",
  "immune-infiltration-pathway": "ScriptHubInfiltrationConfig",
  "immune-infiltration-sample-pathway": "ScriptHubInfiltrationConfig",
  "immune-infiltration-paired": "ScriptHubInfiltrationConfig",
  "immune-infiltration-concordance": "ScriptHubInfiltrationConfig",
  "immune-infiltration-consistency": "ScriptHubInfiltrationConfig",
  "db-alignment": "ScriptHubDbAlignmentConfig",
  profile: "ScriptHubProfileConfig",
  boxplot: "ScriptHubProfileConfig",
  "pep-analysis": "ScriptHubPepAnalysisConfig",
  charts: "ChartsCombinedForm",
  "pgen-analysis": "ScriptHubPgenAnalysisConfig",
  topclone: "ScriptHubTopCloneConfig",
  umap: "ScriptHubUmapConfig",
  volcano: "ScriptHubVolcanoConfig",
  "go-kegg-enrichment": "ScriptHubGoKeggConfig",
  umapin: "ScriptHubUmapinConfig",
  "ml-analysis": "ScriptHubMlAnalysisConfig",
  "mait-nkt": "ScriptHubMaitNktConfig",
};

export function isLegacyScriptHubModule(module: string) {
  return SCRIPT_HUB_LEGACY_MODULES.has(module);
}

export function listScriptHubModules() {
  return apiClient.get<ScriptHubModulesResponse>("/api/script-hub/modules", undefined, { skipCache: true })
    .then((response) => ({
      ...response,
      modules: response.modules.map((module) => ({
        ...module,
        label: analysisLabel(module.key),
        description: module.key === "charts" ? "选择图表类型、样本和链，生成组库图表。" : module.key === "volcano" ? "比较表达矩阵或基因使用数据，查看差异结果。" : analysisTools.find(tool=>tool.module === module.key)?.description || "选择数据并配置此项分析。",
        category: "组合分析",
        execution_mode: module.key === "charts" ? "job" as const : "script-hub-legacy" as const,
        ui_entry: MODULE_UI_ENTRIES[module.key] || module.ui_entry || "LegacyScriptHubForm",
        output_kinds: module.output_kinds || MODULE_OUTPUT_KINDS[module.key] || ["html", "zip"],
      })),
    }));
}

export function inspectScriptHubModule<T = Record<string, unknown>>(module: string, payload: Record<string, unknown>) {
  return apiClient.post<T>(`/api/script-hub/${encodeURIComponent(module)}/inspect`, payload);
}

export function submitLegacyScriptHubJob({
  module,
  payload,
  projectId,
  forceRerun,
}: {
  module: string;
  payload: Record<string, unknown>;
  projectId?: string;
  forceRerun?: boolean;
}) {
  return postAfterInputValidation<SubmitJobResponse>("/api/script-hub/jobs", {
    ...normalizeLegacyScriptHubPayload(module, payload),
    module,
    project_id: projectId || payload.project_id || null,
    force_rerun: forceRerun,
  }).then((response) => ({
    ...response,
    job_id: response.job_id || response.task_id || String(response.result_id || ""),
  }));
}

export function getLegacyScriptHubTask(taskId: string) {
  return apiClient.get<ScriptHubTaskStatusResponse>(
    `/api/script-hub/task/${encodeURIComponent(taskId)}`,
    undefined,
    { skipCache: true, maxRetries: 0 },
  );
}

export function legacyScriptHubTaskToResults(task: ScriptHubTaskStatusResponse): JobResultsResponse {
  const result = task.result || {};
  const jobId = String(task.job_id || task.task_id);
  const module = String(task.module || result.module || "script-hub");
  const outputs = scriptHubResultOutputs(result);
  const job = {
    id: jobId,
    job_id: jobId,
    job_type: "script-hub",
    module,
    status: task.status,
    cancel_requested: Boolean(task.cancel_requested),
    progress: Number(task.progress || 0),
    stage: task.stage || null,
    detail: task.detail || null,
    payload: {
      ...task.payload,
      ...(task.config_json ? {config_json: task.config_json} : {}),
      ...(task.input_assets ? {input_assets: task.input_assets} : {}),
      ...(task.analysis_signature ? {analysis_signature: task.analysis_signature} : {}),
      ...(task.runtime ? {runtime: task.runtime} : {}),
      history: task.history || [],
    },
    result,
    error: task.error || null,
    project_id: task.project_id || null,
    created_at: task.created_at || null,
    updated_at: task.updated_at || null,
    started_at: task.started_at || null,
    completed_at: task.completed_at || null,
  } satisfies JobSummary;

  return {
    success: task.success,
    job,
    status: task.status,
    result,
    outputs,
    assets: [],
  };
}

function normalizeLegacyScriptHubPayload(module: string, payload: Record<string, unknown>) {
  const pepPaths = stringList(payload.pep_paths);
  const primaryPepPath = String(payload.base_path || payload.pep_data_dir || payload.pep_data_path || pepPaths[0] || "");
  const profilePath = String(payload.profile_path || payload.datapoint_path || "");
  const transcriptomePath = String(payload.transcriptome_path || payload.expression_path || "");
  const selectedChains = stringList(payload.selected_chains);
  const selectedSamples = Array.isArray(payload.selected_samples) ? stringList(payload.selected_samples) : undefined;
  const selectedGroupValues = normalizeStringListRecord(payload.selected_group_values);
  const selectedSamplesByGroup = normalizeNestedStringListRecord(payload.selected_samples_by_group);
  const groupedSelectedSamples = selectedSamplesByGroup ? flattenNestedStringListRecord(selectedSamplesByGroup) : undefined;
  const groupFields = stringList(payload.group_fields);
  const inputMode = String(payload.input_mode || "").trim();

  const normalized: Record<string, unknown> = {
    ...payload,
    pep_paths: pepPaths,
    base_path: primaryPepPath,
    pep_data_dir: primaryPepPath,
    pep_data_path: primaryPepPath,
    profile_path: profilePath || undefined,
    datapoint_path: profilePath || undefined,
    transcriptome_path: transcriptomePath || undefined,
    output_name: payload.output_name || payload._task_name || undefined,
  };

  if (selectedChains.length) normalized.selected_chains = selectedChains;
  if (groupedSelectedSamples && !["umapin", "volcano"].includes(module) && !(["pep-analysis", "pgen-analysis", "topclone", "db-alignment", "mait-nkt", "ml-analysis", "umap"].includes(module) && payload.group_sample_identity === "batch_sample")) normalized.selected_samples = groupedSelectedSamples;
  else if (selectedSamples) normalized.selected_samples = selectedSamples;
  if (selectedGroupValues) normalized.selected_group_values = selectedGroupValues;
  if (selectedSamplesByGroup) normalized.selected_samples_by_group = selectedSamplesByGroup;
  if (groupFields.length) normalized.group_fields = groupFields;

  if (module === "profile") {
    normalized.grouping_begin = payload.grouping_begin || payload.classification_begin || "";
    normalized.grouping_over = payload.grouping_over || payload.classification_over || "";
  }

  if (module === "boxplot" || module === "umap") {
    normalized.classification_begin = payload.classification_begin || payload.grouping_begin || "";
    normalized.classification_over = payload.classification_over || payload.grouping_over || "";
  }

  if (module === "pep-analysis") {
    if (!selectedChains.length) normalized.selected_chains = ["TRA", "TRB"];
    const optionalSteps = stringList(payload.optional_steps).filter((step) => ["5", "6", "7", "8", "9", "10", "11", "12"].includes(step));
    normalized.optional_steps = Array.isArray(payload.optional_steps) ? optionalSteps : ["5", "6", "7", "8"];
  }

  if (module === "pgen-analysis") {
    if (!selectedChains.length) normalized.selected_chains = ["TRA", "TRB"];
    normalized.species = payload.species || "human";
    normalized.sample_col = payload.sample_col || "sample";
  }

  if (module === "topclone" && !selectedChains.length) {
    normalized.selected_chains = ["TRA", "TRB"];
  }

  if (module === "volcano") {
    delete normalized.selected_group_values;
    delete normalized.selected_samples_by_group;
    normalized.input_mode = inputMode === "vj_usage" ? "usage" : (inputMode || (transcriptomePath ? "expression" : "usage"));
    normalized.expression_path = transcriptomePath || payload.expression_path || undefined;
    normalized.data_dir = payload.data_dir || primaryPepPath || undefined;
    if (normalized.input_mode === "expression") delete normalized.selected_samples;
  }

  if (module.startsWith("immune-infiltration")) {
    delete normalized.selected_samples;
    delete normalized.selected_group_values;
    delete normalized.selected_samples_by_group;
    if (module === "immune-infiltration-paired") {
      delete normalized.selected_infiltration_samples;
      delete normalized.selected_infiltration_groups;
    }
  }
  if (module === "go-kegg-enrichment") {
    delete normalized.selected_samples;
    delete normalized.selected_group_values;
    delete normalized.selected_samples_by_group;
    if (payload.input_mode === "deg") {
      delete normalized.expression_path;
      delete normalized.transcriptome_path;
      delete normalized.deg_directory;
      delete normalized.selected_expression_groups;
      delete normalized.selected_expression_samples;
    } else normalized.expression_path = transcriptomePath || payload.expression_path || undefined;
  }

  if (module === "umapin") {
    normalized.data_path = payload.data_path || payload.df_vj_all_path || primaryPepPath || undefined;
    delete normalized.selected_group_values;
    delete normalized.selected_samples_by_group;
  }

  if (module === "ml-analysis") {
    normalized.datapoint_path = profilePath || undefined;
    normalized.mode = payload.mode || "profile";
  }

  if (module === "mait-nkt") {
    normalized.profile_path = profilePath || undefined;
    normalized.tra_source = payload.tra_source || "upload";
    normalized.tra_path = payload.tra_path || undefined;
    normalized.source_job_id = payload.source_job_id || undefined;
  }

  if (payload.upstream_artifact_id) {
    const field = module === "volcano" ? "data_dir" : module === "umapin" ? "data_path" : module === "umap" ? "vj_usage_path" : module === "ml-analysis" ? "usage_path" : module === "mait-nkt" ? "tra_path" : null;
    if (field) delete normalized[field];
  }
  return normalized;
}

function normalizeStringListRecord(value: unknown): Record<string, string[]> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const result: Record<string, string[]> = {};
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    const list = stringList(item);
    if (list.length) result[key] = list;
  }
  return Object.keys(result).length ? result : undefined;
}

function normalizeNestedStringListRecord(value: unknown): Record<string, Record<string, string[]>> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  const result: Record<string, Record<string, string[]>> = {};
  for (const [field, groups] of Object.entries(value as Record<string, unknown>)) {
    if (!groups || typeof groups !== "object" || Array.isArray(groups)) continue;
    const nested: Record<string, string[]> = {};
    for (const [groupValue, samples] of Object.entries(groups as Record<string, unknown>)) {
      if (Array.isArray(samples)) nested[groupValue] = stringList(samples);
    }
    if (Object.keys(nested).length) result[field] = nested;
  }
  return Object.keys(result).length ? result : undefined;
}

function flattenNestedStringListRecord(value: Record<string, Record<string, string[]>>) {
  return Array.from(new Set(
    Object.values(value)
      .flatMap((groups) => Object.values(groups).flatMap((samples) => samples))
      .map((item) => String(item || "").trim())
      .filter(Boolean),
  ));
}

function scriptHubResultOutputs(result: Record<string, unknown>): JobOutput[] {
  type ExtendedJobOutput = JobOutput & {
    module?: string;
    category?: string;
    download_url?: string | null;
  };
  const outputs: ExtendedJobOutput[] = [];
  const structuredUrls = new Set<string>();
  const add = (kind: string, url: unknown, label: string) => {
    if (typeof url === "string" && url.trim()) {
      outputs.push({ kind, url, label });
    }
  };
  const addMany = (kind: string, value: unknown, label: string) => {
    if (Array.isArray(value)) {
      value.forEach((url, index) => add(kind, url, `${label} ${index + 1}`));
    } else {
      add(kind, value, label);
    }
  };
  const addStructuredItems = (value: unknown) => {
    if (!Array.isArray(value)) return;
    value.forEach((item, index) => {
      if (!item || typeof item !== "object") return;
      const raw = item as Record<string, unknown>;
      const url = typeof raw.url === "string" ? raw.url.trim() : "";
      if (!url) return;
      structuredUrls.add(url);
      const section = String(raw.section || raw.category || "克隆分析结果").trim();
      const step = String(raw.step || "").trim();
      const groupField = String(raw.group_field || raw.group || "").trim();
      const chain = String(raw.chain || "").trim();
      const usageType = String(raw.usage_type || "").trim();
      const plotType = String(raw.plot_type || "").trim();
      const labelParts = [
        step ? `步骤 ${step}` : "",
        groupField && groupField !== "Summary" ? groupField : "",
        chain,
        usageType && usageType !== "All" ? usageType : "",
        plotType && plotType !== "plot" && plotType !== "table" ? plotType : "",
      ].filter(Boolean);
      outputs.push({
        kind: String(raw.kind || kindFromUrl(url)).toLowerCase(),
        url,
        label: String(raw.title || raw.label || labelParts.join(" · ") || `克隆分析结果 ${index + 1}`),
        module: "克隆共享分析",
        category: section,
        download_url: typeof raw.download_url === "string" ? raw.download_url : null,
      });
    });
  };

  add("html", result.viewer_url || result.report_url, "交互报告");
  add("json", result.metadata_url, "分析信息");
  add("zip", result.zip_url, "结果文件包");
  addStructuredItems(result.viewer_items);
  if (!structuredUrls.size) addMany("png", result.png_urls, "图表");
  else if (Array.isArray(result.png_urls)) {
    result.png_urls.forEach((url, index) => {
      if (typeof url === "string" && url.trim() && !structuredUrls.has(url)) {
        add("png", url, `图表 ${index + 1}`);
      }
    });
  }
  addMany("csv", result.csv_urls, "数据表");
  addMany("csv", result.shared_matrix_urls, "共享矩阵");
  addMany("csv", result.usage_urls, "基因使用数据表");
  addMany("csv", result.detail_urls, "明细表");

  return outputs.filter((output, index, arr) => (
    arr.findIndex((candidate) => candidate.url === output.url && candidate.kind === output.kind) === index
  ));
}

function kindFromUrl(url: string): string {
  const lower = url.toLowerCase().split("?")[0];
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".svg") || lower.endsWith(".webp")) return "image";
  if (lower.endsWith(".csv") || lower.endsWith(".tsv") || lower.endsWith(".xlsx")) return "csv";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".zip")) return "zip";
  if (lower.endsWith(".pdf")) return "pdf";
  return "data";
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item || "").trim()).filter(Boolean)
    : [];
}


export function submitAnalysisBatch(projectId: string, assetSet: string, taskName: string, items: Array<{module: string; payload: Record<string, unknown>; upstream_from?: number; depends_on?: number[]}>) {
  return postAfterInputValidation<SubmitJobResponse>("/api/script-hub/batches", {
    project_id: projectId, asset_set: assetSet, task_name: taskName,
    items: items.map(item => ({...item, module: item.module, payload: isLegacyScriptHubModule(item.module) ? normalizeLegacyScriptHubPayload(item.module, item.payload) : item.payload})),
  });
}
