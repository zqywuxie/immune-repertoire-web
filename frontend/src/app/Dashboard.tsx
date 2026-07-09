import { useState, useMemo } from "react";
import { Boxes, FlaskConical, Activity, Clock, ArrowRight, Database, Zap, Plus, FolderOpen } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useApi } from "../shared/hooks/useApi";
import { listProjects } from "../shared/api/projects";
import { listJobs } from "../shared/api/jobs";
import { MetricCard } from "../shared/components/MetricCard";
import { PageHeader } from "../shared/components/PageHeader";
import { ProjectList } from "../features/projects/ProjectList";
import { ProjectForm } from "../features/projects/ProjectForm";
import { StatusBadge } from "../shared/components/StatusBadge";
import { Card } from "../shared/components/Card";
import { Skeleton } from "../shared/components/Skeleton";
import { EmptyState } from "../shared/components/EmptyState";
import { SearchBar } from "../shared/components/SearchBar";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "";

export function Dashboard() {
  const navigate = useNavigate();
  const projects = useApi(() => listProjects(), []);
  const jobs = useApi(() => listJobs({ limit: 10 }), []);

  const [showNewProject, setShowNewProject] = useState(false);
  const [searchName, setSearchName] = useState("");
  const [searchInstitution, setSearchInstitution] = useState("");

  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const jobList = jobs.status === "ready" ? jobs.data.jobs : [];

  const filteredProjects = useMemo(() => {
    if (!searchName && !searchInstitution) return projectList;
    return projectList.filter((p) => {
      const nameMatch = !searchName || p.name.toLowerCase().includes(searchName.toLowerCase());
      const instMatch = !searchInstitution || (p.institution || "").toLowerCase().includes(searchInstitution.toLowerCase());
      return nameMatch && instMatch;
    });
  }, [projectList, searchName, searchInstitution]);

  const loadingProjects = projects.status === "loading";
  const loadingJobs = jobs.status === "loading";
  const projectsError = projects.status === "error" ? projects.error : null;
  const jobsError = jobs.status === "error" ? jobs.error : null;

  const stats = {
    projects: projectList.length,
    results: projectList.reduce((sum, p) => sum + Number(p.result_count || 0), 0),
    activeJobs: jobList.filter((j) => j.status === "running" || j.status === "queued").length,
  };

  const quickActions = [
    { icon: Database, label: "Browse Assets", to: "/database", color: "var(--accent)" },
    { icon: Zap, label: "Submit Job", to: "/scripthub", color: "var(--warning)" },
    { icon: Clock, label: "View Jobs", to: "/scripthub", color: "var(--success)" },
  ];

  const handleCreateProject = async (data: { name: string; institution?: string; cooperation_level?: string; description?: string; status: string }) => {
    await fetch(`${API_BASE}/api/projects`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }).then((r) => {
      if (!r.ok) return r.json().then((e) => { throw new Error(e.detail || e.message || "Failed to create project"); });
      return r.json();
    });
    projects.refetch();
  };

  const latestActivity = jobList.slice(0, 5);

  return (
    <>
      <PageHeader title="Immune Repertoire Platform" subtitle="Database & ScriptHub analysis workspace" />

      {/* Error banners */}
      {projectsError && <ErrorBanner message={projectsError} />}
      {jobsError && <ErrorBanner message={jobsError} />}

      {/* Metric cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "var(--spacing-lg)" }}>
        {loadingProjects ? (
          <>
            <Skeleton height="100px" />
            <Skeleton height="100px" />
            <Skeleton height="100px" />
          </>
        ) : (
          <>
            <MetricCard icon={Boxes} label="Projects" value={stats.projects} color="var(--accent)" />
            <MetricCard icon={FlaskConical} label="Results" value={stats.results} color="var(--success)" />
            <MetricCard icon={Activity} label="Active Jobs" value={stats.activeJobs} color="var(--warning)" />
          </>
        )}
      </div>

      {/* Quick actions */}
      <div style={{ display: "flex", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
        {quickActions.map((action) => (
          <button key={action.to} onClick={() => navigate(action.to)} style={{
            display: "inline-flex", alignItems: "center", gap: "var(--spacing-sm)",
            padding: "10px 20px", borderRadius: "var(--radius-pill)",
            background: `${action.color}12`, color: action.color,
            border: `1px solid ${action.color}30`, fontWeight: 500, fontSize: "0.875rem",
          }}>
            <action.icon size={16} />{action.label}<ArrowRight size={14} />
          </button>
        ))}
      </div>

      {/* Split: projects + latest activity */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(360px, 100%), 1fr))", gap: "var(--spacing-lg)" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--spacing-md)" }}>
            <h3 style={{ margin: 0 }}>Projects</h3>
            <div style={{ display: "flex", gap: "var(--spacing-sm)" }}>
              <SearchBar
                placeholder="Search by name…"
                value={searchName}
                onChange={setSearchName}
                onClear={() => setSearchName("")}
              />
              <button onClick={() => setShowNewProject(true)} style={{
                display: "inline-flex", alignItems: "center", gap: "4px",
                padding: "7px 16px", borderRadius: "var(--radius-pill)",
                background: "var(--accent)", color: "#fff", fontWeight: 500,
                fontSize: "0.85rem", border: "none", cursor: "pointer",
              }}>
                <Plus size={16} /> New Project
              </button>
            </div>
          </div>

          {filteredProjects.length === 0 && !loadingProjects && (searchName || searchInstitution) ? (
            <EmptyState icon={FolderOpen} title="No matching projects" description="Try a different search term." />
          ) : (
            <ProjectList projects={filteredProjects} loading={loadingProjects} />
          )}
        </div>

        <div>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "var(--spacing-md)" }}>
            <h3 style={{ margin: 0 }}>Latest Activity</h3>
          </div>
          <Card>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
              {loadingJobs ? (
                [1, 2, 3].map((i) => <Skeleton key={i} height="50px" variant="text" />)
              ) : latestActivity.length === 0 ? (
                <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", textAlign: "center", padding: "var(--spacing-lg) 0" }}>
                  No recent activity. Submit your first job from ScriptHub.
                </p>
              ) : (
                latestActivity.map((job) => (
                  <div key={job.job_id || job.id} style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    gap: "var(--spacing-sm)", padding: "var(--spacing-sm) 0",
                    borderBottom: "1px solid var(--separator)",
                  }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: "0.85rem", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {job.module || job.job_type}
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "2px" }}>
                        {job.stage || job.detail || ""}
                      </div>
                    </div>
                    <StatusBadge status={job.status} />
                  </div>
                ))
              )}
              {latestActivity.length > 0 && (
                <button onClick={() => navigate("/scripthub")} style={{
                  padding: "8px", borderRadius: "var(--radius-control)", color: "var(--accent)",
                  fontWeight: 500, fontSize: "0.82rem", textAlign: "center", width: "100%",
                }}>
                  View all jobs →
                </button>
              )}
            </div>
          </Card>
        </div>
      </div>

      {/* New project modal */}
      <ProjectForm open={showNewProject} onClose={() => setShowNewProject(false)} onSubmit={handleCreateProject} />
    </>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      padding: "var(--spacing-md) var(--spacing-lg)", borderRadius: "var(--radius-panel)",
      background: "var(--danger)", color: "#fff", fontSize: "0.85rem", fontWeight: 500,
    }}>
      ⚠ {message}
    </div>
  );
}
