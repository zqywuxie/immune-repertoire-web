import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAnalysisInputSelection } from "../analysis/useAnalysisInputSelection";
import { DirectoryBrowser } from "../../shared/components/DirectoryBrowser";
import type { ProjectAsset } from "../../shared/types/domain";
import { inputDataForAsset } from "../analysis/InputAssetIntent";
import { Select } from "../../shared/components/Select";
import { assetPath } from "../assets/assetSets";
import { useAnalysisData, type AnalysisData } from "../analysis/AnalysisDataContext";

const kinds = [
  {key:"pepPaths", title:"克隆序列表", types:["pep"]},
  {key:"profilePath", title:"样本指标表", types:["profile","datapoint"]},
  {key:"transcriptomePath", title:"转录组", types:["transcriptome","expression"]},
  {key:"deconvolutionPath", title:"免疫细胞浸润", types:["deconvolution","cibersort"]},
] as const;

export function ProjectDatasetSummary({projectId, revision, requestedAsset, inputIntentPending=false}:{projectId:string; revision:number;requestedAsset?:ProjectAsset;inputIntentPending?:boolean}) {
  const appliedIntent=useRef("");
  const [query,setQuery] = useSearchParams();
  const {data,setData} = useAnalysisData();
  const [selectedVersions,setSelectedVersions] = useState<ProjectAsset[]>([]);
  const paths = [...(data?.pepPaths || []),data?.profilePath,data?.transcriptomePath,data?.deconvolutionPath];
  const pinned = [...(data?.inputAssets || []),...selectedVersions].filter(asset=>asset.project_id===projectId && paths.includes(assetPath(asset)));
  const preferred=query.has("asset_set")?query.get("asset_set") || "":data?.projectId===projectId?data.assetSetName:"";
  const inputs=useAnalysisInputSelection(projectId,preferred,[...pinned,...(requestedAsset?[requestedAsset]:[])],revision,!query.has("asset_set"));
  const sets=inputs.sets;
  const name=inputs.scope;
  const selected=name && inputs.ready?inputs.selected:undefined;
  const [browseKind,setBrowseKind]=useState("");
  useEffect(() => {
    if(!requestedAsset)appliedIntent.current="";
    if (!selected || inputIntentPending || inputs.error) return;
    const same = data?.projectId === projectId && data.assetSetName === selected.name;
    const available = new Set(selected.assets.map(assetPath));
    let next: AnalysisData = {projectId,assetSetName:selected.name,pepPaths:selected.pepPaths,profilePath:selected.profilePath,transcriptomePath:selected.transcriptomePath,deconvolutionPath:selected.deconvolutionPath};
    for (const key of ["profilePath","transcriptomePath","deconvolutionPath"] as const) {
      if (same && data && (data.selectionExplicit || (data[key] && available.has(data[key]!)))) next[key] = data[key] || "";
    }
    if (same && data && (data.selectionExplicit || (data.pepPaths.length && data.pepPaths.every(path=>available.has(path))))) next.pepPaths=data.pepPaths;
    if(requestedAsset && appliedIntent.current!==requestedAsset.id){
      const selectedPath=assetPath(requestedAsset);
      const alreadySelected=same && [...(data?.pepPaths || []),data?.profilePath,data?.transcriptomePath,data?.deconvolutionPath].includes(selectedPath);
      if(!(query.get("reuse_inputs")==="1" && data?.selectionExplicit && alreadySelected) && (!appliedIntent.current || !alreadySelected)) next=inputDataForAsset(next,requestedAsset);
      appliedIntent.current=requestedAsset.id;
    }
    const selectedPaths=new Set([...next.pepPaths,next.profilePath,next.transcriptomePath,next.deconvolutionPath]);
    next.inputAssets=selected.assets.filter(asset=>selectedPaths.has(assetPath(asset)));
    next.selectionExplicit=true;
    if (JSON.stringify(next) !== JSON.stringify(data)) setData(next);
  }, [selected,projectId,data,setData,requestedAsset,inputIntentPending,query,inputs.error]);
  if (inputs.loading) return <p role="status">正在读取项目输入…</p>;
  if (inputs.error) return <p role="alert">项目数据读取失败。<button className="btn btn-secondary" onClick={inputs.refresh}>重新读取</button></p>;
  return <div className="project-dataset-summary">
    <div className="project-dataset-selector"><span>本次分析数据集</span><Select ariaLabel="本次分析数据集" value={name} placeholder="请选择数据集" options={sets.map(set => ({value:set.name,label:(set.display_name || set.name)+(set.archived ? "（已归档）" : "")}))} onChange={value => {
      setBrowseKind("");
      setQuery(previous => {const next=new URLSearchParams(previous);next.set("asset_set",value);next.delete("upstream_artifact");next.delete("input_asset");return next;});
    }} /></div>
    {preferred && !inputs.containsScope(preferred) && <p role="alert">指定数据集不存在或已移除，请重新选择。</p>}
    {!sets.length ? <p>还没有输入数据，点击“上传与管理数据集”开始准备。</p> : !selected ? <p>请选择数据集，查看本次分析可用的输入。</p> : <div className="project-input-grid">
      {kinds.map(kind => {
        const candidates = selected.assets.filter(asset => (kind.types as readonly string[]).includes(asset.asset_type));
        const value = data?.projectId === projectId && data.assetSetName === name ? data[kind.key] : "";
        const chosen = candidates.filter(asset => kind.key === "pepPaths" ? Array.isArray(value) && value.includes(assetPath(asset)) : assetPath(asset) === value);
        const invalid = chosen.some(asset => (asset.metadata as any)?.validation?.status === "invalid");
        const failed = chosen.some(asset => (asset.metadata as any)?.validation?.status === "failed");
        const pending = chosen.some(asset => (asset.metadata as any)?.validation?.status === "pending");
        const mapped = chosen.some(asset => (asset.metadata as any)?.validation?.status === "needs_mapping");
        const valid = chosen.length > 0 && chosen.every(asset => (asset.metadata as any)?.validation?.status === "valid");
        const state = invalid ? "校验未通过" : failed ? "校验失败，请重试" : pending ? "正在校验" : mapped ? "需要确认列映射" : !candidates.length ? "未上传" : !chosen.length ? "请选择版本" : valid ? "校验通过" : "已选择，待分析检查";
        return <article key={kind.key} className={`project-input-card${invalid || failed ? " is-invalid" : ""}`}>
          <div><h3>{kind.title}</h3><span>{state}</span></div>
          {kind.key !== "pepPaths" && candidates.length > 1 ? <Select ariaLabel={`${kind.title}版本`} value={typeof value === "string" ? value : ""} options={candidates.map(asset => ({value:assetPath(asset),label:`${asset.original_name} · ${asset.uploaded_at?.slice(0,10) || asset.id}`}))} onChange={path => {
            const chosenAsset=candidates.find(asset=>assetPath(asset)===path);
            if(!chosenAsset || !data)return;
            setSelectedVersions(previous=>[...previous.filter(asset=>asset.id!==chosenAsset.id),chosenAsset]);
            setQuery(previous=>{const next=new URLSearchParams(previous);next.set("input_asset",chosenAsset.id);next.set("reuse_inputs","1");return next;});
            setData({...data,[kind.key]:path,inputAssets:[...(data.inputAssets || []),chosenAsset],selectionExplicit:true});
          }} /> : <p title={chosen.map(asset => asset.original_name).join("、")}>{chosen.length > 1 ? `${chosen.length} 个输入文件` : chosen[0]?.original_name || "按分析需要提供"}</p>}
          {kind.key!=="pepPaths" && inputs.truncatedKinds.includes(kind.key==="profilePath"?"profile":kind.key==="transcriptomePath"?"transcriptome":"deconvolution") && <button className="btn btn-secondary" onClick={()=>setBrowseKind(kind.key)}>搜索更多版本</button>}
          {chosen.length === 1 && <small>上传于 {chosen[0].uploaded_at?.replace("T"," ").slice(0,16) || "未记录"}</small>}
        </article>;
      })}
    </div>}
    {browseKind && name && inputs.ready && <section aria-label="搜索输入版本"><div className="data-row-actions"><strong>搜索并选择版本</strong><button className="btn btn-secondary" onClick={()=>setBrowseKind("")}>收起版本选择</button></div><DirectoryBrowser key={`${projectId}:${name}:${browseKind}`} projectId={projectId} assetSet={name} inputsOnly assetType={browseKind==="profilePath"?"profile":browseKind==="transcriptomePath"?"transcriptome":"deconvolution"} searchable onSelect={asset=>{
      if(!data)return;
      setSelectedVersions(previous=>[...previous.filter(item=>item.id!==asset.id),asset]);
      setData({...data,[browseKind]:assetPath(asset),inputAssets:[...(data.inputAssets || []),asset],selectionExplicit:true});
      setQuery(previous=>{const next=new URLSearchParams(previous);next.set("input_asset",asset.id);next.set("reuse_inputs","1");return next;});
      setBrowseKind("");
    }}/></section>}
  </div>;
}
