import { useApi } from "../../shared/hooks/useApi";
import { listProjects } from "../../shared/api/projects";
import { Skeleton } from "../../shared/components/Skeleton";
import { ProjectCard } from "./ProjectCard";

export function ProjectList() {
  const state = useApi(() => listProjects(), []);

  if (state.status === "loading") {
    return (
      <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
        {[1, 2, 3].map((i) => (
          <Skeleton key={i} height="100px" />
        ))}
      </div>
    );
  }

  if (state.status === "error") {
    return <p style={{ color: "var(--danger)" }}>{state.error}</p>;
  }

  const projects = state.status === "ready" ? state.data.projects : [];

  if (projects.length === 0) {
    return (
      <p style={{ color: "var(--text-tertiary)", textAlign: "center", padding: "var(--spacing-3xl)" }}>
        No projects found.
      </p>
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
