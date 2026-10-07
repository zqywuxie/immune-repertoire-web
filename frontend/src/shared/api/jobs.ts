import { apiClient } from "./client";
import { postAfterInputValidation } from "./submission";
import type { JobModule, JobOutput, JobSummary, ProjectAsset } from "../types/domain";

export interface JobListResponse {
  success: boolean;
  jobs: JobSummary[];
  total?: number;
  has_more?: boolean;
  counts?: Record<string, number>;
  modules?: string[];
}

export interface JobDetailResponse {
  success: boolean;
  job: JobSummary;
}

export interface JobModulesResponse {
  success: boolean;
  modules: JobModule[];
}

export interface SubmitJobPayload {
  module: string;
  payload: Record<string, unknown>;
  projectId?: string;
  forceRerun?: boolean;
}

export interface SubmitJobResponse {
  success: boolean;
  job_id: string;
  task_id?: string;
  status?: string;
  status_url?: string;
  reused_result?: boolean;
  result_id?: string;
  result?: Record<string, unknown>;
}

export interface JobResultsResponse {
  success: boolean;
  job: JobSummary;
  status: string;
  result: Record<string, unknown>;
  outputs: JobOutput[];
  assets: Array<ProjectAsset & { preview_url?: string; download_url?: string }>;
}

export interface JobEventResponse {
  success: boolean;
  job: JobSummary;
  status: string;
}

export interface DeleteJobResponse {
  success: boolean;
  deleted_job?: JobSummary;
  deleted_children?: number;
  deleted_assets?: string[];
  deleted_paths?: string[];
  skipped_paths?: string[];
  errors?: string[];
}

export interface BulkDeleteJobsResponse {
  success: boolean;
  results: Array<DeleteJobResponse & { job_id: string; error?: string }>;
}

export function listJobs(params: { projectId?: string; status?: string; limit?: number; offset?: number; module?: string; search?: string; assetSet?: string } = {}) {
  return apiClient.get<JobListResponse>("/api/jobs", {
    project_id: params.projectId,
    status: params.status,
    limit: params.limit, offset: params.offset, module: params.module, q: params.search, asset_set: params.assetSet
  }, { skipCache: true });
}

export function listJobModules() {
  return apiClient.get<JobModulesResponse>("/api/jobs/modules");
}

export function submitJob({ module, payload, projectId, forceRerun }: SubmitJobPayload) {
  return postAfterInputValidation<SubmitJobResponse>("/api/jobs", {
    module,
    payload,
    project_id: projectId,
    force_rerun: forceRerun
  }).then((response) => {
    apiClient.invalidatePath("/api/jobs");
    return response;
  });
}

export function getJob(jobId: string, options: { forceFresh?: boolean } = {}) {
  return apiClient.get<JobDetailResponse>(`/api/jobs/${jobId}`, undefined, { skipCache: true, deduplicate: !options.forceFresh });
}

export function getJobResults(jobId: string, options: { forceFresh?: boolean } = {}) {
  return apiClient.get<JobResultsResponse>(`/api/jobs/${jobId}/results`, undefined, { skipCache: true, deduplicate: !options.forceFresh });
}

export function jobEventsUrl(jobId: string) {
  return `/api/jobs/${jobId}/events`;
}

export function retryJob(jobId: string) {
  return apiClient.post<{success: boolean; job_id: string}>(`/api/jobs/${jobId}/retry`).then((response) => {
    apiClient.invalidatePath("/api/jobs");
    return response;
  });
}

export function cancelJob(jobId: string) {
  return apiClient.post<JobDetailResponse>(`/api/jobs/${jobId}/cancel`).then((response) => {
    apiClient.invalidatePath("/api/jobs");
    return response;
  });
}

export function deleteJob(jobId: string, params: { deleteResults?: boolean } = {}) {
  const query = params.deleteResults ? "?delete_results=1" : "";
  return apiClient.delete<DeleteJobResponse>(`/api/jobs/${jobId}${query}`).then((response) => {
    apiClient.invalidatePath("/api/jobs");
    return response;
  });
}

export function bulkDeleteJobs(jobIds: string[], params: { deleteResults?: boolean } = {}) {
  return apiClient.post<BulkDeleteJobsResponse>("/api/jobs/bulk-delete", {
    job_ids: jobIds,
    delete_results: Boolean(params.deleteResults),
  }).then((response) => {
    apiClient.invalidatePath("/api/jobs");
    return response;
  });
}


export async function downloadResultArchive(items: Array<{ job_id: string; url: string }>) {
  if (!items.length) throw new Error("请选择需要下载的结果文件。");
  // A native form download lets the browser stream the response to disk instead
  // of materializing a potentially multi-gigabyte ZIP in a JavaScript Blob.
  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/api/jobs/results/archive";
  form.style.display = "none";
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = "items";
  input.value = JSON.stringify(items);
  form.appendChild(input);
  document.body.appendChild(form);
  form.submit();
  form.remove();
}
