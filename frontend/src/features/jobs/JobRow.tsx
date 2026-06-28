import { StatusBadge } from "../../shared/components/StatusBadge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import type { JobSummary } from "../../shared/types/domain";

type Props = {
  job: JobSummary;
  onSelect?: (jobId: string) => void;
};

export function JobRow({ job, onSelect }: Props) {
  const jobId = job.job_id || job.id;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-md) var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
      }}
    >
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            marginBottom: "6px",
          }}
        >
          <strong style={{ fontSize: "0.9rem" }}>
            {job.module || job.job_type}
          </strong>
          <StatusBadge status={job.status} />
        </div>
        <ProgressBar value={Number(job.progress || 0)} />
        <div
          style={{
            fontSize: "0.75rem",
            color: "var(--text-tertiary)",
            marginTop: "4px",
          }}
        >
          {job.stage || job.detail || job.status}
        </div>
      </div>
      {onSelect && (job.status === "completed" || job.status === "failed") && (
        <button
          onClick={() => onSelect(jobId)}
          style={{
            padding: "6px 14px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--accent)",
            fontWeight: 500,
            fontSize: "0.8rem",
            whiteSpace: "nowrap",
          }}
        >
          Results
        </button>
      )}
    </div>
  );
}
