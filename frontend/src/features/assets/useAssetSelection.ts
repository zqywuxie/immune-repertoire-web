import { useCallback, useEffect, useState } from "react";
import type { ProjectAsset } from "../../shared/types/domain";
import { getAssetSetName } from "./assetSets";
export const FILE_SELECTION_LIMIT = 200;
type Update = Set<string> | ((previous:Set<string>)=>Set<string>);
export type AssetSelection = {items:ProjectAsset[]; change:(update:Update,current:ProjectAsset[])=>void};
/** Explicit identities survive pagination; a new project, dataset or filter starts a new selection. */
export function useAssetSelection(scope:string):AssetSelection {
  const [state,setState] = useState<{scope:string;items:ProjectAsset[]}>({scope,items:[]});
  const items=state.scope===scope?state.items:[];
  useEffect(()=>{setState(previous=>previous.scope===scope?previous:{scope,items:[]});},[scope]);
  const change=useCallback((update:Update,current:ProjectAsset[])=>{
    setState(previous=>{
      const old=previous.scope===scope?previous.items:[];
      const ids=typeof update==="function"?update(new Set(old.map(item=>item.id))):update;
      const identities=new Map([...old,...current].map(item=>[item.id,item]));
      const next=[...ids].slice(0,FILE_SELECTION_LIMIT).map(id=>identities.get(id)).filter((item):item is ProjectAsset=>!!item).map(identity);
      return {scope,items:next};
    });
  },[scope]);
  return {items,change};
}
function identity(asset:ProjectAsset):ProjectAsset {
  const metadata=asset.metadata || {};
  // Keep confirmation facts, never the full validation report or upload manifest.
  return {id:asset.id,project_id:asset.project_id,asset_type:asset.asset_type,original_name:asset.original_name,
    storage_path:asset.storage_path,size:asset.size,uploaded_at:asset.uploaded_at,
    metadata:{asset_set:getAssetSetName(asset),superseded:metadata.superseded,content_version:metadata.content_version,
      validation:{status:(metadata.validation as {status?:string}|undefined)?.status}}};
}
