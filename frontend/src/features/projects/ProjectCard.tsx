import { useNavigate } from "react-router-dom";
import { Card } from "../../shared/components/Card";
import type { ProjectSummary } from "../../shared/types/domain";
import type { ProjectAssetStatus } from "../../shared/api/projects";

export function ProjectCard({ project }: { project: ProjectSummary }) {
  const navigate = useNavigate();
  const assetCount = Object.values(project.asset_counts || {}).reduce(
    (s, c) => s + c,
    0
  );
  const assetStatus = ((project as ProjectSummary & { asset_status?: ProjectAssetStatus }).asset_status || {});
  const statusItems = [
    { label: "Profile", active: Boolean(assetStatus.has_profile || assetStatus.has_datapoint) },
    { label: "PEP", active: Boolean(assetStatus.has_pep) },
    { label: "Sample", active: Boolean(assetStatus.has_sample_summary) },
    { label: "Group", active: Boolean(assetStatus.has_group_spec) },
    { label: "Results", active: Boolean(assetStatus.has_results) },
  ];

  return (
    <Card onClick={() => navigate(`/management/projects/${project.id}`)}>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: "var(--spacing-md)",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h4
            style={{
              margin: 0,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {project.name}
          </h4>
          {project.institution && (
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "0.8rem",
                margin: "4px 0 0",
              }}
            >
              {project.institution}
            </p>
          )}
        </div>
        <span
          style={{
            fontSize: "0.75rem",
            fontWeight: 500,
            textTransform: "capitalize",
            padding: "3px 10px",
            borderRadius: "var(--radius-pill)",
            background:
              project.status === "active"
                ? "rgba(52,199,89,0.12)"
                : "var(--bg-inset)",
            color:
              project.status === "active"
                ? "var(--success)"
                : "var(--text-secondary)",
          }}
        >
          {project.status}
        </span>
      </div>

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "6px",
          marginTop: "var(--spacing-md)",
        }}
      >
        {statusItems.map((item) => (
          <span
            key={item.label}
            style={{
              fontSize: "0.68rem",
              fontWeight: 600,
              padding: "3px 8px",
              borderRadius: "var(--radius-pill)",
              border: item.active ? "1px solid rgba(52,199,89,0.25)" : "1px solid var(--separator)",
              background: item.active ? "rgba(52,199,89,0.1)" : "var(--bg-inset)",
              color: item.active ? "var(--success)" : "var(--text-tertiary)",
            }}
          >
            {item.label}
          </span>
        ))}
        {assetStatus.asset_set_count ? (
          <span
            style={{
              fontSize: "0.68rem",
              fontWeight: 600,
              padding: "3px 8px",
              borderRadius: "var(--radius-pill)",
              background: "rgba(0,113,227,0.08)",
              color: "var(--accent)",
              border: "1px solid rgba(0,113,227,0.18)",
            }}
          >
            {assetStatus.asset_set_count} sets
          </span>
        ) : null}
      </div>

      <div
        style={{
          display: "flex",
          gap: "var(--spacing-xl)",
          marginTop: "var(--spacing-lg)",
          fontSize: "0.875rem",
          color: "var(--text-secondary)",
        }}
      >
        <div>
          <strong style={{ color: "var(--text-primary)" }}>{assetCount}</strong>{" "}
          assets
        </div>
        <div>
          <strong style={{ color: "var(--text-primary)" }}>
            {project.sample_count || 0}
          </strong>{" "}
          samples
        </div>
        <div>
          <strong style={{ color: "var(--text-primary)" }}>
            {project.result_count || 0}
          </strong>{" "}
          results
        </div>
      </div>
    </Card>
  );
}
