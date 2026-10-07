import type { ProjectAsset } from "../../shared/types/domain";

export interface AssetSet {
  display_name?: string;
  archived?: boolean;
  name: string;
  assets: ProjectAsset[];
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
  deconvolutionPath: string;
}

export function assetPath(asset: ProjectAsset): string {
  return asset.storage_path || asset.storage_uri || asset.original_name || asset.id;
}

export function getAssetSetName(asset: ProjectAsset): string {
  const metadata = ((asset as any).metadata || {}) as Record<string, unknown>;
  const value =
    metadata.asset_set ||
    metadata.dataset ||
    metadata.data_set ||
    metadata.group_label ||
    metadata.group;
  return String(value || "Set1").trim() || "Set1";
}

export function isInputAsset(asset: ProjectAsset): boolean {
  const type = (asset.asset_type || "").toLowerCase();
  if (["project_file", "attachment", "document"].includes(type)) return false;
  return (
    !type.includes("processed_result") &&
    (type.includes("pep") ||
      type.includes("profile") ||
      type.includes("datapoint") ||
      type.includes("transcriptome") ||
      type.includes("expression") || type === "deconvolution" || type === "cibersort")
  );
}

export function buildAssetSets(assets: ProjectAsset[]): AssetSet[] {
  const groups = new Map<string, AssetSet>();

  for (const asset of assets.filter(isInputAsset)) {
    const name = getAssetSetName(asset);
    if (!groups.has(name)) {
      groups.set(name, {
        name,
        assets: [],
        pepPaths: [],
        profilePath: "",
        transcriptomePath: "",
        deconvolutionPath: "",
      });
    }

    const group = groups.get(name)!;
    const path = assetPath(asset);
    const type = (asset.asset_type || "").toLowerCase();

    group.assets.push(asset);
    if (type.includes("pep") && !group.pepPaths.includes(path)) {
      group.pepPaths.push(path);
    } else if ((type.includes("profile") || type.includes("datapoint")) && !group.profilePath) {
      group.profilePath = path;
    } else if ((type.includes("transcriptome") || type.includes("expression")) && !group.transcriptomePath) {
      group.transcriptomePath = path;
    } else if (["deconvolution", "cibersort"].includes(type) && !group.deconvolutionPath) {
      group.deconvolutionPath = path;
    }
  }

  for (const group of groups.values()) {
    for (const [key, types] of [["profilePath", ["profile", "datapoint"]], ["transcriptomePath", ["transcriptome", "expression"]], ["deconvolutionPath", ["deconvolution", "cibersort"]]] as const) {
      const paths = new Set(group.assets.filter(asset => (types as readonly string[]).includes(asset.asset_type)).map(assetPath));
      if (paths.size > 1) group[key] = "";
    }
  }
  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

export function nextAssetSetName(sets: Pick<AssetSet, "name">[]): string {
  let max = 0;
  for (const set of sets) {
    const match = /^Set(\d+)$/i.exec(set.name.trim());
    if (match) max = Math.max(max, Number(match[1]));
  }
  return `Set${max + 1 || 1}`;
}

export function projectReturnPath(projectId: string, value: string, fallback: string) {
  if(value){
    try {
      const url=new URL(value,window.location.origin);
      if(url.origin===window.location.origin && url.pathname===`/management/projects/${encodeURIComponent(projectId)}`)return url.pathname+url.search+url.hash;
    }catch{ /* Return to the current project when the source is unavailable. */ }
  }
  return fallback;
}

export function projectAssetDetailPath(projectId: string, assetId: string, dataset: string, kind = "") {
  const query = new URLSearchParams({ tab: "assets", asset_set: dataset, asset: assetId });
  if (kind) query.set("file_type", kind);
  return `/management/projects/${encodeURIComponent(projectId)}?${query}`;
}

/** A result with no saved scope must not inherit the input upload default. */
export function getAssetSetLabel(asset: ProjectAsset): string {
  if(asset.asset_type !== "processed_result") return getAssetSetName(asset);
  const saved=asset.metadata || {};
  for(const key of ["asset_set","dataset","data_set","group_label","group"]){const value=saved[key];if(typeof value==="string" && value.trim())return value.trim();}
  const config=saved.config_json;
  if(config && typeof config==="object" && !Array.isArray(config)){
    const value=(config as Record<string,unknown>).asset_set;if(typeof value==="string" && value.trim())return value.trim();
  }
  return "未记录数据集";
}
