const terminalStatuses = new Set(["completed", "failed", "cancelled", "interrupted"]);
export const isTerminalJobStatus = (status: string) => terminalStatuses.has(status);

export function BatchStatus({ statuses, expectedCount }: { statuses: string[]; expectedCount: number }) {
  const total = Math.max(expectedCount, statuses.length);
  const completed = statuses.filter(status => status === "completed").length;
  const failed = statuses.filter(status => status === "failed").length;
  const cancelled = statuses.filter(status => status === "cancelled").length;
  const interrupted = statuses.filter(status => status === "interrupted").length;
  const pending = total - statuses.filter(isTerminalJobStatus).length;
  const title = pending > 0 ? "分析进行中" : completed === total && total > 0 ? "分析完成" : completed > 0 ? "部分分析完成" : "分析已结束";
  return <section role="status" aria-label="批次进度" style={{padding: "var(--spacing-lg)", border: "1px solid var(--separator)", borderRadius: "var(--radius-panel)", background: "var(--bg-elevated)"}}>
    <strong>{title}</strong>
    <p style={{marginBottom: 0}}>已完成 {completed}/{total} 个任务{pending > 0 ? `，另有 ${pending} 个任务待完成或待确认` : ""}。</p>
    {(failed > 0 || cancelled > 0 || interrupted > 0) && <p style={{marginBottom: 0}}>失败 {failed} 项 · 已取消 {cancelled} 项 · 已中断 {interrupted} 项。已生成的结果仍可查看和下载。</p>}
  </section>;
}
