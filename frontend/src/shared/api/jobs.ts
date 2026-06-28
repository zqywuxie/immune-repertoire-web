import { apiClient } from "./client";
import type { JobModule, JobSummary } from "../types/domain";

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

export function listJobs(params: { projectId?: string; status?: string; limit?: number } = {}) {
  return apiClient.get<JobListResponse>("/api/jobs", {
    project_id: params.projectId,
    status: params.status,
    limit: params.limit
  });
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
  });
}

export function getJob(jobId: string) {
  return apiClient.get<JobDetailResponse>(`/api/jobs/${jobId}`);
}

export function cancelJob(jobId: string) {
  return apiClient.post<JobDetailResponse>(`/api/jobs/${jobId}/cancel`);
}
