import type { ProjectSummary } from "../../shared/types/domain";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { FolderOpen } from "lucide-react";
import { ProjectCard } from "./ProjectCard";

type Props = {
  projects: ProjectSummary[];
  loading: boolean;
};

export function ProjectList({ projects, loading }: Props) {
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

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
        gap: "var(--spacing-lg)",
      }}
    >
      {projects.map((p) => (
        <ProjectCard key={p.id} project={p} />
      ))}
    </div>
  );
}
