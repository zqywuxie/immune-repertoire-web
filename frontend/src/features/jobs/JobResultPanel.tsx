import type { JobResultsResponse } from "../../shared/api/jobs";
import { StatusBadge } from "../../shared/components/StatusBadge";

type Props = {
  result: JobResultsResponse | null;
  loading: boolean;
};

export function JobResultPanel({ result, loading }: Props) {
  if (loading) {
    return (
      <div
        style={{
          background: "var(--bg-elevated)",
          borderRadius: "var(--radius-panel)",
          border: "1px solid var(--separator)",
          padding: "var(--spacing-xl)",
          textAlign: "center",
          color: "var(--text-tertiary)",
        }}
      >
        Loading job results…
      </div>
    );
  }

  if (!result) return null;

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        padding: "var(--spacing-xl)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-lg)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <h4 style={{ margin: 0 }}>{result.job.module || "Job Result"}</h4>
        <StatusBadge status={result.status} />
      </div>

      {result.outputs.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              textTransform: "uppercase",
              color: "var(--text-secondary)",
              marginBottom: "var(--spacing-sm)",
            }}
          >
            Outputs
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {result.outputs.map((o) => (
              <a
                key={`${o.kind}-${o.url}`}
                href={o.url}
                target="_blank"
                rel="noreferrer"
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--radius-pill)",
                  background: "var(--bg-root)",
                  color: "var(--accent)",
                  fontSize: "0.82rem",
                  fontWeight: 500,
                  textDecoration: "none",
                  border: "1px solid var(--separator)",
                }}
              >
                {o.label}
              </a>
            ))}
          </div>
        </div>
      )}

      {result.assets.length > 0 && (
        <div>
          <div
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              textTransform: "uppercase",
              color: "var(--text-secondary)",
              marginBottom: "var(--spacing-sm)",
            }}
          >
            Registered Assets
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {result.assets.map((a) => (
              <a
                key={a.id}
                href={a.preview_url || "#"}
                target="_blank"
                rel="noreferrer"
                style={{
                  padding: "6px 14px",
                  borderRadius: "var(--radius-pill)",
                  background: "var(--bg-root)",
                  color: "var(--text-primary)",
                  fontSize: "0.82rem",
                  textDecoration: "none",
                  border: "1px solid var(--separator)",
                }}
              >
                {a.original_name}
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
