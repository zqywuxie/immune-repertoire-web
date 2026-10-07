import type { JobSummary } from "../types/domain";

export const isTerminalJobStatus = (status: string) =>
  ["completed", "failed", "cancelled", "interrupted"].includes(status);

/** Keep SSE and polling from restoring an older snapshot of the same task. */
export function preferLatestJobSnapshot(current: JobSummary | null, incoming: JobSummary): JobSummary {
  if (!current || (current.job_id || current.id) !== (incoming.job_id || incoming.id)) return incoming;
  if (isTerminalJobStatus(current.status) && current.status !== incoming.status) return current;
  const previousTime = Date.parse(current.updated_at || "");
  const incomingTime = Date.parse(incoming.updated_at || "");
  if (Number.isFinite(previousTime) && Number.isFinite(incomingTime) && incomingTime < previousTime) return current;
  return incoming;
}
