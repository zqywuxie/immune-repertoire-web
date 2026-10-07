import type { ProjectAsset } from "../../shared/types/domain";
import type { AnalysisData } from "./AnalysisDataContext";
import { useApi } from "../../shared/hooks/useApi";
import { getProjectAsset } from "../../shared/api/projects";
import { assetPath, getAssetSetName, projectAssetDetailPath, projectReturnPath } from "../assets/assetSets";
import { validationLabels } from "../assets/assetLabels";
import "../assets/DataManagement.css";

export function inputAssetKind(asset: ProjectAsset) {
  const kind=asset.asset_type.toLowerCase();
  if(kind==="pep")return "pep";
  if(["profile","datapoint"].includes(kind))return "profile";
  if(["transcriptome","expression"].includes(kind))return "transcriptome";
  if(["deconvolution","cibersort"].includes(kind))return "deconvolution";
  return null;
}

export function validateInputAsset(asset:ProjectAsset,projectId:string,dataset:string) {
  if(asset.project_id!==projectId)throw new Error("所选文件不属于当前项目，请重新选择。");
  if(dataset && getAssetSetName(asset)!==dataset)throw new Error("所选文件不属于当前数据集，请重新选择。");
  if(!inputAssetKind(asset))throw new Error("此文件不是分析输入，请选择克隆序列、样本指标、转录组或免疫细胞浸润数据。");
  if(!asset.storage_path && !asset.storage_uri)throw new Error("此文件没有可用的输入地址，请重新导入。");
  return asset;
}

export function useInputAssetIntent(projectId:string,dataset:string,requestedId:string) {
  return useApi(async()=>{
    if(!requestedId)return null;
    if(!projectId)throw new Error("请先指定文件所属项目。");
    const result=await getProjectAsset(projectId,requestedId);
    return validateInputAsset(result.asset,projectId,dataset);
  },[projectId,dataset,requestedId]);
}

export function inputDataForAsset(base:AnalysisData,asset:ProjectAsset):AnalysisData {
  const dataset=getAssetSetName(asset);
  const same=base.projectId===asset.project_id && base.assetSetName===dataset;
  const next:AnalysisData=same?{...base}:{projectId:asset.project_id,assetSetName:dataset,pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""};
  const path=assetPath(asset);
  switch(inputAssetKind(asset)){
    case "pep":next.pepPaths=[path];break;
    case "profile":next.profilePath=path;break;
    case "transcriptome":next.transcriptomePath=path;break;
    case "deconvolution":next.deconvolutionPath=path;break;
  }
  return next;
}

export function inputAssetReturnPath(projectId:string,asset:ProjectAsset|null,value:string) {
  const fallback=asset?projectAssetDetailPath(projectId,asset.id,getAssetSetName(asset)): `/management/projects/${encodeURIComponent(projectId)}?tab=assets`;
  return projectReturnPath(projectId,value,fallback);
}

export function InputAssetNotice({asset,loading,error,returnPath,onClear,onRetry}:{asset:ProjectAsset|null;loading:boolean;error?:string|null;returnPath:string;onClear:()=>void;onRetry:()=>void}) {
  const metadata=asset?.metadata || {};
  const validation=metadata.validation as {status?:string}|undefined;
  return <aside className="data-input-intent" aria-label="本次使用文件">
    {loading?<p role="status">正在读取入口指定的文件…</p>:error?<p className="data-error" role="alert">{error}</p>:asset?<>
      <p><strong>{asset.original_name}</strong><span> · 数据集：{getAssetSetName(asset)}</span></p>
      <p className="data-muted">{metadata.superseded?"历史版本 · 本次明确选用":"当前输入"} · 版本 <span title={String(metadata.content_version || asset.id)}>{String(metadata.content_version || asset.id).slice(0,12)}</span> · {validationLabels[validation?.status || "unknown"] || "尚未校验"}</p>
      <p className="data-muted">核对本次输入和分析配置后再运行；选择历史版本不会更改项目当前输入。</p>
    </>:null}
    <div className="data-row-actions"><a className="btn btn-secondary" href={returnPath}>返回来源文件</a><button className="btn btn-secondary" onClick={onClear}>重新选择文件</button>{error&&<button className="btn btn-secondary" onClick={onRetry}>重新读取文件</button>}</div>
  </aside>;
}
