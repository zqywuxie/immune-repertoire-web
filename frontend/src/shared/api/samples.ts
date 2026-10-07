import { apiClient } from "./client";
import type { components } from "./generated/schema";

/** Fields returned by GET /api/projects/samples */
export interface SampleRecord {
  id: string;
  project_id: string;
  project_name: string | null;
  sample_id: string | null;
  sample_name: string;
  sequence_id: string | null;
  spices: string | null;
  institution: string | null;
  chain_flag: string | null;
  is_healthy: string | null;
  illness: string | null;
  is_pe: string | null;
  contain_method: string | null;
  iso_tag: string | null;
  extra_metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface SampleListResponse {
  samples: SampleRecord[];
  pagination?: import("../components/Pagination").PaginationInfo;
}

export interface SampleFieldOptionsResponse {
  fields: Record<string, string[]>;
}

export interface SampleUpdatePayload {
  expected_values?: Record<string, string | null>;
  sample_name?: string;
  sequence_id?: string;
  spices?: string;
  institution?: string;
  chain_flag?: string;
  is_healthy?: string;
  illness?: string;
  is_pe?: string;
  contain_method?: string;
  iso_tag?: string;
  extra_metadata?: Record<string, unknown>;
}

export interface ListSamplesParams {
  q?: string;
  page?: number;
  page_size?: number;
  project_id?: string;
  asset_set?: string;
  sample_id?: string;
  input_sample_id?: string;
  sample_name?: string;
  project_name?: string;
  institution?: string;
  sequence_id?: string;
  contain_method?: string;
  iso_tag?: string;
  spices?: string;
  chain_flag?: string;
  is_healthy?: string;
  illness?: string;
  is_pe?: string;
}

/** List samples with optional filters. */
export function listSamples(params: ListSamplesParams = {}) {
  return apiClient.get<SampleListResponse>("/api/samples", params as Record<string, string | number | undefined>);
}

/** Update a single sample record. */
export function updateSample(id: string, data: SampleUpdatePayload) {
  return apiClient.put<SampleRecord>(`/api/samples/${id}`, data);
}

/** Fetch distinct field values for a given field name. */
export function getSampleFieldOptions(projectId: string, field: string, assetSet = "", options: {view?: "filters"} = {}) {
  return apiClient.get<SampleFieldOptionsResponse>("/api/samples/field-options", {
    project_id: projectId,
    asset_set: assetSet,
    field,
    view: options.view,
  });
}

export type SampleFieldCatalogResponse = components["schemas"]["SampleFieldCatalogResponse"];
export type SampleIdentifierField = SampleFieldCatalogResponse["field"];
export function getSampleFieldCandidates(projectId: string, assetSet: string, field: SampleIdentifierField, search: string, page: number) {
  return apiClient.get<SampleFieldCatalogResponse>("/api/samples/field-options", {
    project_id: projectId, asset_set: assetSet, field, view: "catalog", q: search, page, page_size: 20,
  }, {skipCache: true, deduplicate: false});
}

/** Build the CSV export URL (returns a URL string, not a data response). */
export function exportSamplesUrl(params: ListSamplesParams & {format?: "csv" | "xlsx"; columns?: "business" | "technical" | "legacy"} = {}): string {
  const base = import.meta.env.VITE_API_BASE_URL || "";
  const url = new URL(`${base}/api/samples/export`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (key !== "page" && key !== "page_size" && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url.toString();
}

export async function downloadSamples(params: ListSamplesParams, format: "csv" | "xlsx", includeSource: boolean, signal?: AbortSignal, recordIds?: string[]) {
  if (recordIds && (!recordIds.length || recordIds.length > 5000)) throw new Error("请选择 1 至 5000 条登记后导出。");
  const columns = includeSource ? "technical" : "business";
  const response = recordIds
    ? await fetch(exportSamplesUrl(), {method:"POST", credentials:"include", signal, headers:{"Content-Type":"application/json"},
        body:JSON.stringify({filters:Object.fromEntries(Object.entries(params).filter(([key,value])=>key!=="page" && key!=="page_size" && value!==undefined)), record_ids:recordIds, format, columns})})
    : await fetch(exportSamplesUrl({...params, format, columns}), {credentials:"include", signal});
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(typeof payload.message === "string" ? payload.message : "导出未完成，请重试。");
  }
  if (!response.headers.get("Content-Type")?.includes(format === "csv" ? "text/csv" : "spreadsheetml")) {
    throw new Error("未收到数据文件，请检查登录状态后重试。");
  }
  return {blob: await response.blob(), count: response.headers.get("X-Export-Count")};
}
