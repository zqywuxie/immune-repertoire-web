import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listProjects, getProject } from "../../shared/api/projects";
import { useApi } from "../../shared/hooks/useApi";
import { Select } from "../../shared/components/Select";
import "./ProjectCatalog.css";

export function ProjectPicker({ value, onChange, label = "项目", allowAll = false, autoSelectFirst = false, disabled = false, onAvailability, revision = 0 }: {
  value: string; onChange: (value: string) => void; label?: string;
  allowAll?: boolean; autoSelectFirst?: boolean; disabled?: boolean;
  onAvailability?: (available: boolean) => void; revision?: number;
}) {
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const initialized = useRef(false);
  useEffect(() => {
    if (draft.trim() === search) return;
    const timer = setTimeout(() => { setSearch(draft.trim()); setPage(1); }, 300);
    return () => clearTimeout(timer);
  }, [draft, search]);
  const catalog = useApi(() => listProjects({ view: "selector", search, page, pageSize: 20 }), [search, page, revision]);
  const projects = catalog.status === "ready" ? catalog.data.projects : [];
  const present = projects.some(project => project.id === value);
  const selected = useApi(() => getProject(value, { summaryOnly: true }), [value, revision], !!value && catalog.status === "ready" && !present);
  const pinned = selected.status === "ready" && selected.data?.id === value ? selected.data : null;
  const pagination = catalog.status === "ready" ? catalog.data.pagination : undefined;
  useEffect(() => {
    if (!autoSelectFirst || initialized.current || catalog.status !== "ready" || search || page !== 1) return;
    initialized.current = true;
    if (!value && projects[0]) onChange(projects[0].id);
  }, [autoSelectFirst, catalog.status, projects, value, onChange, search, page]);
  useEffect(() => {
    if (pagination && page > Math.max(1, pagination.total_pages)) setPage(Math.max(1, pagination.total_pages));
  }, [pagination, page]);
  useEffect(() => {
    if (catalog.status === "ready" && !search && page === 1) onAvailability?.((pagination?.total ?? projects.length) > 0);
  }, [catalog.status, pagination, projects, search, page, onAvailability]);
  const options = [
    ...(allowAll ? [{ value: "", label: "全部项目" }] : []),
    ...(value && !present ? [{ value, label: pinned?.name || (selected.status === "error" ? "当前项目（名称读取失败）" : "当前项目（正在读取名称…）") }] : []),
    ...projects.map(project => ({ value: project.id, label: project.name })),
  ];
  return <div className="project-picker">
    <label className="project-picker-search"><span>{label}</span><input className="input" aria-label={`搜索${label}`} placeholder="按项目名称或机构搜索" value={draft} disabled={disabled} onChange={event => setDraft(event.target.value)} /></label>
    <Select value={value} options={options} ariaLabel={label} placeholder="请选择项目…" disabled={disabled} onChange={onChange} />
    {catalog.status === "loading" && <span className="project-catalog-muted" role="status">正在读取项目…</span>}
    {catalog.status === "error" && <div role="alert" className="project-catalog-error">项目加载失败：{catalog.error}<button className="btn btn-secondary" type="button" onClick={catalog.refetch}>重新读取项目</button></div>}
    {value && !present && selected.status === "error" && <div role="alert" className="project-catalog-error">当前项目名称读取失败：{selected.error}<button className="btn btn-secondary" type="button" onClick={selected.refetch}>重新读取当前项目</button></div>}
    {catalog.status === "ready" && !projects.length && <p className="project-catalog-muted">{search ? "没有符合条件的项目，请调整搜索。" : "先建立一个项目，用于保存数据、分析参数和结果。"}{!search && <Link to="/management/projects">创建项目</Link>}</p>}
    {pagination && pagination.total_pages > 1 && <div className="project-picker-pages"><span>共 {pagination.total} 个匹配项目 · 第 {page} / {pagination.total_pages} 页</span><div><button type="button" className="btn btn-secondary" disabled={disabled || page <= 1 || catalog.status !== "ready"} aria-label={`${label}上一页`} onClick={() => setPage(previous => previous - 1)}>上一页</button><button type="button" className="btn btn-secondary" disabled={disabled || page >= pagination.total_pages || catalog.status !== "ready"} aria-label={`${label}下一页`} onClick={() => setPage(previous => previous + 1)}>下一页</button></div></div>}
  </div>;
}
