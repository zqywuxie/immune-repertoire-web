import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { ProjectAsset } from "../../shared/types/domain";
import { INPUT_RESOLUTION_BATCH_SIZE, resolveProjectInputSelection } from "../../shared/api/projects";
import { assetPath, getAssetSetName } from "../assets/assetSets";
import { inputAssetKind, validateInputAsset } from "./InputAssetIntent";

export type AnalysisData = {projectId:string;assetSetName:string;pepPaths:string[];profilePath:string;transcriptomePath:string;deconvolutionPath?:string;inputAssets?:ProjectAsset[];selectionExplicit?:boolean};
type SavedSelection = {projectId:string;assetSetName:string;inputs?:{pep:string[];profile:string;transcriptome:string;deconvolution:string}};
type SelectionState = "ready"|"loading"|"error";
const empty = (scope:SavedSelection):AnalysisData => ({projectId:scope.projectId,assetSetName:scope.assetSetName,pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""});
const Context = createContext<{data:AnalysisData|null;setData:(data:AnalysisData)=>void;selectionState:SelectionState;selectionError:string;retrySelection:()=>void}>({data:null,setData:()=>{},selectionState:"ready",selectionError:"",retrySelection:()=>{}});

function readSelection(key:string):SavedSelection|null {
  try {
    const saved=JSON.parse(sessionStorage.getItem(key)||"null");
    if(!saved || typeof saved.projectId!=="string" || typeof saved.assetSetName!=="string")return null;
    const scope={projectId:saved.projectId,assetSetName:saved.assetSetName};
    const inputs=saved.inputs;
    if(!inputs || !Array.isArray(inputs.pep) || !inputs.pep.every((id:unknown)=>typeof id==="string" && id)
      || ![inputs.profile,inputs.transcriptome,inputs.deconvolution].every(value=>typeof value==="string"))return scope;
    return {...scope,inputs};
  }catch{return null;}
}
function selectedPaths(data:AnalysisData) {return new Set([...data.pepPaths,data.profilePath,data.transcriptomePath,data.deconvolutionPath].filter(Boolean));}

export function AnalysisDataProvider({children,storageKey="analysis-selection"}:{children:ReactNode;storageKey?:string}) {
  const [saved]=useState(()=>readSelection(storageKey));
  const [data,updateData]=useState<AnalysisData|null>(()=>saved?empty(saved):null);
  const [selectionState,setSelectionState]=useState<SelectionState>(saved?.inputs?"loading":"ready");
  const [selectionError,setSelectionError]=useState("");
  const [retry,setRetry]=useState(0);
  const generation=useRef(0);
  const cancelledRestoration=useRef(false);
  const setData=useCallback((next:AnalysisData)=>{
    cancelledRestoration.current=true;
    generation.current++;
    setSelectionState("ready");setSelectionError("");
    updateData(previous=>{
      const same=previous?.projectId===next.projectId && previous.assetSetName===next.assetSetName;
      // Keep other selected identities, but let a fresh row replace metadata for the same asset.
      const refs=[...(same?previous?.inputAssets||[]:[]),...(next.inputAssets||[])];
      const paths=selectedPaths(next);
      const inputAssets=[...new Map(refs.filter(asset=>asset.project_id===next.projectId && getAssetSetName(asset)===next.assetSetName && paths.has(assetPath(asset))).map(asset=>[asset.id,asset])).values()];
      return {...next,...(next.inputAssets || (same && previous?.inputAssets)?{inputAssets,selectionExplicit:next.selectionExplicit ?? true}:{})};
    });
  },[]);
  useEffect(()=>{
    if(!saved?.inputs || cancelledRestoration.current)return;
    const version=++generation.current;
    setSelectionState("loading");setSelectionError("");
    const inputs=saved.inputs;
    const ids=[...new Set([...inputs.pep,inputs.profile,inputs.transcriptome,inputs.deconvolution].filter(Boolean))];
    const restore=async()=>{
      const assets:ProjectAsset[]=[];
      for(let offset=0;offset<ids.length;offset+=INPUT_RESOLUTION_BATCH_SIZE){
        const result=await resolveProjectInputSelection(saved.projectId,saved.assetSetName,ids.slice(offset,offset+INPUT_RESOLUTION_BATCH_SIZE));
        if(generation.current!==version)return;
        for(const asset of result.assets){
          if(getAssetSetName(asset)!==saved.assetSetName)throw new Error("保存的输入不属于当前数据集，请重新选择。");
          assets.push(validateInputAsset(asset,saved.projectId,saved.assetSetName));
        }
      }
      const map=new Map(assets.map(asset=>[asset.id,asset]));
      const path=(id:string,kind:string)=>{
        if(!id)return "";
        const asset=map.get(id);
        if(!asset || inputAssetKind(asset)!==kind)throw new Error("保存的输入类型已不匹配，请重新选择输入。");
        return assetPath(asset);
      };
      const restored:AnalysisData={...empty(saved),pepPaths:inputs.pep.map(id=>path(id,"pep")),profilePath:path(inputs.profile,"profile"),transcriptomePath:path(inputs.transcriptome,"transcriptome"),deconvolutionPath:path(inputs.deconvolution,"deconvolution"),inputAssets:assets,selectionExplicit:true};
      if(generation.current!==version)return;
      updateData(restored);setSelectionState("ready");
    };
    void restore().catch(reason=>{
      if(generation.current!==version)return;
      setSelectionState("error");setSelectionError(reason instanceof Error?reason.message:"输入恢复失败，请重试或重新选择。");
    });
    return ()=>{generation.current++;};
  },[saved,retry]);
  useEffect(()=>{
    if(!data || selectionState!=="ready")return;
    const scope={projectId:data.projectId,assetSetName:data.assetSetName};
    const assets=data.inputAssets || [];
    const paths=selectedPaths(data);
    const complete=data.selectionExplicit && [...paths].every(path=>assets.some(asset=>assetPath(asset)===path));
    const id=(path:string|undefined,kind:string)=>assets.find(asset=>assetPath(asset)===path && inputAssetKind(asset)===kind)?.id || "";
    const snapshot=complete?{...scope,inputs:{pep:data.pepPaths.map(path=>id(path,"pep")),profile:id(data.profilePath,"profile"),transcriptome:id(data.transcriptomePath,"transcriptome"),deconvolution:id(data.deconvolutionPath,"deconvolution")}}:scope;
    try{sessionStorage.setItem(storageKey,JSON.stringify(snapshot));}catch{ /* In-memory selection remains available. */ }
  },[data,selectionState,storageKey]);
  return <Context.Provider value={{data,setData,selectionState,selectionError,retrySelection:()=>{cancelledRestoration.current=false;setRetry(value=>value+1);}}}>{children}</Context.Provider>;
}
export const useAnalysisData=()=>useContext(Context);
