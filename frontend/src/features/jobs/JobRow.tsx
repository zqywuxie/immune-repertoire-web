import { StatusBadge } from "../../shared/components/StatusBadge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { cancelJob } from "../../shared/api/jobs";
import { Eye, Trash2 } from "lucide-react";
import type { MouseEvent } from "react";
import type { JobSummary } from "../../shared/types/domain";

type Props = {
  job: JobSummary;
  onOpenDetails?: (job: JobSummary) => void;
  selected?: boolean;
  onToggleSelected?: (job: JobSummary) => void;
  onDelete?: (job: JobSummary) => void;
  onJobChanged?: () => void;
};

export function JobRow({
  job,
  onOpenDetails,
  selected = false,
  onToggleSelected,
  onDelete,
  onJobChanged,
}: Props) {
  const jobId = job.job_id || job.id;
  const isRunning = job.status === "running" || job.status === "queued";
  const isTerminal = ["completed", "failed", "cancelled", "interrupted"].includes(job.status);
  const clickable = Boolean(onOpenDetails);

  const handleCancel = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (!confirm(`Cancel job ${job.module || jobId}?`)) return;
    try {
      await cancelJob(jobId);
      onJobChanged?.();
    } catch {
      // best effort
    }
  };

  return (
    <div
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={() => onOpenDetails?.(job)}
      onKeyDown={(event) => {
        if (!clickable) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpenDetails?.(job);
        }
      }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-md) var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: selected ? "1px solid var(--accent)" : "1px solid var(--separator)",
        boxShadow: selected ? "0 0 0 3px color-mix(in srgb, var(--accent) 12%, transparent)" : "none",
        cursor: clickable ? "pointer" : "default",
        transition: "border-color 140ms ease, background 140ms ease",
      }}
    >
      {onToggleSelected && (
        <input
          type="checkbox"
          checked={selected}
          aria-label={`Select job ${jobId}`}
          onClick={(event) => event.stopPropagation()}
          onChange={() => onToggleSelected(job)}
          style={{ width: "16px", height: "16px", flexShrink: 0, cursor: "pointer" }}
        />
      )}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", marginBottom: "6px" }}>
          <strong style={{ fontSize: "0.9rem" }}>{job.module || job.job_type}</strong>
          <StatusBadge status={job.status} />
        </div>
        <ProgressBar value={Number(job.progress || 0)} />
        <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "4px" }}>
          {job.stage || job.detail || job.status}
        </div>
      </div>

      <div style={{ display: "flex", gap: "var(--spacing-xs)", flexShrink: 0 }}>
        {onOpenDetails && (
          <button
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetails(job);
            }}
            title="View job configuration"
            aria-label="View job configuration"
            style={{
              width: "32px", height: "32px", borderRadius: "var(--radius-control)",
              border: "1px solid var(--separator)", background: "var(--bg-elevated)",
              color: "var(--text-secondary)", display: "inline-flex", alignItems: "center",
              justifyContent: "center", cursor: "pointer",
            }}
          >
            <Eye size={16} />
          </button>
        )}
        {isRunning && (
          <button
            onClick={handleCancel}
            style={{
              padding: "6px 14px", borderRadius: "var(--radius-control)",
              border: "1px solid var(--danger)", background: "transparent",
              color: "var(--danger)", fontWeight: 500, fontSize: "0.8rem",
              whiteSpace: "nowrap", cursor: "pointer",
            }}
          >
            Cancel
          </button>
        )}
        {onDelete && isTerminal && (
          <button
            onClick={(event) => {
              event.stopPropagation();
              onDelete(job);
            }}
            title="Delete job"
            aria-label="Delete job"
            style={{
              width: "32px", height: "32px", borderRadius: "var(--radius-control)",
              border: "1px solid color-mix(in srgb, var(--danger) 55%, var(--separator))",
              background: "transparent", color: "var(--danger)", display: "inline-flex",
              alignItems: "center", justifyContent: "center", cursor: "pointer",
            }}
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>
    </div>
  );
}
