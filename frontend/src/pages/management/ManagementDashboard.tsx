import { useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { usePageActivity } from "../../shared/hooks/usePageActivity";
import { analysisLabel, jobTextLabel } from "../../shared/utils/analysisLabels";
import { taskName } from "../../features/jobs/jobConfiguration";
import "./ManagementDashboard.css";
import { Boxes, FlaskConical, Activity, Database, Users, Settings2, ArrowRight } from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import { listProjects, getProjectStatistics } from "../../shared/api/projects";
import { listJobs } from "../../shared/api/jobs";
import { PageHeader } from "../../shared/components/PageHeader";
import { MetricCard } from "../../shared/components/MetricCard";
import { Card } from "../../shared/components/Card";
import { ProjectList } from "../../features/projects/ProjectList";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { DataReadError } from "../../features/assets/DataReadError";

export function ManagementDashboard() {
  const navigate = useNavigate();
  const projects = useApi(() => listProjects({ pageSize: 4, sort: "updated_desc" }), []);
  const statistics = useApi(() => getProjectStatistics(), []);
  const pageActive = usePageActivity();
  const jobs = useApi(() => listJobs({ limit: 10 }), [], pageActive);
  const hasActiveJobs = jobs.status === "ready" && (jobs.data.counts
    ? (jobs.data.counts.running || 0) + (jobs.data.counts.queued || 0) > 0
    : jobs.data.jobs.some(job => ["running", "queued"].includes(job.status)));
  useEffect(() => {
    if (!pageActive || !hasActiveJobs) return;
    const timer = setTimeout(jobs.refetch, 5000);
    return () => clearTimeout(timer);
  }, [pageActive, hasActiveJobs, jobs.status, jobs.refetch]);

  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const jobList = jobs.status === "ready" ? jobs.data.jobs : [];

  const loadingProjects = projects.status === "loading" || projects.status === "idle";
  const loadingJobs = jobs.status === "loading" || jobs.status === "idle";
  const projectsError = projects.status === "error" ? projects.error : null;
  const jobsError = jobs.status === "error" ? jobs.error : null;

  const stats = {
    projects: statistics.status === "ready" ? statistics.data.project_count : 0,
    results: statistics.status === "ready" ? statistics.data.result_count : 0,
    activeJobs: jobs.status === "ready" ? (jobs.data.counts?.running || 0) + (jobs.data.counts?.queued || 0) : 0,
  };

  const quickActions = [
    {
      icon: Database,
      label: "项目管理",
      description: "整理项目数据与分析结果",
      to: "/management/projects",
      color: "var(--accent)",
    },
    {
      icon: Users,
      label: "样本登记",
      description: "查看与编辑样本信息",
      to: "/management/samples",
      color: "var(--success)",
    },
    {
      icon: Settings2,
      label: "设置",
      description: "设置工作台与显示偏好",
      to: "/management/settings",
      color: "var(--warning)",
    },
  ];

  const recentProjects = projectList.slice(0, 4);
  const latestActivity = jobList.slice(0, 5);

  return (
    <>
      <PageHeader
        title="项目概览"
        subtitle="从项目数据出发，管理样本并跟进分析进度"
      />

      {/* Metric cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "var(--spacing-lg)",
        }}
      >
        {statistics.status === "loading" || statistics.status === "idle" ? (
          <>
            <Skeleton height="100px" />
            <Skeleton height="100px" />
            <Skeleton height="100px" />
          </>
        ) : statistics.status === "error" ? <Card><p role="alert">项目统计暂时无法读取：{statistics.error}</p><button className="btn btn-secondary" onClick={statistics.refetch}>重新读取统计</button></Card> : (
          <>
            <MetricCard icon={Boxes} label="项目数" value={stats.projects} color="var(--accent)" />
            <MetricCard icon={FlaskConical} label="结果数" value={stats.results} color="var(--success)" />
            {loadingJobs ? <Skeleton height="100px" /> : jobsError ? <Card>任务统计暂时无法读取</Card> : <MetricCard icon={Activity} label="进行中的任务" value={stats.activeJobs} color="var(--warning)" />}
          </>
        )}
      </div>

      {/* Quick action cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "var(--spacing-lg)",
        }}
      >
        {quickActions.map((action) => (
          <Card
            key={action.to}
            onClick={() => navigate(action.to)}
            ariaLabel={action.label}
          >
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "var(--spacing-md)",
              }}
            >
              <div
                style={{
                  width: "44px",
                  height: "44px",
                  borderRadius: "var(--radius-control)",
                  background: `color-mix(in srgb, ${action.color} 8%, transparent)`,
                  color: action.color,
                  display: "grid",
                  placeItems: "center",
                  flexShrink: 0,
                }}
              >
                <action.icon size={22} />
              </div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "4px",
                    fontWeight: 600,
                  }}
                >
                  {action.label}
                  <ArrowRight size={14} style={{ color: "var(--text-tertiary)" }} />
                </div>
                <p
                  style={{
                    margin: "4px 0 0",
                    fontSize: "0.8rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  {action.description}
                </p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* Split: recent projects + latest activity */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))",
          gap: "var(--spacing-lg)",
        }}
      >
        {/* Recent projects */}
        <div>
          <h3 style={{ margin: "0 0 var(--spacing-md)" }}>最近项目</h3>
          {loadingProjects ? (
            <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
              {[1, 2].map((i) => (
                <Skeleton key={i} height="100px" />
              ))}
            </div>
          ) : projectsError ? <DataReadError title="最近项目暂时无法读取" message={projectsError} onRetry={projects.refetch} retryLabel="重新读取项目" /> : recentProjects.length === 0 ? (
            <EmptyState
              icon={Database}
              title="还没有项目"
              description="创建第一个项目，上传数据后开始分析。"
              action={{ label: "前往项目管理", to: "/management/projects" }}
            />
          ) : (
            <ProjectList projects={recentProjects} loading={false} />
          )}
        </div>

        {/* Latest activity */}
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "var(--spacing-md)",
            }}
          >
            <h3 style={{ margin: 0 }}>最近任务</h3>
          </div>
          <Card>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--spacing-sm)",
              }}
            >
              {loadingJobs ? (
                [1, 2, 3].map((i) => (
                  <Skeleton key={i} height="50px" variant="text" />
                ))
              ) : jobsError ? <DataReadError title="最近任务暂时无法读取" message={jobsError} onRetry={jobs.refetch} retryLabel="重新读取任务" /> : latestActivity.length === 0 ? (
                <p
                  style={{
                    color: "var(--text-tertiary)",
                    fontSize: "0.85rem",
                    textAlign: "center",
                    padding: "var(--spacing-lg) 0",
                  }}
                >
                  暂无任务。可前往分析向导提交第一次分析。
                </p>
              ) : (
                latestActivity.map((job) => {
                  const label = taskName(job) || analysisLabel(job.module || job.job_type);
                  const target = new URLSearchParams({job:job.job_id || job.id});
                  if (job.project_id) target.set("project", job.project_id);
                  const dataset = job.payload?.asset_set;
                  if (typeof dataset === "string" && dataset) target.set("asset_set", dataset);
                  const updated = job.updated_at || job.created_at;
                  return <Link key={job.job_id || job.id} className="management-recent-task"
                    to={"/analysis/script-hub/jobs?" + target} aria-label={`查看任务：${label}`}>
                    <div className="management-recent-task-copy"><strong>{label}</strong>
                      <span>{jobTextLabel(job.stage || job.detail) || "查看任务进度与结果"}</span>
                      <small>{typeof dataset === "string" && dataset ? `数据集：${dataset} · ` : ""}{updated ? new Date(updated).toLocaleString("zh-CN",{hour12:false}) : "未记录更新时间"}</small>
                    </div>
                    <StatusBadge status={job.status} /><ArrowRight size={16} aria-hidden="true"/>
                  </Link>;
                })
              )}
              {latestActivity.length > 0 && (
                <button
                  onClick={() => navigate("/analysis/script-hub/jobs")}
                  style={{
                    padding: "8px",
                    borderRadius: "var(--radius-control)",
                    color: "var(--accent)",
                    fontWeight: 500,
                    fontSize: "0.82rem",
                    textAlign: "center",
                    width: "100%",
                    border: "none",
                    background: "transparent",
                    cursor: "pointer",
                  }}
                >
                  查看全部任务 →
                </button>
              )}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
