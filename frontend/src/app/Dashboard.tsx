import { Boxes, FlaskConical, Activity } from "lucide-react";
import { useApi } from "../shared/hooks/useApi";
import { listProjects } from "../shared/api/projects";
import { listJobs } from "../shared/api/jobs";
import { MetricCard } from "../shared/components/MetricCard";
import { PageHeader } from "../shared/components/PageHeader";
import { ProjectList } from "../features/projects/ProjectList";
import { JobList } from "../features/jobs/JobList";
import { useNavigate } from "react-router-dom";

export function Dashboard() {
  const navigate = useNavigate();
  const projects = useApi(() => listProjects(), []);
  const jobs = useApi(() => listJobs({ limit: 5 }), []);

  const projectList =
    projects.status === "ready" ? projects.data.projects : [];
  const jobList = jobs.status === "ready" ? jobs.data.jobs : [];

  const stats = {
    projects: projectList.length,
    results: projectList.reduce(
      (sum, p) => sum + Number(p.result_count || 0),
      0
    ),
    activeJobs: jobList.filter(
      (j) => j.status === "running" || j.status === "queued"
    ).length,
  };

  return (
    <>
      <PageHeader
        title="Immune Repertoire Platform"
        subtitle="Database & ScriptHub analysis workspace"
      />

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "var(--spacing-lg)",
        }}
      >
        <MetricCard icon={Boxes} label="Projects" value={stats.projects} color="var(--accent)" />
        <MetricCard
          icon={FlaskConical}
          label="Results"
          value={stats.results}
          color="var(--success)"
        />
        <MetricCard
          icon={Activity}
          label="Active Jobs"
          value={stats.activeJobs}
          color="var(--warning)"
        />
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
          <h3 style={{ margin: 0 }}>Recent Jobs</h3>
          <button
            onClick={() => navigate("/scripthub")}
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
        <JobList
          jobs={jobList}
          loading={jobs.status === "loading"}
          emptyLabel="No jobs yet. Submit one from ScriptHub."
        />
      </div>
    </>
  );
}
