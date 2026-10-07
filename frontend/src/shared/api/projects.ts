import type { components } from "./generated/schema";
import { apiClient, ApiError } from "./client";
import { UploadResponseUnknownError, confirmInterruptedUpload, getSavedUploadOperation } from "./uploadOperations";
import type { ProjectAsset, ProjectSummary } from "../types/domain";

export interface ProjectListResponse {
  projects: ProjectSummary[];
  pagination: Pagination;
}

export interface ProjectListParams {
  page?: number;
  pageSize?: number;
  search?: string;
  status?: string;
  sort?: "created_desc" | "updated_desc" | "name_asc" | "name_desc";
  name?: string;
  institution?: string;
  cooperationLevel?: string;
  view?: "summary" | "selector";
}

export type ProjectStatistics = components["schemas"]["ProjectStatistics"];

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
  has_transcriptome?: boolean;
  has_deconvolution?: boolean;
  asset_set_count?: number;
}

export interface AssetListResponse {
  assets: ProjectAsset[];
  pagination?: Pagination;
}

export interface AssetUploadResponse {
  assets: ProjectAsset[];
}

export interface ResultFacets {
  datasets: Array<{name:string;count:number}>;
  analysis_types: Array<{name:string;count:number}>;
  unscoped_count: number;
}
export interface ResultListResponse {
  facets?: ResultFacets;
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

export function listProjects(params: ProjectListParams = {}) {
  return apiClient.get<ProjectListResponse>("/api/projects", {
    page: params.page ?? 1, page_size: params.pageSize ?? 24,
    q: params.search, status: params.status, sort: params.sort,
    name: params.name, institution: params.institution,
    cooperation_level: params.cooperationLevel, view: params.view,
  });
}

export function getProjectStatistics() {
  return apiClient.get<ProjectStatistics>("/api/projects/statistics");
}

export function getProject(projectId: string, options: { summaryOnly?: boolean; includeGroupSpecs?: boolean } = {}) {
  return apiClient.get<ProjectDetail>(`/api/projects/${projectId}`, { summary_only: options.summaryOnly, include_group_specs: options.includeGroupSpecs });
}

export interface DatasetSummary {
  id?: string;
  display_name?: string;
  description?: string;
  source?: string;
  batch?: string;
  archived?: boolean;
  revision?: number;
  updated_at?: string;
  name: string;
  input_count: number;
  kinds: Record<string, { count: number; statuses: Record<string, number>; sample_min: number | null; sample_max: number | null }>;
}
export function listProjectDatasets(projectId: string, options: {skipCache?:boolean} = {}) {
  return apiClient.get<{ datasets: DatasetSummary[] }>(`/api/projects/${projectId}/datasets`, undefined, options);
}

export type DatasetUpdatePayload = {asset_set:string;expected_revision:number;display_name?:string;description?:string;source?:string;batch?:string;archived?:boolean};
export function updateProjectDataset(projectId:string,payload:DatasetUpdatePayload) {
  return apiClient.put<{dataset:Omit<DatasetSummary,"input_count"|"kinds">}>(`/api/projects/${projectId}/datasets`,payload).then(response=>{
    apiClient.invalidatePath(`/api/projects/${projectId}`);
    return response;
  });
}

export type InputSelectionResponse = components["schemas"]["ProjectInputSelection"];
export function getProjectInputSelection(projectId:string, dataset:string) {
  return apiClient.get<InputSelectionResponse>(`/api/projects/${projectId}/input-selection`,{asset_set:dataset},{skipCache:true});
}

export type InputResolutionResponse = components["schemas"]["ProjectInputResolution"];
export const INPUT_RESOLUTION_BATCH_SIZE = 500;
export function resolveProjectInputSelection(projectId: string, dataset: string, assetIds: string[]) {
  return apiClient.post<InputResolutionResponse>(`/api/projects/${projectId}/input-selection/resolve`, {asset_set: dataset, asset_ids: assetIds}, undefined, {deduplicate: true});
}

export async function listProjectAssets(projectId: string, options: {
  assetType?: string; page?: number; pageSize?: number; inputsOnly?: boolean; allPages?: boolean; view?: "selector";
  assetSet?: string; search?: string; validationStatus?: string; includeSuperseded?: boolean; skipCache?: boolean; sort?: string;
} = {}): Promise<AssetListResponse> {
  const load = (page: number) => apiClient.get<AssetListResponse>(`/api/projects/${projectId}/assets`, {
    view: options.view, asset_type: options.assetType, inputs_only: options.inputsOnly, asset_set: options.assetSet,
    q: options.search, validation_status: options.validationStatus, include_superseded: options.includeSuperseded, sort: options.sort,
    page, page_size: options.pageSize || (options.allPages ? 200 : 50),
  }, { skipCache: options.skipCache });
  const first = await load(options.allPages ? 1 : options.page || 1);
  if (!options.allPages || !first.pagination || first.pagination.total_pages <= 1) return first;
  const assets = [...first.assets];
  for (let page = 2; page <= first.pagination.total_pages; page++) assets.push(...(await load(page)).assets);
  return { ...first, assets };
}

export interface ExpectedInputVersion { id: string; content_version: string }
export interface UploadImpactItem { asset_type: string; asset_set: string; name: string; directory: boolean }
export interface UploadImpact extends UploadImpactItem {
  expected_versions: ExpectedInputVersion[];
  assets: { id: string; original_name: string; uploaded_at: string | null; content_version: string }[];
  pagination: Pagination;
}
export function uploadImpactKey(item: UploadImpactItem) {
  return JSON.stringify([item.asset_set.trim(), item.asset_type, item.name.trim(), item.directory]);
}
export async function previewUploadImpact(projectId: string, items: UploadImpactItem[], options: {page?: number; pageSize?: number} = {}) {
  const impacts: UploadImpact[] = [];
  for (let offset = 0; offset < items.length; offset += 200) {
    const params = new URLSearchParams({page: String(options.page || 1), page_size: String(options.pageSize || 20)});
    const result = await apiClient.post<{impacts: UploadImpact[]}>(`/api/projects/${projectId}/upload-impact?${params}`, {items: items.slice(offset, offset + 200)});
    impacts.push(...result.impacts);
  }
  return {impacts};
}
export function isUploadImpactConflict(error: unknown) {
  return error instanceof ApiError && error.status === 409
    && (error.payload as {error_code?: string} | null)?.error_code === "UPLOAD_IMPACT_CHANGED";
}

export async function uploadProjectAssets(
  projectId: string,
  options: {
    assetType: string;
    files: File[];
    replaceExisting?: boolean;
    expectedVersions?: ExpectedInputVersion[];
    assetSet?: string;
    onProgress?: (percentage: number) => void;
    onStatusCheck?: () => void;
    operationId?: string;
    retry?: boolean;
    signal?: AbortSignal;
  }
) {
  const verifySaved = (assets: ProjectAsset[]) => {
    const receipt = assets[0]?.metadata?.upload_operation as { manifest?: Record<string, any> } | undefined;
    const manifest = receipt?.manifest;
    if (manifest && (manifest.kind !== "files" || manifest.asset_type !== options.assetType
      || manifest.asset_set !== (options.assetSet?.trim() || "Set1")
      || manifest.replace_existing !== !!options.replaceExisting
      || manifest.files.length !== options.files.length
      || manifest.files.some((item: { name: string; relative_path: string }, index: number) =>
        item.name !== options.files[index].name.trim() || item.relative_path !== (options.files[index].webkitRelativePath || options.files[index].name)))) {
      throw new Error("本次文件已按原选择保存，当前选项已改变。请查看原数据集；如需新上传，请重新选择文件。");
    }
    return { assets };
  };
  if (options.operationId && options.retry) {
    options.onStatusCheck?.();
    let saved;
    try { saved = await getSavedUploadOperation(projectId, options.operationId); }
    catch { /* Repeated POST uses the same database identity if lookup is unavailable. */ }
    if (saved?.saved) return verifySaved(saved.assets);
  }
  const formData = new FormData();
  formData.set("asset_type", options.assetType);
  if (options.operationId) formData.set("operation_id", options.operationId);
  formData.set("replace_existing", options.replaceExisting ? "true" : "false");
  if (options.expectedVersions !== undefined) formData.set("expected_versions", JSON.stringify(options.expectedVersions));
  if (options.assetSet) formData.set("asset_set", options.assetSet);
  formData.set("relative_paths", JSON.stringify(options.files.map((file) => file.webkitRelativePath || file.name)));
  options.files.forEach((file) => formData.append("files", file, file.name));

  const uploadUrl = `${import.meta.env.VITE_API_BASE_URL || ''}/api/projects/${projectId}/assets`;
  try {
  if (options.onProgress) {
    return await new Promise<AssetUploadResponse>((resolve, reject) => {
      const request = new XMLHttpRequest();
      const abort = () => request.abort();
      const finish = () => options.signal?.removeEventListener('abort', abort);
      request.open('POST', uploadUrl);
      request.withCredentials = true;
      request.upload.onprogress = event => { if (event.lengthComputable) options.onProgress?.(Math.round(event.loaded / event.total * 100)); };
      request.onload = () => {
        finish();
        let payload: any;
        try { payload = JSON.parse(request.responseText); } catch { reject(new UploadResponseUnknownError('服务器返回了无法读取的上传结果，正在核对保存状态。')); return; }
        if (request.status < 200 || request.status >= 300) reject(new ApiError(payload.message || payload.detail || '上传失败', request.status, payload));
        else { apiClient.invalidateCache(); resolve(payload as AssetUploadResponse); }
      };
      request.onerror = () => { finish(); reject(new UploadResponseUnknownError('上传连接中断，正在核对保存状态。')); };
      request.onabort = () => { finish(); reject(new UploadResponseUnknownError('上传已取消，正在核对服务器已接收的文件。')); };
      if (options.signal?.aborted) { finish(); reject(new Error('上传已取消')); return; }
      options.signal?.addEventListener('abort', abort, { once: true });
      request.send(formData);
    });
  }
  return await fetch(uploadUrl, {
    method: "POST",
    credentials: "include",
    body: formData, signal: options.signal,
  }).catch(() => { throw new UploadResponseUnknownError(); }).then(async (response) => {
    const payload = await response.json().catch(() => { throw new UploadResponseUnknownError(); });
    if (!response.ok) {
      throw new ApiError(payload?.message || response.statusText, response.status, payload);
    }
    apiClient.invalidateCache();
    return payload as AssetUploadResponse;
  });
  } catch (error) {
    if (options.operationId && error instanceof UploadResponseUnknownError) {
      options.onStatusCheck?.();
      return verifySaved((await confirmInterruptedUpload(projectId, options.operationId)).assets);
    }
    throw error;
  }
}

export async function registerProjectPath(projectId: string, options: {
  storagePath: string; assetSet: string; operationId: string; retry?: boolean;
  signal?: AbortSignal; onStatusCheck?: () => void;
}) {
  const verifySaved = (asset: ProjectAsset) => {
    const receipt = asset.metadata?.upload_operation as { manifest?: Record<string, any> } | undefined;
    const manifest = receipt?.manifest;
    if (manifest && (manifest.kind !== "path" || manifest.asset_set !== options.assetSet
      || (manifest.requested_path || manifest.storage_path) !== options.storagePath)) {
      throw new Error("此目录已按原选择登记，当前数据集已改变。请查看原登记；如需新的登记，请重新添加目录。");
    }
    return asset;
  };
  if (options.retry) {
    options.onStatusCheck?.();
    let saved;
    try { saved = await getSavedUploadOperation(projectId, options.operationId); }
    catch { /* Server protects repeated registration with the same operation identity. */ }
    if (saved?.saved) return verifySaved(saved.assets[0]);
  }
  try {
    const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/projects/${projectId}/assets/register`, {
      method: 'POST', credentials: 'include', signal: options.signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_type: 'pep', storage_path: options.storagePath,
        operation_id: options.operationId, metadata_json: { asset_set: options.assetSet, group_label: options.assetSet } }),
    }).catch(() => { throw new UploadResponseUnknownError(); });
    const result = await response.json().catch(() => { throw new UploadResponseUnknownError(); });
    if (!response.ok) throw new Error(result.message || '目录登记失败');
    apiClient.invalidateCache();
    return result as ProjectAsset;
  } catch (error) {
    if (error instanceof UploadResponseUnknownError) {
      options.onStatusCheck?.();
      const saved = await confirmInterruptedUpload(projectId, options.operationId);
      return verifySaved(saved.assets[0]);
    }
    throw error;
  }
}

export function assetPreviewUrl(assetId: string) {
  return `/api/assets/${assetId}/preview`;
}

export function assetDownloadUrl(assetId: string) {
  return `/api/assets/${assetId}/download`;
}

export async function getProjectAsset(projectId: string, assetId: string, options?: {view?: "selector"}) {
  const result = await apiClient.get<{ asset: ProjectAsset }>(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}`,
    options?.view ? {view:options.view} : undefined, { skipCache: true });
  if (!result.asset || result.asset.id !== assetId) throw new Error("返回的文件信息不完整，请重新读取文件。");
  return result;
}

export function projectAssetPreviewUrl(projectId: string, assetId: string) {
  return `/api/projects/${projectId}/assets/${assetId}/preview`;
}

export function projectAssetDownloadUrl(projectId: string, assetId: string) {
  return `/api/projects/${projectId}/assets/${assetId}/download`;
}

export function listProjectResults(projectId: string, options: { analysisType?: string; assetSet?: string; jobId?: string; unscoped?: boolean; page?: number; pageSize?: number } = {}) {
  return apiClient.get<ResultListResponse>(`/api/projects/${projectId}/results`, {
    analysis_type: options.analysisType,
    asset_set: options.assetSet, job_id: options.jobId, unscoped: options.unscoped,
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
