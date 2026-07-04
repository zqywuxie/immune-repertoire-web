import { apiClient } from "./client";
import type { JobModule, JobOutput, JobSummary } from "../types/domain";
import type { JobResultsResponse, SubmitJobResponse } from "./jobs";

export interface ScriptHubInspectRequest {
  project_id?: string;
  pep_paths: string[];
  profile_path?: string;
  transcriptome_path?: string;
}

export interface ScriptHubPepPreview {
  path?: string;
  filename?: string;
  chain?: string;
  sample?: string;
}

export interface ScriptHubInspectResponse {
  success: boolean;
  pep_paths: string[];
  profile_path?: string;
  profile_candidates?: string[];
  profile_columns?: string[];
  registered_profile_paths?: string[];
  invalid_profile_paths?: string[];
  transcriptome_path?: string;
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
  count: number;
  message?: string;
}

export function readScriptHubTablePreview(filePath: string) {
  return apiClient.post<ScriptHubTablePreviewResponse>("/api/script-hub/read-table-preview", {
    file_path: filePath,
  });
}

export function readScriptHubGroupValues(filePath: string, column: string) {
  return apiClient.post<ScriptHubGroupValuesResponse>("/api/script-hub/boxplot/group-values", {
    file_path: filePath,
    column,
  });
}

export interface PepCacheCandidate {
  id: string;
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

export function listPepCacheCandidates(projectId?: string, cacheType?: string) {
  return apiClient.get<PepCacheCandidatesResponse>(
    "/api/script-hub/pep-cache-candidates",
    { project_id: projectId, cache_type: cacheType },
    { skipCache: true },
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
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress?: number;
  stage?: string;
  detail?: string;
  error?: string;
  result?: Record<string, unknown>;
  history?: Array<Record<string, unknown>>;
  meta?: Record<string, unknown>;
  project_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

const SCRIPT_HUB_LEGACY_MODULES = new Set([
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
        category: "Script Hub",
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
  return apiClient.post<SubmitJobResponse>("/api/script-hub/jobs", {
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
    progress: Number(task.progress || 0),
    stage: task.stage || null,
    detail: task.detail || null,
    payload: {},
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
  if (groupedSelectedSamples) normalized.selected_samples = groupedSelectedSamples;
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
    const optionalSteps = stringList(payload.optional_steps).filter((step) => ["5", "6", "7", "8"].includes(step));
    normalized.optional_steps = optionalSteps.length ? optionalSteps : ["5", "6", "7", "8"];
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
    normalized.input_mode = inputMode === "vj_usage" ? "usage" : (inputMode || (transcriptomePath ? "expression" : "usage"));
    normalized.expression_path = transcriptomePath || payload.expression_path || undefined;
    normalized.data_dir = payload.data_dir || primaryPepPath || undefined;
  }

  if (module === "go-kegg-enrichment") {
    normalized.expression_path = transcriptomePath || payload.expression_path || undefined;
  }

  if (module === "umapin") {
    normalized.data_path = payload.data_path || payload.df_vj_all_path || primaryPepPath || undefined;
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
      const section = String(raw.section || raw.category || "PEP Result").trim();
      const step = String(raw.step || "").trim();
      const groupField = String(raw.group_field || raw.group || "").trim();
      const chain = String(raw.chain || "").trim();
      const usageType = String(raw.usage_type || "").trim();
      const plotType = String(raw.plot_type || "").trim();
      const labelParts = [
        step ? `Step ${step}` : "",
        groupField && groupField !== "Summary" ? groupField : "",
        chain,
        usageType && usageType !== "All" ? usageType : "",
        plotType && plotType !== "plot" && plotType !== "table" ? plotType : "",
      ].filter(Boolean);
      outputs.push({
        kind: String(raw.kind || kindFromUrl(url)).toLowerCase(),
        url,
        label: String(raw.title || raw.label || labelParts.join(" · ") || `PEP Result ${index + 1}`),
        module: "Pep Analysis",
        category: section,
        download_url: typeof raw.download_url === "string" ? raw.download_url : null,
      });
    });
  };

  add("html", result.viewer_url || result.report_url, "Interactive Report");
  add("json", result.metadata_url, "Metadata");
  add("zip", result.zip_url, "Result Bundle");
  addStructuredItems(result.viewer_items);
  if (!structuredUrls.size) addMany("png", result.png_urls, "Figure");
  else if (Array.isArray(result.png_urls)) {
    result.png_urls.forEach((url, index) => {
      if (typeof url === "string" && url.trim() && !structuredUrls.has(url)) {
        add("png", url, `Figure ${index + 1}`);
      }
    });
  }
  addMany("csv", result.csv_urls, "CSV");
  addMany("csv", result.shared_matrix_urls, "Shared Matrix");
  addMany("csv", result.usage_urls, "Usage Table");
  addMany("csv", result.detail_urls, "Detail Table");

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
