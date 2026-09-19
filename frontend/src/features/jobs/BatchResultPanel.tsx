import { useState, type ReactNode } from "react";
import type { JobResultsResponse } from "../../shared/api/jobs";
import { useJobResult } from "../../shared/hooks/useJobResult";
import { analysisLabel } from "../../shared/utils/analysisLabels";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { BatchStatus } from "./BatchStatus";

export interface BatchItem { module: string; job_id?: string; status: string; error?: string }
export function batchItems(result: JobResultsResponse): BatchItem[] {
  const job = result.job as unknown as {payload?: {items?: BatchItem[]}};
  return job.payload?.items || [];
}
export function BatchResultPanel({ result, renderResult }: {result: JobResultsResponse; renderResult: (result: JobResultsResponse) => ReactNode}) {
  const items = batchItems(result);
  const cancelling = (result.job as unknown as {cancel_requested?: boolean}).cancel_requested && result.status === "running";
  const [selected, setSelected] = useState("");
  const selectedId = items.some(item => item.job_id === selected) ? selected : items.find(item => item.status === "completed" && item.job_id)?.job_id || "";
  const child = useJobResult(selectedId || null);
  return <section aria-label="批次分析结果" style={{display: "grid", gap: "var(--spacing-md)"}}>
    {cancelling && <p role="status">正在取消，等待当前子任务在计算检查点停止。</p>}
    <BatchStatus statuses={items.map(item => item.status)} expectedCount={items.length} />
    <div style={{display: "grid", gap: "var(--spacing-sm)"}}>
      {items.map((item, index) => <div key={`${index}:${item.job_id}`} style={{border: "1px solid var(--separator)", borderRadius: "var(--radius-control)", padding: "var(--spacing-md)"}}>
        <div style={{display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)", alignItems: "center"}}>
          <strong>{index + 1}. {analysisLabel(item.module)}</strong><StatusBadge status={item.status} />
          {item.job_id && <button className="btn btn-secondary" onClick={() => setSelected(item.job_id!)}>查看此项结果</button>}
        </div>
        {item.error && <p style={{marginBottom:0}}>{item.error}</p>}
        {!item.job_id && item.status === "queued" && <p style={{marginBottom:0}}>等待服务端执行。</p>}
      </div>)}
    </div>
    {child.error && <div role="alert">{child.error} <button className="btn btn-secondary" onClick={child.retry}>重新读取</button></div>}
    {child.result && renderResult(child.result)}
    {selectedId && !child.result && !child.error && <p role="status">正在读取子任务状态与结果…</p>}
  </section>;
}
