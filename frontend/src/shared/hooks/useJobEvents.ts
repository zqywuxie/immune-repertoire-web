import { useEffect, useState } from "react";
import { jobEventsUrl, type JobEventResponse } from "../api/jobs";

const terminalStatuses = new Set(["completed", "failed", "cancelled", "interrupted"]);

export function useJobEvents(jobId: string | null) {
  const [event, setEvent] = useState<JobEventResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!jobId) {
      setEvent(null);
      setError(null);
      setConnected(false);
      return;
    }

    let disposed = false;
    setEvent(null); setError(null);
    const source = new EventSource(jobEventsUrl(jobId), { withCredentials: true });

    const handleEvent = (message: MessageEvent<string>) => {
      if (disposed) return;
      try {
        const payload = JSON.parse(message.data) as JobEventResponse;
        setEvent(payload);
        setError(null);
        if (terminalStatuses.has(payload.status)) {
          source.close();
          setConnected(false);
        }
      } catch {
        setError("无法解析任务状态信息。");
      }
    };

    source.addEventListener("open", () => {
      setConnected(true);
      setError(null);
    });
    source.addEventListener("update", handleEvent as EventListener);
    source.addEventListener("completed", handleEvent as EventListener);
    source.addEventListener("error", () => {
      setConnected(false);
      setError("任务状态连接已断开。");
    });

    return () => {
      disposed = true;
      source.close();
      setConnected(false);
    };
  }, [jobId]);

  return { event: event && (event.job.job_id || event.job.id) === jobId ? event : null, error, connected };
}
