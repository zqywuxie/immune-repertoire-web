import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
import { listProjectAssets } from "../../shared/api/projects";
import { Select } from "../../shared/components/Select";
import { assetPath, buildAssetSets } from "../assets/assetSets";
import { useAnalysisData, type AnalysisData } from "../analysis/AnalysisDataContext";

const kinds = [
  {key:"pepPaths", title:"克隆序列表", types:["pep"]},
  {key:"profilePath", title:"样本指标表", types:["profile","datapoint"]},
  {key:"transcriptomePath", title:"转录组", types:["transcriptome","expression"]},
  {key:"deconvolutionPath", title:"免疫细胞浸润", types:["deconvolution","cibersort"]},
] as const;

export function ProjectDatasetSummary({projectId, revision}:{projectId:string; revision:number}) {
  const assets = useApi(() => listProjectAssets(projectId, {pageSize:200}), [projectId,revision]);
  const [query,setQuery] = useSearchParams();
  const {data,setData} = useAnalysisData();
  const sets = useMemo(() => buildAssetSets(assets.status === "ready" ? assets.data.assets : []), [assets.status, assets.status === "ready" ? assets.data : null]);
  const name = query.get("asset_set") || (data?.projectId === projectId ? data.assetSetName : "") || (sets.length === 1 ? sets[0].name : "");
  const selected = sets.find(set => set.name === name);
  useEffect(() => {
    if (!selected) return;
    const same = data?.projectId === projectId && data.assetSetName === selected.name;
    const available = new Set(selected.assets.map(assetPath));
    const next: AnalysisData = {projectId,assetSetName:selected.name,pepPaths:selected.pepPaths,profilePath:selected.profilePath,transcriptomePath:selected.transcriptomePath,deconvolutionPath:selected.deconvolutionPath};
    for (const key of ["profilePath","transcriptomePath","deconvolutionPath"] as const) {
      if (same && data?.[key] && available.has(data[key]!)) next[key] = data[key];
    }
    if (JSON.stringify(next) !== JSON.stringify(data)) setData(next);
  }, [selected,projectId,data,setData]);
  if (assets.status === "loading") return <p role="status">正在读取项目输入…</p>;
  if (assets.status === "error") return <p role="alert">项目数据读取失败。<button className="btn btn-secondary" onClick={assets.refetch}>重新读取</button></p>;
  return <div className="project-dataset-summary">
    <div className="project-dataset-selector"><span>本次分析数据集</span><Select ariaLabel="本次分析数据集" value={name} placeholder="请选择数据集" options={sets.map(set => ({value:set.name,label:set.name}))} onChange={value => {
      setQuery(previous => {const next=new URLSearchParams(previous);next.set("asset_set",value);next.delete("upstream_artifact");return next;});
    }} /></div>
    {!sets.length ? <p>还没有输入数据，点击“上传与管理数据集”开始准备。</p> : !selected ? <p>请选择数据集，查看本次分析可用的输入。</p> : <div className="project-input-grid">
      {kinds.map(kind => {
        const candidates = selected.assets.filter(asset => (kind.types as readonly string[]).includes(asset.asset_type));
        const value = data?.projectId === projectId && data.assetSetName === name ? data[kind.key] : "";
        const chosen = kind.key === "pepPaths" ? candidates : candidates.filter(asset => assetPath(asset) === value);
        const invalid = chosen.some(asset => (asset.metadata as any)?.validation?.status === "invalid");
        const pending = chosen.some(asset => (asset.metadata as any)?.validation?.status === "pending");
        const mapped = chosen.some(asset => (asset.metadata as any)?.validation?.status === "needs_mapping");
        const valid = chosen.length > 0 && chosen.every(asset => (asset.metadata as any)?.validation?.status === "valid");
        const state = invalid ? "校验未通过" : pending ? "正在校验" : mapped ? "需要确认列映射" : !candidates.length ? "未上传" : !chosen.length ? "请选择版本" : valid ? "校验通过" : "已选择，待分析检查";
        return <article key={kind.key} className={`project-input-card${invalid ? " is-invalid" : ""}`}>
          <div><h3>{kind.title}</h3><span>{state}</span></div>
          {kind.key !== "pepPaths" && candidates.length > 1 ? <Select ariaLabel={`${kind.title}版本`} value={typeof value === "string" ? value : ""} options={candidates.map(asset => ({value:assetPath(asset),label:`${asset.original_name} · ${asset.uploaded_at?.slice(0,10) || asset.id}`}))} onChange={path => {if (data) setData({...data,[kind.key]:path});}} /> : <p title={chosen.map(asset => asset.original_name).join("、")}>{chosen.length > 1 ? `${chosen.length} 个输入文件` : chosen[0]?.original_name || "按分析需要提供"}</p>}
          {chosen.length === 1 && <small>上传于 {chosen[0].uploaded_at?.replace("T"," ").slice(0,16) || "未记录"}</small>}
        </article>;
      })}
    </div>}
  </div>;
}
