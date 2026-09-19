import { analysisLabel } from "../../shared/utils/analysisLabels";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { cancelJob, retryJob } from "../../shared/api/jobs";
import { Eye, Trash2 } from "lucide-react";
import { useState, type MouseEvent } from "react";
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
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [cancelError, setCancelError] = useState("");
  const jobId = job.job_id || job.id;
  const isRunning = job.status === "running" || job.status === "queued";
  const isTerminal = ["completed", "failed", "cancelled", "interrupted"].includes(job.status);
  const clickable = Boolean(onOpenDetails);

  const handleCancel = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (cancelling || !confirm(`确定取消任务 ${analysisLabel(job.module) || jobId}？`)) return;
    setCancelling(true); setCancelError("");
    try {
      await cancelJob(jobId);
      onJobChanged?.();
    } catch (reason) {
      setCancelError(reason instanceof Error ? reason.message : "取消失败，请重试");
    } finally { setCancelling(false); }
  };

  return (
    <div
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={() => onOpenDetails?.(job)}
      onKeyDown={(event) => {
        if (!clickable || event.target !== event.currentTarget) return;
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
          aria-label={`选择任务 ${jobId}`}
          onClick={(event) => event.stopPropagation()}
          onChange={() => onToggleSelected(job)}
          style={{ width: "16px", height: "16px", flexShrink: 0, cursor: "pointer" }}
        />
      )}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", marginBottom: "6px" }}>
          <strong style={{ fontSize: "0.9rem" }}>{analysisLabel(job.module || job.job_type)}</strong>
          <StatusBadge status={job.status} />
        </div>
        {cancelError && <p role="alert" style={{ color: "var(--danger)" }}>{cancelError}</p>}
        <ProgressBar value={Number(job.progress || 0)} />
        <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "4px" }}>
          {job.stage || job.detail || job.status}
          {job.status === "queued" && job.detail && job.detail !== job.stage && <div>{job.detail}</div>}
        </div>
      </div>

      <div style={{ display: "flex", gap: "var(--spacing-xs)", flexShrink: 0 }}>
        {onOpenDetails && (
          <button
            onClick={(event) => {
              event.stopPropagation();
              onOpenDetails(job);
            }}
            title="查看任务详情"
            aria-label="查看任务详情"
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
            disabled={cancelling}
            style={{
              padding: "6px 14px", borderRadius: "var(--radius-control)",
              border: "1px solid var(--danger)", background: "transparent",
              color: "var(--danger)", fontWeight: 500, fontSize: "0.8rem",
              whiteSpace: "nowrap", cursor: "pointer",
            }}
          >
            {cancelling ? "正在取消…" : "取消任务"}
          </button>
        )}
        {["failed", "cancelled", "interrupted"].includes(job.status) && (
          <button className="btn btn-secondary" disabled={retrying} onClick={async (event) => {
            event.stopPropagation();
            if (retrying) return;
            setRetrying(true); setCancelError("");
            try {
              await retryJob(jobId);
              onJobChanged?.();
            } catch (error) {
              setCancelError(error instanceof Error ? error.message : "重试提交失败");
            } finally { setRetrying(false); }
          }}>{retrying ? "正在提交…" : "重试任务"}</button>
        )}
        {onDelete && isTerminal && (
          <button
            onClick={(event) => {
              event.stopPropagation();
              onDelete(job);
            }}
            title="删除任务"
            aria-label="删除任务"
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
