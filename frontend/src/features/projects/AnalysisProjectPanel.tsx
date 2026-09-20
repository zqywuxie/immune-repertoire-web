import { ProjectDatasetSummary } from "./ProjectDatasetSummary";
import { useAnalysisData } from "../analysis/AnalysisDataContext";
import { FolderOpen, Plus, Upload, ChevronUp, CheckCircle2 } from "lucide-react";
import { Select } from "../../shared/components/Select";
import "./AnalysisProjectPanel.css";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
import { apiClient } from "../../shared/api/client";
import { listProjects } from "../../shared/api/projects";
import { ProjectForm } from "./ProjectForm";
import { InputValidationStatus } from "../assets/InputValidationStatus";
import { AssetUpload } from "../assets/AssetUpload";
import type { ProjectCreate, ProjectSummary } from "../../shared/types/domain";

export function AnalysisProjectPanel() {
  const {data:sharedData,setData} = useAnalysisData();
  const projects = useApi(listProjects, []);
  const [query, setQuery] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [editingData, setEditingData] = useState(false);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState("");
  const projectId = query.get("project") || sharedData?.projectId || "";
  const items = projects.status === "ready" ? projects.data.projects : [];
  const selected = items.find(item => item.id === projectId);
  function select(id: string) {
    setEditingData(false); setMessage("");
    setData({projectId:id,assetSetName:"",pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""});
    setQuery(previous => { const next = new URLSearchParams(previous); next.delete("asset_set"); if (id) next.set("project", id); else next.delete("project"); return next; });
  }
  async function create(data: ProjectCreate) {
    const result = await apiClient.post<ProjectSummary>("/api/projects", data);
    apiClient.invalidatePath("/api/projects"); projects.refetch();
    select(result.id);
    setEditingData(true);
  }
  return <section className="project-intake" aria-label="项目与数据">
    <div className="project-intake-heading"><span className="project-intake-icon"><FolderOpen size={23}/></span><div><h2>项目与数据</h2>
    <p>为本次分析选择项目，输入数据可在项目内重复使用。</p></div><span className="project-intake-step">分析准备</span></div>
    {projects.status === "error" ? <p role="alert">项目读取失败。<button className="btn btn-secondary" onClick={projects.refetch}>重新读取</button></p> :
      <div className="project-intake-controls">
        <div className="project-intake-picker"><span id="current-project-label">当前项目</span>
          <Select ariaLabel="当前项目" value={projectId} disabled={projects.status !== "ready"}
            placeholder={projects.status === "loading" ? "正在读取项目…" : "选择一个项目开始分析"}
            options={items.map(project => ({value: project.id, label: project.name}))} onChange={select}/>
        </div>
        <button className="project-intake-button project-intake-secondary" onClick={() => setCreating(true)}><Plus size={17}/>新建项目</button>
        <button className="project-intake-button project-intake-primary" disabled={!selected} aria-expanded={editingData} onClick={() => setEditingData(!editingData)}>{editingData ? <ChevronUp size={17}/> : <Upload size={17}/>} {editingData ? "收起数据管理" : "上传与管理数据集"}</button>
      </div>}
    <div className="project-intake-summary">{selected ? <><CheckCircle2 size={15}/><span>当前分析将关联至 <strong>{selected.name}</strong></span></> : <><FolderOpen size={15}/><span>还没有项目？新建项目后即可上传数据并开始分析。</span></>}</div>
    {message && <p className="project-intake-success" role="status">{message}</p>}
    {selected && <ProjectDatasetSummary key={`dataset-${selected.id}`} projectId={selected.id} revision={revision} />}
    {selected && <InputValidationStatus key={`validation-${selected.id}`} projectId={selected.id} revision={revision}/>}
    {editingData && selected && <AssetUpload key={`upload-${selected.id}`} projectId={selected.id} onSuccess={() => { apiClient.invalidatePath("/api/projects"); projects.refetch(); setMessage("数据已保存，可以选择下方分析。"); setRevision(value => value + 1); }}/>}
    <ProjectForm open={creating} onClose={() => setCreating(false)} onSubmit={create}/>
  </section>;
}
