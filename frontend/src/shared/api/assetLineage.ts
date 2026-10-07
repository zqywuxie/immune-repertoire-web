import {apiClient} from "./client";
import type {components} from "./generated/schema";
export type AssetLineageResponse=components["schemas"]["AssetLineageResponse"];
export type LineageSection=AssetLineageResponse["section"];
export type LineageEntry=AssetLineageResponse["items"][number];
export function getAssetLineage(projectId:string,assetId:string,section:LineageSection,page:number) {
  return apiClient.get<AssetLineageResponse>(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/lineage`,{section,page,page_size:20},{skipCache:true});
}
