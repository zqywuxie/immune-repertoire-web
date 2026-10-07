import "./JobRow.css";
import { taskName } from "./jobConfiguration";
import { analysisLabel, jobTextLabel } from "../../shared/utils/analysisLabels";
import { StatusBadge, statusLabels } from "../../shared/components/StatusBadge";
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
  onRetried?: (jobId: string) => void;
};

export function JobRow({
  job,
  onOpenDetails,
  selected = false,
  onToggleSelected,
  onDelete,
  onJobChanged,
  onRetried,
}: Props) {
  const [cancelling, setCancelling] = useState(false);
  const [cancelAccepted, setCancelAccepted] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retriedJobId, setRetriedJobId] = useState("");
  const [cancelError, setCancelError] = useState("");
  const jobId = job.job_id || job.id;
  const moduleLabel = analysisLabel(job.module || job.job_type);
  const name = taskName(job) || moduleLabel;
  const isRunning = job.status === "running" || job.status === "queued";
  const cancelPending = isRunning && Boolean(job.cancel_requested || cancelAccepted);
  const isTerminal = ["completed", "failed", "cancelled", "interrupted"].includes(job.status);
  const clickable = Boolean(onOpenDetails);

  const handleCancel = async (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    if (cancelling || cancelPending || !confirm(`确定取消任务 ${analysisLabel(job.module) || jobId}？`)) return;
    setCancelling(true); setCancelError("");
    try {
      await cancelJob(jobId);
      setCancelAccepted(true);
      onJobChanged?.();
    } catch (reason) {
      setCancelError(reason instanceof Error ? reason.message : "取消失败，请重试");
    } finally { setCancelling(false); }
  };

  return (
    <div
      data-job-status={job.status}
      className={`job-row${onToggleSelected ? " job-row--selectable" : ""}`}
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
        alignItems: "center",
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
          className="job-row__select"
          type="checkbox"
          checked={selected}
          aria-label={`选择任务 ${jobId}`}
          onClick={(event) => event.stopPropagation()}
          onChange={() => onToggleSelected(job)}
          style={{ width: "16px", height: "16px", flexShrink: 0, cursor: "pointer" }}
        />
      )}
      <div className="job-row__summary" style={{ minWidth: 0, flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", flexWrap: "wrap", marginBottom: "6px" }}>
          <strong className="job-row__title" style={{ fontSize: "0.9rem" }}>{name}</strong>
          <StatusBadge status={job.status} />
        </div>
        <p className="job-row__identity">{name !== moduleLabel && <span>{moduleLabel} · </span>}{jobId}</p>
        {cancelError && <p role="alert" style={{ color: "var(--danger)" }}>{cancelError}</p>}
        {retriedJobId && <p role="status">已创建新任务，原记录保留。<a href={"/analysis/script-hub/jobs?job=" + encodeURIComponent(retriedJobId)} onClick={event => event.stopPropagation()}>查看重试任务</a></p>}
        <ProgressBar value={Number(job.progress || 0)} />
        <div style={{ fontSize: "0.75rem", color: "var(--text-tertiary)", marginTop: "4px" }}>
          {jobTextLabel(job.stage || job.detail) || statusLabels[job.status]}
          {cancelPending && <div role="status">等待计算停止后可重试或删除任务。</div>}
          {job.status === "queued" && job.detail && job.detail !== job.stage && <div>{jobTextLabel(job.detail)}</div>}
        </div>
      </div>

      <div className="job-row__actions" style={{ display: "flex", gap: "var(--spacing-xs)", flexShrink: 0 }}>
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
            disabled={cancelling || cancelPending}
            style={{
              padding: "6px 14px", borderRadius: "var(--radius-control)",
              border: "1px solid var(--danger)", background: "transparent",
              color: "var(--danger)", fontWeight: 500, fontSize: "0.8rem",
              whiteSpace: "nowrap", cursor: "pointer",
            }}
          >
            {cancelling || cancelPending ? "正在取消…" : "取消任务"}
          </button>
        )}
        {["failed", "cancelled", "interrupted"].includes(job.status) && (
          <button className="btn btn-secondary" disabled={retrying} onClick={async (event) => {
            event.stopPropagation();
            if (retrying) return;
            setRetrying(true); setCancelError("");
            try {
              const response = await retryJob(jobId);
              setRetriedJobId(response.job_id);
              onJobChanged?.();
              onRetried?.(response.job_id);
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
