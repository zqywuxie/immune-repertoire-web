import type { JobSummary } from "../../shared/types/domain";
import { analysisLabel, jobTextLabel } from "../../shared/utils/analysisLabels";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { BatchStatus, isTerminalJobStatus } from "./BatchStatus";
import "./BatchExecutionProgress.css";

export interface BatchItem {
  module: string;
  job_id?: string;
  status: string;
  error?: string;
  depends_on?: number[];
  blocked_by?: number[];
}
export function batchItemsForJob(job: JobSummary): BatchItem[] {
  const payload = job.payload as unknown as {items?: BatchItem[]} | undefined;
  return payload?.items || [];
}
export function batchItemStatus(item: BatchItem, job?: JobSummary): string {
  // A terminal parent item remains terminal even if the last child read was earlier.
  return isTerminalJobStatus(item.status) && job && !isTerminalJobStatus(job.status)
    ? item.status : job?.status || item.status;
}
function waitingReason(item: BatchItem, items: BatchItem[], jobs: Record<string, JobSummary>): string {
  if (item.status !== "queued") return "";
  const waiting = (item.depends_on || []).filter(index => {
    const source = items[index];
    return source && batchItemStatus(source, jobs[source.job_id || ""]) !== "completed";
  });
  return waiting.length
    ? "等待" + waiting.map(index => analysisLabel(items[index].module)).join("、") + "完成后，自动使用其输出。"
    : item.job_id ? "等待任务队列执行。" : "前置条件已满足，等待服务端执行此项。";
}
export function BatchExecutionProgress({ items, jobs = {}, readErrors = {}, onRetry, onSelectResult }: {
  items: BatchItem[];
  jobs?: Record<string, JobSummary>;
  readErrors?: Record<string, string>;
  onRetry?: (item: BatchItem) => void;
  onSelectResult?: (id: string) => void;
}) {
  return <section className="batch-execution" aria-label="逐项分析进度">
    <BatchStatus statuses={items.map(item => batchItemStatus(item, jobs[item.job_id || ""]))} expectedCount={items.length}/>
    <div className="batch-execution__items">{items.map((item, index) => {
      const id = item.job_id || "";
      const job = jobs[id];
      const status = batchItemStatus(item, job);
      const recorded = typeof job?.progress === "number" && Number.isFinite(job.progress);
      const progress = recorded ? job!.progress! : null;
      const stage = jobTextLabel(job?.stage || job?.detail || "");
      const reason = waitingReason({...item, status}, items, jobs);
      const blocked = !item.error && item.blocked_by?.length
        ? "前置分析未成功完成，未执行此项：" + item.blocked_by.filter(i => items[i]).map(i => analysisLabel(items[i].module)).join("、") : "";
      return <article className="batch-execution__item" key={index}
        aria-label={"第 " + (index + 1) + " 项 · " + analysisLabel(item.module)}>
        <div className="batch-execution__header">
          <span className="batch-execution__number" aria-hidden="true">{index + 1}</span>
          <div className="batch-execution__title"><strong>{analysisLabel(item.module)}</strong>
            {id && <span className="batch-execution__id">任务 {id.slice(-8)}</span>}
          </div>
          <StatusBadge status={status}/>
        </div>
        {reason && <p className="batch-execution__note">{reason}</p>}
        {id && <div className="batch-execution__progress">
          {progress !== null ? <>
            <div className="batch-execution__caption"><span>{stage || (status === "completed" ? "分析已完成" : "最近记录的进度")}</span><strong>{Math.round(progress)}%</strong></div>
            <ProgressBar value={progress}/>
          </> : <p className="batch-execution__note">{stage || "尚未读取到此项的进度记录。"}</p>}
        </div>}
        {(item.error || job?.error || blocked) && <p className="batch-execution__error">{jobTextLabel(item.error || job?.error || blocked)}</p>}
        {readErrors[id] && <div role="status" className="batch-execution__notice">
          <span>{readErrors[id]}</span>
          {onRetry && <button className="btn btn-secondary" onClick={() => onRetry(item)}>重新读取此项</button>}
        </div>}
        {id && <div className="batch-execution__actions">
          {onSelectResult ? <button className="btn btn-secondary" onClick={() => onSelectResult(id)}>查看此项结果</button>
            : <a className="batch-execution__link" href={"/analysis/script-hub/jobs?job=" + encodeURIComponent(id)} target="_blank" rel="noreferrer">{status === "completed" ? "查看此项结果" : "查看任务"}</a>}
        </div>}
      </article>;
    })}</div>
  </section>;
}
