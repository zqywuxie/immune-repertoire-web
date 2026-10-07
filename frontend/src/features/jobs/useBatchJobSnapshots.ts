import { useEffect, useRef, useState } from "react";
import { getJob } from "../../shared/api/jobs";
import type { JobSummary } from "../../shared/types/domain";
import { preferLatestJobSnapshot } from "../../shared/utils/jobState";
import { isTerminalJobStatus } from "./BatchStatus";
import type { BatchItem } from "./BatchExecutionProgress";

type SnapshotState = { batchId: string; jobs: Record<string, JobSummary>; errors: Record<string, string> };
/** Read each child's actual progress; the parent records the plan, not live child percentages. */
export function useBatchJobSnapshots(batchId: string, parentStatus: string, items: BatchItem[]) {
  const empty = (): SnapshotState => ({batchId, jobs: {}, errors: {}});
  const [state, setState] = useState<SnapshotState>(empty);
  const snapshots = useRef(state);
  const readOne = useRef<((id: string) => Promise<void>) | null>(null);
  const ids = [...new Set(items.map(item => item.job_id).filter((id): id is string => Boolean(id)))];
  const idKey = JSON.stringify(ids);
  const terminal = isTerminalJobStatus(parentStatus);
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const childIds: string[] = JSON.parse(idKey);
    if (snapshots.current.batchId !== batchId) snapshots.current = {batchId, jobs: {}, errors: {}};
    setState({...snapshots.current});
    const versions: Record<string, number> = {};
    async function read(id: string, forceFresh = false) {
      if (disposed || !childIds.includes(id)) return;
      const version = versions[id] = (versions[id] || 0) + 1;
      try {
        const {job} = await getJob(id, {forceFresh: forceFresh || terminal});
        if (disposed || versions[id] !== version) return;
        const previous = snapshots.current;
        const errors = {...previous.errors};
        delete errors[id];
        snapshots.current = {...previous, errors, jobs: {
          ...previous.jobs, [id]: preferLatestJobSnapshot(previous.jobs[id] || null, job),
        }};
        setState({...snapshots.current});
      } catch {
        if (disposed || versions[id] !== version) return;
        snapshots.current = {...snapshots.current, errors: {
          ...snapshots.current.errors, [id]: "此项进度暂时读取失败，保留最近记录。",
        }};
        setState({...snapshots.current});
      }
    }
    readOne.current = id => read(id, true);
    async function poll() {
      const pending = childIds.filter(id => !isTerminalJobStatus(snapshots.current.jobs[id]?.status || ""));
      await Promise.all(pending.map(id => read(id)));
      if (!disposed && !terminal && childIds.some(id => !isTerminalJobStatus(snapshots.current.jobs[id]?.status || ""))) timer = setTimeout(poll, 2000);
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); readOne.current = null; };
  }, [batchId, idKey, terminal]);
  const visible = state.batchId === batchId ? state : empty();
  return {
    jobs: visible.jobs,
    readErrors: visible.errors,
    retry: (id: string) => { void readOne.current?.(id); },
  };
}

export type BatchJobSnapshots = ReturnType<typeof useBatchJobSnapshots>;
