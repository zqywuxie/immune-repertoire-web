/** Group-spec API for ScriptHub analysis module forms. */
import { apiClient } from "./client";
import type { components } from "./generated/schema";

export interface GroupSpec {
  revision?: string;
  id: string;
  name: string;
  project_id: string;
  spec_json?: Record<string, unknown>;
  source?: { asset_id: string | null; name: string; asset_set: string; content_version?: string;
    available: boolean; reason: string };
}

export interface GroupSpecListResponse {
  group_specs: GroupSpec[];
}

export function listGroupSpecs(projectId: string, context: {profilePath?: string; assetSet?: string} = {}) {
  return apiClient.get<GroupSpecListResponse>(
    `/api/projects/${projectId}/group-specs`, {profile_path: context.profilePath, asset_set: context.assetSet}
  );
}


// Management cards are summaries; callers must fetch full detail before editing.
export type FullGroupSpec = components["schemas"]["ProjectGroupSpec"];
export type GroupSpecSummary = components["schemas"]["ProjectGroupSpecSummary"];
export type GroupSpecCatalog = components["schemas"]["ProjectGroupSpecCatalog"];

export function listGroupSpecCatalog(projectId:string, options:{assetSet?:string; search?:string; page?:number; pageSize?:number} = {}) {
  return apiClient.get<GroupSpecCatalog>(`/api/projects/${encodeURIComponent(projectId)}/group-specs`,
    {view:"summary", asset_set:options.assetSet, q:options.search, page:options.page || 1, page_size:options.pageSize || 20},
    {skipCache:true});
}

export async function getGroupSpec(projectId:string, specId:string) {
  const result = await apiClient.get<{group_spec:FullGroupSpec}>(`/api/projects/${encodeURIComponent(projectId)}/group-specs/${encodeURIComponent(specId)}`,
    undefined, {skipCache:true, deduplicate:false});
  const spec = result.group_spec;
  if (!spec || spec.id !== specId || spec.project_id !== projectId || !spec.spec_json
      || typeof spec.spec_json !== "object" || Array.isArray(spec.spec_json)) {
    throw new Error("返回的完整分组定义不匹配，请重新读取；当前编辑仍保留。");
  }
  return spec;
}
