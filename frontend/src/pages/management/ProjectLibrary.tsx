import { useState, useMemo } from "react";
import { Plus, Search, FolderOpen, Boxes, FlaskConical, Layers, Database, AlertTriangle, Building2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
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
          "Failed to create project"
      );
    }
    projects.refetch();
  };

  const hasFilters = search || statusFilter;

  return (
    <>
      <PageHeader title="Project Library" subtitle="Create and manage immune repertoire analysis projects">
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
          New Project
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
          <MetricCard icon={FolderOpen} label="Total Projects" value={stats.total} color="var(--accent)" />
          <MetricCard icon={Boxes} label="Active" value={stats.active} color="var(--success)" />
          <MetricCard icon={FlaskConical} label="Total Assets" value={stats.totalAssets} color="var(--warning)" />
          <MetricCard icon={Database} label="Samples" value={stats.totalSamples} color="var(--info)" />
        </div>
      )}

      {/* Filter toolbar */}
      <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
        <SearchBar
          placeholder="Search by project name or institution…"
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
          <option value="">All Statuses</option>
          <option value="active">Active</option>
          <option value="paused">Paused</option>
          <option value="archived">Archived</option>
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
            <X size={14} /> Clear Filters
          </button>
        )}
        <span style={{ marginLeft: "auto", fontSize: "0.8rem", color: "var(--text-tertiary)" }}>
          {filteredProjects.length} of {projectList.length} project{projectList.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Project list */}
      {filteredProjects.length === 0 && !loading ? (
        <EmptyState
          icon={hasFilters ? Search : FolderOpen}
          title={hasFilters ? "No matching projects" : "No projects yet"}
          description={hasFilters ? "Try a different search term or adjust your filters." : "Create your first project to get started with immune repertoire analysis."}
          action={hasFilters ? undefined : { label: "Create Project", to: "" }}
        />
      ) : (
        <ProjectList projects={filteredProjects} loading={loading} />
      )}

      {/* Create project sheet */}
      <ProjectForm
        open={showNewProject}
        onClose={() => setShowNewProject(false)}
        onSubmit={handleCreateProject}
        title="New Project"
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
