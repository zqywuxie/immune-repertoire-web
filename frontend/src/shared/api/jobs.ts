import { apiClient } from "./client";
import type { JobSummary } from "../types/domain";

export interface JobListResponse {
  success: boolean;
  jobs: JobSummary[];
}

export interface JobDetailResponse {
  success: boolean;
  job: JobSummary;
}

export function listJobs(params: { projectId?: string; status?: string; limit?: number } = {}) {
  return apiClient.get<JobListResponse>("/api/jobs", {
    project_id: params.projectId,
    status: params.status,
    limit: params.limit
  });
}

export function getJob(jobId: string) {
  return apiClient.get<JobDetailResponse>(`/api/jobs/${jobId}`);
}

export function cancelJob(jobId: string) {
  return apiClient.post<JobDetailResponse>(`/api/jobs/${jobId}/cancel`);
}
