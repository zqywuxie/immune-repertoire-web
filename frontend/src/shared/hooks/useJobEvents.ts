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

    const source = new EventSource(jobEventsUrl(jobId), { withCredentials: true });

    const handleEvent = (message: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(message.data) as JobEventResponse;
        setEvent(payload);
        setError(null);
        if (terminalStatuses.has(payload.status)) {
          source.close();
          setConnected(false);
        }
      } catch {
        setError("Unable to parse job event.");
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
      setError("Job event stream disconnected.");
    });

    return () => {
      source.close();
      setConnected(false);
    };
  }, [jobId]);

  return { event, error, connected };
}
