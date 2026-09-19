import { apiClient } from "./client";
import type { JobModule, JobOutput, JobSummary, ProjectAsset } from "../types/domain";

export interface JobListResponse {
  success: boolean;
  jobs: JobSummary[];
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

export function listJobs(params: { projectId?: string; status?: string; limit?: number } = {}) {
  return apiClient.get<JobListResponse>("/api/jobs", {
    project_id: params.projectId,
    status: params.status,
    limit: params.limit
  }, { skipCache: true });
}

export function listJobModules() {
  return apiClient.get<JobModulesResponse>("/api/jobs/modules");
}

export function submitJob({ module, payload, projectId, forceRerun }: SubmitJobPayload) {
  return apiClient.post<SubmitJobResponse>("/api/jobs", {
    module,
    payload,
    project_id: projectId,
    force_rerun: forceRerun
  }).then((response) => {
    apiClient.invalidatePath("/api/jobs");
    return response;
  });
}

export function getJob(jobId: string) {
  return apiClient.get<JobDetailResponse>(`/api/jobs/${jobId}`, undefined, { skipCache: true });
}

export function getJobResults(jobId: string) {
  return apiClient.get<JobResultsResponse>(`/api/jobs/${jobId}/results`, undefined, { skipCache: true });
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
  const response = await fetch("/api/jobs/results/archive", {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ items }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.message || "结果打包失败，请重试。");
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url; link.download = "分析结果.zip";
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
