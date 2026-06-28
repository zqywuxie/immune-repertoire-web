import { Activity, Boxes, Database, FlaskConical, GitBranch, ListChecks } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { listJobs } from "../shared/api/jobs";
import { listProjects } from "../shared/api/projects";
import type { JobSummary, ProjectSummary } from "../shared/types/domain";

type LoadState = "idle" | "loading" | "ready" | "error";

export function App() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoadState("loading");
    Promise.all([listProjects(), listJobs({ limit: 8 })])
      .then(([projectPayload, jobPayload]) => {
        if (cancelled) return;
        setProjects(projectPayload.projects || []);
        setJobs(jobPayload.jobs || []);
        setLoadState("ready");
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load API data");
        setLoadState("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stats = useMemo(() => {
    const resultCount = projects.reduce((sum, project) => sum + Number(project.result_count || 0), 0);
    const sampleCount = projects.reduce((sum, project) => sum + Number(project.sample_count || 0), 0);
    const runningJobs = jobs.filter((job) => job.status === "running" || job.status === "queued").length;
    return {
      projects: projects.length,
      resultCount,
      sampleCount,
      runningJobs
    };
  }, [projects, jobs]);

  return (
    <main className="shell">
      <aside className="rail" aria-label="Primary navigation">
        <div className="brand-mark">IR</div>
        <button className="rail-button is-active" aria-label="Projects">
          <Boxes size={20} />
        </button>
        <button className="rail-button" aria-label="Jobs">
          <Activity size={20} />
        </button>
        <button className="rail-button" aria-label="Data">
          <Database size={20} />
        </button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Migration console</p>
            <h1>Immune Repertoire Platform</h1>
          </div>
          <div className="status-pill">
            <GitBranch size={16} />
            Flask API bridge
          </div>
        </header>

        <section className="hero-band">
          <div>
            <p className="eyebrow">Phase 1</p>
            <h2>Frontend shell for project, asset, job, and result workflows</h2>
          </div>
          <div className="hero-grid" aria-label="Platform summary">
            <Metric label="Projects" value={stats.projects} />
            <Metric label="Samples" value={stats.sampleCount} />
            <Metric label="Results" value={stats.resultCount} />
            <Metric label="Active jobs" value={stats.runningJobs} />
          </div>
        </section>

        {loadState === "error" && <div className="notice">{error}</div>}

        <section className="split">
          <div className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Projects</p>
                <h3>Recent workspace inventory</h3>
              </div>
              <FlaskConical size={20} />
            </div>
            <div className="table-shell">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Assets</th>
                    <th>Results</th>
                  </tr>
                </thead>
                <tbody>
                  {projects.slice(0, 8).map((project) => (
                    <tr key={project.id}>
                      <td>{project.name}</td>
                      <td>{project.status}</td>
                      <td>{Object.values(project.asset_counts || {}).reduce((sum, count) => sum + count, 0)}</td>
                      <td>{project.result_count || 0}</td>
                    </tr>
                  ))}
                  {loadState === "loading" && <PlaceholderRows columns={4} rows={4} />}
                  {loadState === "ready" && projects.length === 0 && (
                    <tr>
                      <td colSpan={4}>No projects returned by the API.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Jobs</p>
                <h3>Unified task stream</h3>
              </div>
              <ListChecks size={20} />
            </div>
            <div className="job-list">
              {jobs.map((job) => (
                <article className="job-row" key={job.id}>
                  <div>
                    <strong>{job.module || job.job_type}</strong>
                    <span>{job.stage || job.detail || job.status}</span>
                  </div>
                  <meter min={0} max={100} value={Number(job.progress || 0)} />
                </article>
              ))}
              {loadState === "loading" && Array.from({ length: 4 }).map((_, index) => <div className="job-row skeleton" key={index} />)}
              {loadState === "ready" && jobs.length === 0 && <p className="empty">No jobs returned by the API.</p>}
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PlaceholderRows({ columns, rows }: { columns: number; rows: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <tr key={rowIndex}>
          {Array.from({ length: columns }).map((__, columnIndex) => (
            <td key={columnIndex}>
              <span className="line-skeleton" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}
