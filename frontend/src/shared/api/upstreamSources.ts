import { apiClient } from "./client";
import type { PreparationSource } from "../../features/analysis/analysisPreparation";
import type { components } from "./generated/schema";

export type UpstreamSummary = components["schemas"]["UpstreamSummary"];
export type UpstreamCandidate = components["schemas"]["UpstreamCandidate"];
export type UpstreamCatalog = components["schemas"]["UpstreamCatalogResponse"];
function endpoint(source:PreparationSource) {
  return "/api/script-hub/"+(source.kind==="pep" ? "pep-cache-candidates" : source.kind==="differential" ? "go-kegg-enrichment/sources" : "immune-infiltration-pathway/sources");
}
function context(projectId:string,dataset:string,source:PreparationSource) {
  return {project_id:projectId,asset_set:dataset,...(source.cacheType?{cache_type:source.cacheType}:{})};
}
export function getUpstreamSummary(projectId:string,dataset:string,source:PreparationSource) {
  return apiClient.get<{success:boolean;summary:UpstreamSummary}>(endpoint(source),{...context(projectId,dataset,source),view:"summary"},{skipCache:true,deduplicate:false});
}
export function getUpstreamCatalog(projectId:string,dataset:string,source:PreparationSource,options:{page:number;search:string;status:string}) {
  return apiClient.get<UpstreamCatalog>(endpoint(source),{...context(projectId,dataset,source),view:"catalog",page:options.page,page_size:20,q:options.search,status:options.status},{skipCache:true,deduplicate:false});
}
