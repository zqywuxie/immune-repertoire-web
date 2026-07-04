import type { ProjectAsset } from "../../shared/types/domain";

export interface AssetSet {
  name: string;
  assets: ProjectAsset[];
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
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
      type.includes("expression"))
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
    }
  }

  return [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
}

export function nextAssetSetName(sets: AssetSet[]): string {
  let max = 0;
  for (const set of sets) {
    const match = /^Set(\d+)$/i.exec(set.name.trim());
    if (match) max = Math.max(max, Number(match[1]));
  }
  return `Set${max + 1 || 1}`;
}
