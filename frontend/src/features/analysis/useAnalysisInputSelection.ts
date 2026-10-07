import { useEffect, useMemo } from "react";
import { getProjectInputSelection, listProjectDatasets } from "../../shared/api/projects";
import { useApi } from "../../shared/hooks/useApi";
import type { ProjectAsset } from "../../shared/types/domain";
import { buildAssetSets, getAssetSetName, type AssetSet } from "../assets/assetSets";

export function useAnalysisInputSelection(projectId:string, preferredScope:string, pinned:ProjectAsset[], revision=0, allowDefault=true) {
  const summaries=useApi(()=>projectId?listProjectDatasets(projectId):Promise.resolve({datasets:[]}),[projectId,revision]);
  const datasets=summaries.status==="ready"?summaries.data.datasets:[];
  const activeDatasets=datasets.filter(dataset=>!dataset.archived);
  const scope=preferredScope || (allowDefault && activeDatasets.length===1?activeDatasets[0].name:"");
  const selection=useApi(async()=>({projectId,...(projectId && scope?await getProjectInputSelection(projectId,scope):{asset_set:scope,assets:[],totals:{},truncated_kinds:[]})}),[projectId,scope,revision]);
  const ready=selection.status==="ready" && selection.data.projectId===projectId && selection.data.asset_set===scope;
  const currentAssets=ready?selection.data.assets:[];
  const snapshot=selection.status==="ready"?selection.data:null;
  useEffect(()=>{
    if(!ready || !snapshot?.assets.some(asset=>asset.metadata?.validation && (asset.metadata.validation as {status?:string}).status==="pending"))return;
    const timer=setTimeout(selection.refetch,5000);
    return ()=>clearTimeout(timer);
  },[ready,snapshot,selection.refetch]);
  const sets=useMemo(()=>{
    const rows=buildAssetSets([...new Map([...pinned,...currentAssets].filter(asset=>asset.project_id===projectId).map(asset=>[asset.id,asset])).values()]);
    const map=new Map(rows.map(set=>[set.name,set]));
    for(const dataset of datasets){
      const row=map.get(dataset.name) || {name:dataset.name,assets:[],pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""};
      map.set(dataset.name,{...row,display_name:dataset.display_name,archived:dataset.archived});
    }
    return [...map.values()].filter(row=>!row.archived || row.name===scope).sort((a,b)=>(a.display_name || a.name).localeCompare(b.display_name || b.name,undefined,{numeric:true}));
  },[projectId,currentAssets,pinned,datasets,scope]);
  const empty:AssetSet={name:scope,assets:[],pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""};
  const selected=sets.find(set=>set.name===scope) || empty;
  const error=summaries.status==="error"?summaries.error:selection.status==="error"?selection.error:null;
  const summaryLoading=summaries.status==="idle" || summaries.status==="loading";
  const loading=summaries.status==="idle" || summaries.status==="loading" || Boolean(scope && !ready && selection.status!=="error");
  return {scope,sets,selected,datasets,currentAssets,ready,error,loading,
    totals:ready?selection.data.totals:{},truncatedKinds:ready?selection.data.truncated_kinds:[],
    refresh:()=>{summaries.refetch();selection.refetch();},
    summaryLoading,containsScope:(name:string)=>datasets.some(dataset=>dataset.name===name) || pinned.some(asset=>getAssetSetName(asset)===name),
  };
}
