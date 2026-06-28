import { apiClient } from "./client";
import type { ProjectAsset, ProjectSummary } from "../types/domain";

export interface ProjectListResponse {
  projects: ProjectSummary[];
}

export interface ProjectDetail extends ProjectSummary {
  assets: ProjectAsset[];
  group_specs?: unknown[];
  samples_preview?: unknown[];
}

export interface AssetListResponse {
  assets: ProjectAsset[];
}

export interface ResultListResponse {
  success: boolean;
  results: ProjectAsset[];
}

export function listProjects() {
  return apiClient.get<ProjectListResponse>("/api/projects");
}

export function getProject(projectId: string) {
  return apiClient.get<ProjectDetail>(`/api/projects/${projectId}`);
}

export function listProjectAssets(projectId: string, assetType?: string) {
  return apiClient.get<AssetListResponse>(`/api/projects/${projectId}/assets`, {
    asset_type: assetType
  });
}

export function listProjectResults(projectId: string, analysisType?: string) {
  return apiClient.get<ResultListResponse>(`/api/projects/${projectId}/results`, {
    analysis_type: analysisType
  });
}
