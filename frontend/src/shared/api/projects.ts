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

export interface ProjectAssetStatus {
  has_profile?: boolean;
  has_datapoint?: boolean;
  has_pep?: boolean;
  has_sample_summary?: boolean;
  has_group_spec?: boolean;
  has_results?: boolean;
  asset_set_count?: number;
}

export interface AssetListResponse {
  assets: ProjectAsset[];
  pagination?: Pagination;
}

export interface AssetUploadResponse {
  assets: ProjectAsset[];
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

export function uploadProjectAssets(
  projectId: string,
  options: {
    assetType: string;
    files: File[];
    replaceExisting?: boolean;
    assetSet?: string;
  }
) {
  const formData = new FormData();
  formData.set("asset_type", options.assetType);
  formData.set("replace_existing", options.replaceExisting ? "true" : "false");
  if (options.assetSet) formData.set("asset_set", options.assetSet);
  formData.set("relative_paths", JSON.stringify(options.files.map((file) => file.webkitRelativePath || file.name)));
  options.files.forEach((file) => formData.append("files", file, file.name));

  return fetch(`/api/projects/${projectId}/assets`, {
    method: "POST",
    credentials: "include",
    body: formData
  }).then(async (response) => {
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload?.message || response.statusText);
    }
    return payload as AssetUploadResponse;
  });
}

export function assetPreviewUrl(assetId: string) {
  return `/api/assets/${assetId}/preview`;
}

export function assetDownloadUrl(assetId: string) {
  return `/api/assets/${assetId}/download`;
}

export function projectAssetPreviewUrl(projectId: string, assetId: string) {
  return `/api/projects/${projectId}/assets/${assetId}/preview`;
}

export function projectAssetDownloadUrl(projectId: string, assetId: string) {
  return `/api/projects/${projectId}/assets/${assetId}/download`;
}

export function listProjectResults(projectId: string, options: { analysisType?: string; page?: number; pageSize?: number } = {}) {
  return apiClient.get<ResultListResponse>(`/api/projects/${projectId}/results`, {
    analysis_type: options.analysisType,
    page: options.page,
    page_size: options.pageSize
  });
}

export function projectExportUrl(
  projectId: string,
  options: {
    includeAssets?: boolean;
    includeResults?: boolean;
    includeGroupSpecs?: boolean;
    includeManifest?: boolean;
  } = {}
) {
  const params = new URLSearchParams();
  params.set("include_assets", String(options.includeAssets ?? true));
  params.set("include_results", String(options.includeResults ?? true));
  params.set("include_group_specs", String(options.includeGroupSpecs ?? true));
  params.set("include_manifest", String(options.includeManifest ?? true));
  return `/api/projects/${projectId}/export?${params.toString()}`;
}
