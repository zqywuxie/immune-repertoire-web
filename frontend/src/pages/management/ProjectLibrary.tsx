import { useEffect, useState } from "react";
import { Plus, Search, FolderOpen, Boxes, Database, FileText } from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { projectCatalogNavigationState } from "../../features/projects/catalogNavigation";
import { useMediaQuery } from "../../shared/hooks/useMediaQuery";
import { useApi } from "../../shared/hooks/useApi";
import { apiClient } from "../../shared/api/client";
import { listProjects, getProjectStatistics, type ProjectListParams } from "../../shared/api/projects";
import { PageHeader } from "../../shared/components/PageHeader";
import { SearchBar } from "../../shared/components/SearchBar";
import { Select } from "../../shared/components/Select";
import { Pagination } from "../../shared/components/Pagination";
import { ProjectList } from "../../features/projects/ProjectList";
import { ProjectForm } from "../../features/projects/ProjectForm";
import { MetricCard } from "../../shared/components/MetricCard";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import type { ProjectCreate } from "../../shared/types/domain";
import "../../features/projects/ProjectCatalog.css";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const sorts = [
  { value: "updated_desc", label: "最近更新" }, { value: "created_desc", label: "最近创建" },
  { value: "name_asc", label: "名称升序" }, { value: "name_desc", label: "名称降序" },
];
export function ProjectLibrary() {
  const [query, setQuery] = useSearchParams();
  const mobile = useMediaQuery("(max-width: 768px)");
  const search = query.get("q") || "";
  const status = query.get("status") || "";
  const page = Math.max(1, Math.floor(Number(query.get("page")) || 1));
  const sort = (sorts.some(item => item.value === query.get("sort")) ? query.get("sort") : "created_desc") as NonNullable<ProjectListParams["sort"]>;
  const layout = query.get("layout") === "list" ? "list" : "cards";
  const [draft, setDraft] = useState(search);
  const [showNewProject, setShowNewProject] = useState(false);
  const [createdNotice, setCreatedNotice] = useState("");
  const [createdId, setCreatedId] = useState("");
  const location = useLocation();
  const projects = useApi(() => listProjects({ search, status, sort, page, pageSize: 24 }), [search, status, sort, page]);
  const statistics = useApi(() => getProjectStatistics(), []);
  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const pagination = projects.status === "ready" ? projects.data.pagination : undefined;
  const error = projects.status === "error" ? projects.error : null;
  const stats = statistics.status === "ready" ? statistics.data : null;
  useEffect(() => setDraft(search), [search]);
  useEffect(() => {
    if (draft.trim() === search) return;
    const timer = setTimeout(() => setQuery(previous => { const next = new URLSearchParams(previous); draft.trim() ? next.set("q", draft.trim()) : next.delete("q"); next.delete("page"); return next; }, { replace: true }), 300);
    return () => clearTimeout(timer);
  }, [draft, search, setQuery]);
  useEffect(() => {
    if (pagination && page > Math.max(1, pagination.total_pages)) setQuery(previous => { const next = new URLSearchParams(previous); next.set("page", String(Math.max(1, pagination.total_pages))); return next; }, { replace: true });
  }, [pagination, page, setQuery]);
  function update(key: string, value: string) {
    setQuery(previous => { const next = new URLSearchParams(previous); value ? next.set(key, value) : next.delete(key); if (key !== "page" && key !== "layout") next.delete("page"); return next; });
  }
  async function handleCreateProject(data: ProjectCreate) {
    const response = await fetch(`${API_BASE}/api/projects`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    if (!response.ok) { const reason = await response.json().catch(() => ({})); throw new Error(reason.detail || reason.message || "创建项目失败"); }
    const created = await response.json();
    setCreatedId(typeof created.id === "string" ? created.id : "");
    apiClient.invalidatePath("/api/projects");
    setCreatedNotice(`项目“${data.name}”已创建${search || status ? "；当前筛选可能不包含新项目" : ""}。`);
    statistics.refetch();
    if (page !== 1) update("page", "1"); else projects.refetch();
  }
  const hasFilters = !!search || !!status;
  const statisticsCards = <div className="project-catalog-statistics" aria-label="全部项目统计">{stats ? <><MetricCard icon={FolderOpen} label="项目总数" value={stats.project_count} color="var(--accent)" /><MetricCard icon={Boxes} label="进行中" value={stats.status_counts.active || 0} color="var(--success)" /><MetricCard icon={FileText} label="文件总数" value={stats.file_count} color="var(--warning)" /><MetricCard icon={Database} label="输入样本条目" value={stats.input_sample_count} color="var(--info)" /></> : [1,2,3,4].map(number => <Skeleton key={number} height="80px" />)}</div>;
  return <>
    <PageHeader title="项目管理" subtitle="创建和管理免疫组库分析项目"><button className="btn btn-primary" onClick={() => setShowNewProject(true)}><Plus size={16} />新建项目</button></PageHeader>
    {createdNotice && <div className="project-catalog-created"><p role="status">{createdNotice}</p>{createdId && <Link className="btn btn-primary" to={`/management/projects/${encodeURIComponent(createdId)}`} state={projectCatalogNavigationState(location)}>打开新项目</Link>}</div>}
    {statistics.status === "error" ? <div className="project-catalog-error" role="alert">项目统计暂时无法读取：{statistics.error}<button className="btn btn-secondary" onClick={statistics.refetch}>重新读取统计</button></div> : mobile ? <details className="project-catalog-stats-summary"><summary>全部项目统计{stats ? ` · ${stats.project_count} 个项目` : ""}</summary>{statisticsCards}</details> : statisticsCards}
    <div className="project-catalog-toolbar"><SearchBar placeholder="搜索项目名称或机构…" value={draft} onChange={setDraft} onClear={() => setDraft("")} />
      <Select value={status} ariaLabel="项目状态筛选" options={[{value:"",label:"全部状态"},{value:"active",label:"进行中"},{value:"paused",label:"已暂停"},{value:"archived",label:"已归档"}]} onChange={value => update("status",value)} />
      <Select value={sort} ariaLabel="项目排序" options={sorts} onChange={value => update("sort",value)} />
      <div className="project-catalog-layout" role="group" aria-label="项目显示方式"><button type="button" className="btn btn-secondary" aria-pressed={layout === "cards"} onClick={() => update("layout","cards")}>卡片</button><button type="button" className="btn btn-secondary" aria-pressed={layout === "list"} onClick={() => update("layout","list")}>列表</button></div>
      {hasFilters && <button className="btn btn-secondary" onClick={() => { setDraft(""); setQuery(previous => { const next = new URLSearchParams(previous); ["q","status","page"].forEach(key => next.delete(key)); return next; }); }}>清除筛选</button>}
    </div>
    {error ? <div className="project-catalog-error" role="alert">{error}<button className="btn btn-secondary" onClick={projects.refetch}>重新读取项目</button></div> : <>
      {projects.status === "ready" && <p className="project-catalog-muted">当前页 {projectList.length} 个项目 · 匹配 {pagination?.total ?? projectList.length} 个项目；上方为全部项目统计。</p>}
      {projects.status === "ready" && projectList.length === 0 ? <EmptyState icon={hasFilters ? Search : FolderOpen} title={hasFilters ? "没有符合条件的项目" : "暂无项目"} description={hasFilters ? "请调整搜索关键词或筛选条件。" : "创建第一个项目，开始免疫组库分析。"} action={hasFilters ? undefined : {label:"创建项目",onClick:() => setShowNewProject(true)}} /> : <ProjectList projects={projectList} loading={projects.status === "loading" || projects.status === "idle"} layout={layout} />}
      {projects.status === "ready" && pagination && <Pagination pagination={pagination} onPageChange={value => update("page",String(value))} />}
    </>}
    <ProjectForm open={showNewProject} onClose={() => setShowNewProject(false)} onSubmit={handleCreateProject} title="新建项目" />
  </>;
}
