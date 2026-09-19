import { useState, useMemo } from "react";
import { Plus, Search, FolderOpen, Boxes, FlaskConical, Layers, Database, AlertTriangle, Building2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
import { apiClient } from "../../shared/api/client";
import { listProjects } from "../../shared/api/projects";
import { PageHeader } from "../../shared/components/PageHeader";
import { SearchBar } from "../../shared/components/SearchBar";
import { ProjectList } from "../../features/projects/ProjectList";
import { ProjectForm } from "../../features/projects/ProjectForm";
import { MetricCard } from "../../shared/components/MetricCard";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { StatusBadge } from "../../shared/components/StatusBadge";
import type { ProjectCreate } from "../../shared/types/domain";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export function ProjectLibrary() {
  const navigate = useNavigate();
  const projects = useApi(() => listProjects(), []);
  const [showNewProject, setShowNewProject] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const loading = projects.status === "loading";
  const error = projects.status === "error" ? projects.error : null;

  // Compute stats
  const stats = useMemo(() => {
    const active = projectList.filter((p) => p.status === "active").length;
    const archived = projectList.filter((p) => p.status === "archived").length;
    const totalAssets = projectList.reduce((s, p) => s + Object.values(p.asset_counts || {}).reduce((a: number, c: any) => a + Number(c), 0), 0);
    const totalSamples = projectList.reduce((s, p) => s + (Number(p.sample_count) || 0), 0);
    return { active, archived, totalAssets, totalSamples, total: projectList.length };
  }, [projectList]);

  // Filter projects
  const filteredProjects = useMemo(() => {
    let result = projectList;
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.institution || "").toLowerCase().includes(q)
      );
    }
    if (statusFilter) {
      result = result.filter((p) => p.status === statusFilter);
    }
    return result;
  }, [projectList, search, statusFilter]);

  const handleCreateProject = async (data: ProjectCreate) => {
    const r = await fetch(`${API_BASE}/api/projects`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(
        (e as { detail?: string }).detail ||
          (e as { message?: string }).message ||
          "创建项目失败"
      );
    }
    apiClient.invalidatePath("/api/projects");
    projects.refetch();
  };

  const hasFilters = search || statusFilter;

  return (
    <>
      <PageHeader title="项目管理" subtitle="创建和管理免疫组库分析项目">
        <button
          onClick={() => setShowNewProject(true)}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "10px 20px",
            borderRadius: "var(--radius-pill)",
            background: "var(--accent)",
            color: "#fff",
            fontWeight: 500,
            fontSize: "0.875rem",
            border: "none",
            cursor: "pointer",
          }}
        >
          <Plus size={16} />
          新建项目
        </button>
      </PageHeader>

      {/* Error banner */}
      {error && <ErrorBanner message={error} />}

      {/* Stat tiles */}
      {loading ? (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "var(--spacing-md)" }}>
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} height="80px" />)}
        </div>
      ) : !error && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "var(--spacing-md)" }}>
          <MetricCard icon={FolderOpen} label="项目总数" value={stats.total} color="var(--accent)" />
          <MetricCard icon={Boxes} label="进行中" value={stats.active} color="var(--success)" />
          <MetricCard icon={FlaskConical} label="文件总数" value={stats.totalAssets} color="var(--warning)" />
          <MetricCard icon={Database} label="样本" value={stats.totalSamples} color="var(--info)" />
        </div>
      )}

      {/* Filter toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
        <SearchBar
          placeholder="搜索项目名称或机构…"
          value={search}
          onChange={setSearch}
          onClear={() => setSearch("")}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="select"
          style={{ width: "auto", minWidth: "140px" }}
        >
          <option value="">全部状态</option>
          <option value="active">进行中</option>
          <option value="paused">已暂停</option>
          <option value="archived">已归档</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => { setSearch(""); setStatusFilter(""); }}
            style={{
              display: "inline-flex", alignItems: "center", gap: "4px",
              padding: "6px 12px", borderRadius: "var(--radius-pill)",
              border: "1px solid var(--separator)", background: "var(--bg-elevated)",
              color: "var(--text-secondary)", fontSize: "0.8rem", cursor: "pointer",
            }}
          >
            <X size={14} /> 清除筛选
          </button>
        )}
        <span style={{ marginLeft: "auto", fontSize: "0.8rem", color: "var(--text-tertiary)" }}>
          显示 {filteredProjects.length} / {projectList.length} 个项目
        </span>
      </div>

      {/* Project list */}
      {filteredProjects.length === 0 && !loading ? (
        <EmptyState
          icon={hasFilters ? Search : FolderOpen}
          title={hasFilters ? "没有符合条件的项目" : "暂无项目"}
          description={hasFilters ? "请调整搜索关键词或筛选条件。" : "创建第一个项目，开始免疫组库分析。"}
          action={hasFilters ? undefined : { label: "创建项目", onClick: () => setShowNewProject(true) }}
        />
      ) : (
        <ProjectList projects={filteredProjects} loading={loading} />
      )}

      {/* Create project sheet */}
      <ProjectForm
        open={showNewProject}
        onClose={() => setShowNewProject(false)}
        onSubmit={handleCreateProject}
        title="新建项目"
      />
    </>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-sm)",
        padding: "var(--spacing-md) var(--spacing-lg)",
        borderRadius: "var(--radius-panel)",
        background: "var(--danger)",
        color: "#fff",
        fontSize: "0.85rem",
        fontWeight: 500,
        marginBottom: "var(--spacing-lg)",
      }}
    >
      <AlertTriangle size={18} />
      {message}
    </div>
  );
}
