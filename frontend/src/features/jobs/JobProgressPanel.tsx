import {JobQueueNotice} from "./JobQueueNotice";
import { useEffect, useMemo, useState } from "react";
import type { JobSummary } from "../../shared/types/domain";
import { StatusBadge, statusLabels } from "../../shared/components/StatusBadge";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { analysisLabel, jobTextLabel } from "../../shared/utils/analysisLabels";
import { isTerminalJobStatus } from "../../shared/utils/jobState";
import "./JobProgressPanel.css";

type Entry = {progress: number | null; stage: string; detail: string; timestamp: string};
function recordedProgress(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const progress = Number(value);
  return Number.isFinite(progress) && progress >= 0 && progress <= 100 ? progress : null;
}
function historyFor(job: JobSummary) {
  const history = (job as JobSummary & {history?: unknown}).history ?? job.payload?.history;
  if (!Array.isArray(history)) return [];
  const entries: Entry[] = [];
  for (const value of history) {
    if (!value || typeof value !== "object") continue;
    const record = value as Record<string, unknown>;
    const entry = {progress: recordedProgress(record.progress), stage: String(record.stage || ""),
      detail: String(record.detail || ""), timestamp: String(record.timestamp || record.updated_at || "")};
    if (!entry.stage && !entry.detail && entry.progress === null) continue;
    const previous = entries.at(-1);
    if (previous && previous.progress === entry.progress && previous.stage === entry.stage && previous.detail === entry.detail) entries[entries.length - 1] = entry;
    else entries.push(entry);
  }
  return entries;
}
function dateLabel(value: unknown) {
  if (!value) return "未记录";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", {hour12: false});
}
function durationLabel(milliseconds: number) {
  const seconds = Math.floor(milliseconds / 1000);
  const days = Math.floor(seconds / 86400), hours = Math.floor(seconds / 3600) % 24;
  const minutes = Math.floor(seconds / 60) % 60;
  return [days ? days + "天" : "", hours ? hours + "小时" : "", minutes ? minutes + "分" : "", seconds % 60 + "秒"].filter(Boolean).join(" ");
}
function Elapsed({job}: {job: JobSummary}) {
  const started = Date.parse(job.started_at || "");
  const ended = Date.parse(job.completed_at || "");
  const active = job.status === "running" && Number.isFinite(started);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [active, job.started_at]);
  let text = job.status === "queued" ? "尚未开始" : "未记录开始时间";
  if (Number.isFinite(started)) {
    if (isTerminalJobStatus(job.status) && !Number.isFinite(ended)) text = "未记录结束时间";
    else {
      const stop = Number.isFinite(ended) ? ended : now;
      text = stop < started ? "时间记录待核对" : durationLabel(stop - started);
    }
  }
  return <span data-job-elapsed>{text}</span>;
}
export function JobProgressPanel({job}: {job: JobSummary}) {
  const history = useMemo(() => historyFor(job), [job]);
  const recent = history.slice(-20).reverse();
  const progress = recordedProgress(job.progress);
  const terminal = isTerminalJobStatus(job.status);
  const context = new URLSearchParams();
  if (job.project_id) context.set("project", job.project_id);
  if (typeof job.payload?.asset_set === "string" && job.payload.asset_set) context.set("asset_set", job.payload.asset_set);
  const analysisCenter = "/analysis/center" + (context.size ? "?" + context : "");
  const hasTechnicalError = Boolean(job.error) || (terminal && job.status !== "completed" && job.detail);
  return <div className={"job-progress-panel job-progress-panel--" + job.status}>
    <div className="job-progress-heading"><div><h4>任务进度</h4><p>{terminal ? statusLabels[job.status] || "未知状态" : jobTextLabel(job.stage) || statusLabels[job.status] || "等待更新"}</p></div><StatusBadge status={job.status}/></div>
    {progress !== null ? <div className="job-progress-percentage"><ProgressBar value={progress}/><span>{terminal && job.status !== "completed" ? "最后记录进度：" : ""}{progress.toFixed(0)}%</span></div> : <p>尚未记录百分比，请以实际阶段为准。</p>}
    {job.status === "queued" && <JobQueueNotice key={job.job_id || job.id} jobId={job.job_id || job.id}/>}
    {job.cancel_requested && !terminal && <p role="status" className="job-progress-notice">正在取消，等待计算在检查点停止。实际停止前请保留输入文件。</p>}
    {job.status === "failed" && <div role="alert" className="job-progress-error"><strong>本次分析失败</strong><p>请核对配置中的输入与参数；修改参数后可从分析中心重新提交。按原参数重试会创建新任务，原记录保留。</p><a className="btn btn-secondary" href={analysisCenter}>进入分析中心</a></div>}
    {job.status === "interrupted" && <p role="status" className="job-progress-notice">执行已中断。可检查配置后重试；重试从头执行，不是断点续算。</p>}
    <dl className="job-progress-facts">
      <Fact label="分析模块">{analysisLabel(job.module)}</Fact><Fact label="状态">{statusLabels[job.status] || "未知状态"}</Fact>
      <Fact label="已耗时"><Elapsed job={job}/></Fact><Fact label={terminal ? "最后记录阶段" : "运行阶段"}>{jobTextLabel(job.stage) || "未记录"}</Fact>
      {!hasTechnicalError && <Fact label="详情">{jobTextLabel(job.detail) || "未记录"}</Fact>}
      <Fact label="创建时间">{dateLabel(job.created_at)}</Fact><Fact label="更新时间">{dateLabel(job.updated_at)}</Fact>
      <Fact label="开始时间">{dateLabel(job.started_at)}</Fact><Fact label="结束时间">{dateLabel(job.completed_at)}</Fact>
    </dl>
    <p className="job-progress-hint">时间按当前设备时区显示。已耗时不是预计剩余时间。</p>
    <details className="job-progress-records">
      <summary>进度记录（最近 {recent.length} 条变化）</summary>
      {history.length > 20 && <p className="job-progress-hint">这里只显示最近 20 条，较早记录仍保留在任务中。</p>}
      {recent.length ? <ol>{recent.map((entry, index) => <li key={index}>
        <div className="job-progress-entry-heading"><strong>{jobTextLabel(entry.stage) || "状态更新"}</strong><span>{entry.progress === null ? "未记录百分比" : entry.progress.toFixed(0) + "%"}</span></div>
        <time>{dateLabel(entry.timestamp)}</time>
        {entry.detail && <p>{jobTextLabel(entry.detail)}</p>}
      </li>)}</ol> : <p className="job-progress-hint">暂无进度记录。</p>}
    </details>
    {hasTechnicalError && <details className="job-progress-records"><summary>错误与技术详情</summary>
      {job.error && <pre tabIndex={0}>{job.error}</pre>}
      {job.detail && job.detail !== job.error && <pre tabIndex={0}>{job.detail}</pre>}
    </details>}
  </div>;
}
function Fact({label, children}: {label: string; children: React.ReactNode}) {
  return <div><dt>{label}</dt><dd>{children}</dd></div>;
}
