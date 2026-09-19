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
  const projects = useApi(listProjects, []);
  const [query, setQuery] = useSearchParams();
  const [creating, setCreating] = useState(false);
  const [editingData, setEditingData] = useState(false);
  const [revision, setRevision] = useState(0);
  const [message, setMessage] = useState("");
  const projectId = query.get("project") || "";
  const items = projects.status === "ready" ? projects.data.projects : [];
  const selected = items.find(item => item.id === projectId);
  function select(id: string) {
    setEditingData(false); setMessage("");
    setQuery(previous => { const next = new URLSearchParams(previous); next.delete("asset_set"); if (id) next.set("project", id); else next.delete("project"); return next; });
  }
  async function create(data: ProjectCreate) {
    const result = await apiClient.post<ProjectSummary>("/api/projects", data);
    apiClient.invalidatePath("/api/projects"); projects.refetch();
    select(result.id);
    setEditingData(true);
  }
  return <section className="card" aria-label="项目与数据" style={{ padding: "var(--spacing-lg)" }}>
    <h2>项目与数据</h2>
    <p>先选择项目，再上传数据。四类输入按分析需要提供，可在同一项目中复用。</p>
    {projects.status === "error" ? <p role="alert">项目读取失败。<button className="btn btn-secondary" onClick={projects.refetch}>重新读取</button></p> :
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <label className="field-label">当前项目<select className="select" value={projectId} disabled={projects.status !== "ready"} onChange={event => select(event.target.value)}>
          <option value="">{projects.status === "loading" ? "正在读取项目…" : "请选择项目"}</option>
          {items.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}
        </select></label>
        <button className="btn btn-secondary" onClick={() => setCreating(true)}>新建项目</button>
        <button className="btn btn-secondary" disabled={!selected} aria-expanded={editingData} onClick={() => setEditingData(!editingData)}>{editingData ? "收起数据管理" : "上传与管理数据集"}</button>
      </div>}
    {message && <p role="status">{message}</p>}
    {selected && <InputValidationStatus key={selected.id} projectId={selected.id} revision={revision}/>}
    {editingData && selected && <AssetUpload key={selected.id} projectId={selected.id} onSuccess={() => { apiClient.invalidatePath("/api/projects"); projects.refetch(); setMessage("数据已保存，可以选择下方分析。"); setRevision(value => value + 1); }}/>} 
    <ProjectForm open={creating} onClose={() => setCreating(false)} onSubmit={create}/>
  </section>;
}
