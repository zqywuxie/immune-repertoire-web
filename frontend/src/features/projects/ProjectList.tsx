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
        title="No projects yet"
        description="Create your first project to get started with immune repertoire analysis."
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
