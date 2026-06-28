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
  pagination?: Pagination;
}

export interface ResultListResponse {
  success: boolean;
  results: ProjectAsset[];
  pagination?: Pagination;
}

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export function listProjects() {
  return apiClient.get<ProjectListResponse>("/api/projects");
}

export function getProject(projectId: string) {
  return apiClient.get<ProjectDetail>(`/api/projects/${projectId}`);
}

export function listProjectAssets(projectId: string, options: { assetType?: string; page?: number; pageSize?: number } = {}) {
  return apiClient.get<AssetListResponse>(`/api/projects/${projectId}/assets`, {
    asset_type: options.assetType,
    page: options.page,
    page_size: options.pageSize
  });
}

export function listProjectResults(projectId: string, options: { analysisType?: string; page?: number; pageSize?: number } = {}) {
  return apiClient.get<ResultListResponse>(`/api/projects/${projectId}/results`, {
    analysis_type: options.analysisType,
    page: options.page,
    page_size: options.pageSize
  });
}
