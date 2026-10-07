import { ProjectDatasetSummary } from "./ProjectDatasetSummary";
import { useAnalysisData } from "../analysis/AnalysisDataContext";
import { FolderOpen, Plus, Upload, ChevronUp, CheckCircle2 } from "lucide-react";
import { ProjectPicker } from "./ProjectPicker";
import "./AnalysisProjectPanel.css";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
import { apiClient } from "../../shared/api/client";
import { getProject } from "../../shared/api/projects";
import { ProjectForm } from "./ProjectForm";
import { InputValidationStatus } from "../assets/InputValidationStatus";
import { AssetUpload } from "../assets/AssetUpload";
import type { ProjectAsset, ProjectCreate, ProjectSummary } from "../../shared/types/domain";

export function AnalysisProjectPanel({requestedAsset,inputIntentPending=false}:{requestedAsset?:ProjectAsset;inputIntentPending?:boolean}={}) {
  const {data:sharedData,setData} = useAnalysisData();
  const [query, setQuery] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [editingData, setEditingData] = useState(false);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState("");
  const projectId = query.get("project") || sharedData?.projectId || "";
  const assetSet = query.has("asset_set") ? query.get("asset_set") || "" : sharedData?.projectId === projectId ? sharedData.assetSetName : "";
  const selectedState = useApi(() => getProject(projectId, {summaryOnly:true}), [projectId, revision], !!projectId);
  const selected = selectedState.status === "ready" && selectedState.data?.id === projectId ? selectedState.data : null;
  function select(id: string) {
    setEditingData(false); setMessage("");
    setData({projectId:id,assetSetName:"",pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""});
    setQuery(previous => { const next = new URLSearchParams(previous); next.delete("asset_set"); next.delete("input_asset"); next.delete("return_to"); if (id) next.set("project", id); else next.delete("project"); return next; });
  }
  async function create(data: ProjectCreate) {
    const result = await apiClient.post<ProjectSummary>("/api/projects", data);
    apiClient.invalidatePath("/api/projects");
    select(result.id);
    setEditingData(true);
  }
  return <section className="project-intake" aria-label="项目与数据">
    <div className="project-intake-heading"><span className="project-intake-icon"><FolderOpen size={23}/></span><div><h2>项目与数据</h2>
    <p>为本次分析选择项目，输入数据可在项目内重复使用。</p></div><span className="project-intake-step">分析准备</span></div>
    <div className="project-intake-controls">
        <div className="project-intake-picker"><ProjectPicker label="当前项目" value={projectId} onChange={select} revision={revision}/></div>
        <button className="project-intake-button project-intake-secondary" onClick={() => setCreating(true)}><Plus size={17}/>新建项目</button>
        <button className="project-intake-button project-intake-primary" disabled={!selected} aria-expanded={editingData} onClick={() => setEditingData(!editingData)}>{editingData ? <ChevronUp size={17}/> : <Upload size={17}/>} {editingData ? "收起数据管理" : "上传与管理数据集"}</button>
      </div>
    {projectId && selectedState.status === "error" && <p role="alert">当前项目读取失败：{selectedState.error}<button className="btn btn-secondary" onClick={selectedState.refetch}>重新读取当前项目</button></p>}
    <div className="project-intake-summary">{selected ? <><CheckCircle2 size={15}/><span>当前分析将关联至 <strong>{selected.name}</strong></span></> : <><FolderOpen size={15}/><span>{projectId ? "正在确认当前项目及数据范围…" : "还没有项目？新建项目后即可上传数据并开始分析。"}</span></>}</div>
    {message && <p className="project-intake-success" role="status">{message}</p>}
    {selected && <ProjectDatasetSummary key={`dataset-${selected.id}`} projectId={selected.id} revision={revision} requestedAsset={requestedAsset} inputIntentPending={inputIntentPending}/>}
    {selected && assetSet && <InputValidationStatus key={`validation-${selected.id}:${assetSet}`} projectId={selected.id} revision={revision} assetSet={assetSet}/>}
    {editingData && selected && <AssetUpload key={`upload-${selected.id}`} projectId={selected.id} initialAssetSet={assetSet} onSuccess={() => { apiClient.invalidatePath("/api/projects"); setMessage("数据已保存，可以选择下方分析。"); setRevision(value => value + 1); }}/>}
    <ProjectForm open={creating} onClose={() => setCreating(false)} onSubmit={create}/>
  </section>;
}
