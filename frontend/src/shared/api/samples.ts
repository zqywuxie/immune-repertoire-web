import { apiClient } from "./client";

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
}

export interface SampleFieldOptionsResponse {
  fields: Array<{ value: string; label?: string }>;
}

export interface SampleUpdatePayload {
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
  project_id?: string;
  sample_id?: string;
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
  return apiClient.get<SampleListResponse>("/api/samples", params as Record<string, string | undefined>);
}

/** Update a single sample record. */
export function updateSample(id: string, data: SampleUpdatePayload) {
  return apiClient.put<SampleRecord>(`/api/samples/${id}`, data);
}

/** Fetch distinct field values for a given field name. */
export function getSampleFieldOptions(projectId: string, field: string) {
  return apiClient.get<SampleFieldOptionsResponse>("/api/samples/field-options", {
    project_id: projectId,
    field,
  });
}

/** Build the CSV export URL (returns a URL string, not a data response). */
export function exportSamplesUrl(params: ListSamplesParams = {}): string {
  const base = import.meta.env.VITE_API_BASE_URL || "";
  const url = new URL(`${base}/api/samples/export`, window.location.origin);
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  return url.pathname + url.search;
}
