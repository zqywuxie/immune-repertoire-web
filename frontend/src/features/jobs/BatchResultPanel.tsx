import { useState, type ReactNode } from "react";
import { useBatchJobSnapshots, type BatchJobSnapshots } from "./useBatchJobSnapshots";
import { preferLatestJobSnapshot } from "../../shared/utils/jobState";
import type { JobResultsResponse } from "../../shared/api/jobs";
import { useJobResult } from "../../shared/hooks/useJobResult";
import { BatchExecutionProgress, batchItemsForJob, type BatchItem } from "./BatchExecutionProgress";
export type { BatchItem } from "./BatchExecutionProgress";

export function batchItems(result: JobResultsResponse): BatchItem[] {
  return batchItemsForJob(result.job);
}
type Props = {result: JobResultsResponse; renderResult: (result: JobResultsResponse) => ReactNode; snapshots?: BatchJobSnapshots; selectedJobId?: string; onSelectJob?: (id: string) => void};
export function BatchResultPanel(props: Props) {
  return props.snapshots ? <BatchResultContent {...props} snapshots={props.snapshots}/> : <StandaloneBatchResult {...props}/>;
}
function StandaloneBatchResult(props: Props) {
  const progress = useBatchJobSnapshots(props.result.job.id, props.result.status, batchItems(props.result));
  return <BatchResultContent {...props} snapshots={progress}/>;
}
function BatchResultContent({result, renderResult, snapshots: progress, selectedJobId, onSelectJob}: Props & {snapshots: BatchJobSnapshots}) {
  const items = batchItems(result);
  const cancelling = result.job.cancel_requested && result.status === "running";
  const [selected, setSelected] = useState("");
  const preferred = selectedJobId || selected;
  const selectedId = preferred && items.some(item => item.job_id === preferred) ? preferred : items.find(item => item.status === "completed" && item.job_id)?.job_id || "";
  const child = useJobResult(selectedId || null);
  const childJobs = {...progress.jobs};
  if (child.result) {
    const id = child.result.job.id;
    childJobs[id] = preferLatestJobSnapshot(childJobs[id] || null, child.result.job);
  }
  return <section aria-label="批次分析结果" style={{display: "grid", gap: "var(--spacing-md)"}}>
    {cancelling && <p role="status">正在取消，等待当前子任务在计算检查点停止。</p>}
    <BatchExecutionProgress items={items} onSelectResult={id => {setSelected(id);onSelectJob?.(id);}}
      jobs={childJobs} readErrors={progress.readErrors} onRetry={item => progress.retry(item.job_id!)}/>
    {child.error && <div role="alert">{child.error} <button className="btn btn-secondary" onClick={child.retry}>重新读取</button></div>}
    {child.result && renderResult(child.result)}
    {selectedId && !child.result && !child.error && <p role="status">正在读取子任务状态与结果…</p>}
  </section>;
}
