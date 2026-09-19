import { useEffect, useState } from "react";
import { getJob, getJobResults, type JobResultsResponse } from "../api/jobs";

export function useJobResult(jobId: string | null) {
  const [state, setState] = useState<{ jobId: string | null; status: string; result: JobResultsResponse | null; error: string }>({ jobId: null, status: "", result: null, error: "" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!jobId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setState({ jobId, status: "queued", result: null, error: "" });
    async function poll() {
      try {
        const { job } = await getJob(jobId!);
        if (disposed) return;
        const status = String(job.status);
        if (job.module === "analysis-batch") {
          const snapshot: JobResultsResponse = {success: true, job, status, result: (job.result || {}) as Record<string, unknown>, outputs: [], assets: []};
          setState({jobId, status, result: snapshot, error: ""});
          if (!["completed", "failed", "cancelled", "interrupted"].includes(status)) timer = setTimeout(poll, 1500);
          return;
        }
        if (["failed", "cancelled", "interrupted"].includes(status)) {
          setState({ jobId, status, result: null, error: String(job.error || job.detail || "任务未完成，请查看任务详情。") });
          return;
        }
        if (status === "completed") {
          const result = await getJobResults(jobId!);
          if (!disposed) setState({ jobId, status, result, error: "" });
          return;
        }
        setState({ jobId, status, result: null, error: "" });
        timer = setTimeout(poll, 1500);
      } catch (error) {
        if (!disposed) {
          setState(previous => ({...previous, jobId, error: (error instanceof Error ? error.message + "。" : "暂时无法读取任务状态。") + "正在重连。"}));
          timer = setTimeout(poll, 3000);
        }
      }
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [jobId, revision]);
  return { ...(state.jobId === jobId ? state : { jobId, status: jobId ? "queued" : "", result: null, error: "" }), retry: () => setRevision(value => value + 1) };
}
