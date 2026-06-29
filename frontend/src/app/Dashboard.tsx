import { Boxes, FlaskConical, Activity, Clock, ArrowRight, Database, Zap } from "lucide-react";
import { useApi } from "../shared/hooks/useApi";
import { listProjects } from "../shared/api/projects";
import { listJobs } from "../shared/api/jobs";
import { MetricCard } from "../shared/components/MetricCard";
import { PageHeader } from "../shared/components/PageHeader";
import { ProjectList } from "../features/projects/ProjectList";
import { StatusBadge } from "../shared/components/StatusBadge";
import { Card } from "../shared/components/Card";
import { useNavigate } from "react-router-dom";

export function Dashboard() {
  const navigate = useNavigate();
  const projects = useApi(() => listProjects(), []);
  const jobs = useApi(() => listJobs({ limit: 10 }), []);

  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const jobList = jobs.status === "ready" ? jobs.data.jobs : [];

  const stats = {
    projects: projectList.length,
    results: projectList.reduce((sum, p) => sum + Number(p.result_count || 0), 0),
    activeJobs: jobList.filter((j) => j.status === "running" || j.status === "queued").length,
  };

  // Quick actions config
  const quickActions = [
    { icon: Database, label: "Browse Assets", to: "/database", color: "var(--accent)" },
    { icon: Zap, label: "Submit Job", to: "/scripthub", color: "var(--warning)" },
    { icon: Clock, label: "View Jobs", to: "/scripthub", color: "var(--success)" },
  ];

  const latestActivity = jobList.slice(0, 5);

  return (
    <>
      <PageHeader
        title="Immune Repertoire Platform"
        subtitle="Database & ScriptHub analysis workspace"
      />

      {/* Metric cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "var(--spacing-lg)",
        }}
      >
        <MetricCard icon={Boxes} label="Projects" value={stats.projects} color="var(--accent)" />
        <MetricCard icon={FlaskConical} label="Results" value={stats.results} color="var(--success)" />
        <MetricCard icon={Activity} label="Active Jobs" value={stats.activeJobs} color="var(--warning)" />
      </div>

      {/* Quick actions */}
      <div style={{ display: "flex", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
        {quickActions.map((action) => (
          <button
            key={action.to}
            onClick={() => navigate(action.to)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--spacing-sm)",
              padding: "10px 20px",
              borderRadius: "var(--radius-pill)",
              background: `${action.color}12`,
              color: action.color,
              border: `1px solid ${action.color}30`,
              fontWeight: 500,
              fontSize: "0.875rem",
              transition: "all var(--duration-fast)",
            }}
          >
            <action.icon size={16} />
            {action.label}
            <ArrowRight size={14} />
          </button>
        ))}
      </div>

      {/* Split: projects + latest activity */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 2fr) minmax(300px, 1fr)",
          gap: "var(--spacing-lg)",
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "var(--spacing-md)",
            }}
          >
            <h3 style={{ margin: 0 }}>Projects</h3>
            <button
              onClick={() => navigate("/database")}
              style={{
                padding: "6px 14px",
                borderRadius: "var(--radius-pill)",
                color: "var(--accent)",
                fontWeight: 500,
                fontSize: "0.85rem",
              }}
            >
              View all →
            </button>
          </div>
          <ProjectList />
        </div>

        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "var(--spacing-md)",
            }}
          >
            <h3 style={{ margin: 0 }}>Latest Activity</h3>
          </div>
          <Card>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
              {latestActivity.length === 0 && (
                <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", textAlign: "center", padding: "var(--spacing-lg) 0" }}>
                  No recent activity. Submit your first job from ScriptHub.
                </p>
              )}
              {latestActivity.map((job) => (
                <div
                  key={job.job_id || job.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "var(--spacing-sm)",
                    padding: "var(--spacing-sm) 0",
                    borderBottom: "1px solid var(--separator)",
                  }}
                >
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
              ))}
              {latestActivity.length > 0 && (
                <button
                  onClick={() => navigate("/scripthub")}
                  style={{
                    padding: "8px",
                    borderRadius: "var(--radius-control)",
                    color: "var(--accent)",
                    fontWeight: 500,
                    fontSize: "0.82rem",
                    textAlign: "center",
                    width: "100%",
                  }}
                >
                  View all jobs →
                </button>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
