import { Link, useLocation } from "react-router-dom";
import { projectCatalogNavigationState } from "./catalogNavigation";
import { StatusBadge } from "../../shared/components/StatusBadge";
import "./ProjectCatalog.css";
import type { ProjectSummary } from "../../shared/types/domain";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { FolderOpen } from "lucide-react";
import { ProjectCard } from "./ProjectCard";

type Props = {
  projects: ProjectSummary[];
  loading: boolean;
  layout?: "cards" | "list";
};

export function ProjectList({ projects, loading, layout = "cards" }: Props) {
  const location = useLocation();
  if (loading) {
    return (
      <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} height="100px" />
        ))}
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="暂无项目"
        description="创建第一个项目，开始免疫组库分析。"
      />
    );
  }

  if (layout === "list") return <div className="project-catalog-rows" aria-label="项目列表">{projects.map(project => <article className="project-catalog-row" key={project.id}>
    <div className="project-catalog-row-name"><Link to={`/management/projects/${project.id}`} state={projectCatalogNavigationState(location)}>{project.name}</Link><span className="project-catalog-muted">{project.institution || "未填写机构"}</span></div><StatusBadge status={project.status || "active"} />
    <dl><div><dt>文件</dt><dd>{Object.values(project.asset_counts || {}).reduce((sum, count) => sum + count, 0)}</dd></div><div><dt>输入样本条目</dt><dd>{project.input_sample_count || 0}</dd></div><div><dt>结果</dt><dd>{project.result_count || 0}</dd></div></dl>
    <time className="project-catalog-muted">{project.updated_at ? new Date(project.updated_at).toLocaleDateString("zh-CN") : "未记录更新时间"}</time>
  </article>)}</div>;
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(min(340px, 100%), 1fr))",
        gap: "var(--spacing-lg)",
      }}
    >
      {projects.map((p) => (
        <ProjectCard key={p.id} project={p} />
      ))}
    </div>
  );
}
