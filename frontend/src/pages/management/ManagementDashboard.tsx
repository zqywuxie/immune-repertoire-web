import { useNavigate } from "react-router-dom";
import { Boxes, FlaskConical, Activity, Database, Users, Settings2, ArrowRight, AlertTriangle } from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import { listProjects } from "../../shared/api/projects";
import { listJobs } from "../../shared/api/jobs";
import { PageHeader } from "../../shared/components/PageHeader";
import { MetricCard } from "../../shared/components/MetricCard";
import { Card } from "../../shared/components/Card";
import { ProjectList } from "../../features/projects/ProjectList";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";

export function ManagementDashboard() {
  const navigate = useNavigate();
  const projects = useApi(() => listProjects(), []);
  const jobs = useApi(() => listJobs({ limit: 10 }), []);

  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const jobList = jobs.status === "ready" ? jobs.data.jobs : [];

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
    {
      icon: Database,
      label: "项目管理",
      description: "整理项目数据与分析结果",
      to: "/management/projects",
      color: "var(--accent)",
    },
    {
      icon: Users,
      label: "样本管理",
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

      {/* Error banners */}
      {projectsError && <ErrorBanner message={projectsError} />}
      {jobsError && <ErrorBanner message={jobsError} />}

      {/* Metric cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "var(--spacing-lg)",
        }}
      >
        {loadingProjects ? (
          <>
            <Skeleton height="100px" />
            <Skeleton height="100px" />
            <Skeleton height="100px" />
          </>
        ) : (
          <>
            <MetricCard icon={Boxes} label="项目数" value={stats.projects} color="var(--accent)" />
            <MetricCard icon={FlaskConical} label="结果数" value={stats.results} color="var(--success)" />
            <MetricCard icon={Activity} label="进行中的任务" value={stats.activeJobs} color="var(--warning)" />
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
          ) : recentProjects.length === 0 ? (
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
              ) : latestActivity.length === 0 ? (
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
                latestActivity.map((job) => (
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
                      <div
                        style={{
                          fontSize: "0.85rem",
                          fontWeight: 500,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {job.module || job.job_type}
                      </div>
                      <div
                        style={{
                          fontSize: "0.75rem",
                          color: "var(--text-tertiary)",
                          marginTop: "2px",
                        }}
                      >
                        {job.stage || job.detail || ""}
                      </div>
                    </div>
                    <StatusBadge status={job.status} />
                  </div>
                ))
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
      }}
    >
      <AlertTriangle size={18} />
      {message}
    </div>
  );
}
