import { useEffect, useState } from "react";
import { History, FolderOpen, Play, RefreshCw } from "lucide-react";
import { listJobs } from "../../../shared/api/jobs";
import { useJobResult } from "../../../shared/hooks/useJobResult";
import type { JobSummary } from "../../../shared/types/domain";
import { JobList } from "../../jobs/JobList";
import { JobResultPanel } from "../../jobs/JobResultPanel";
import { EmptyState } from "../../../shared/components/EmptyState";

interface Stage6HistoryProps {
  moduleFilter?: string;
  initialJobId?: string;
  projectId: string;
  onSelectResult: (jobId: string) => void;
}

export function Stage6History(props: Stage6HistoryProps) {
  return <ProjectHistory key={`${props.projectId}:${props.moduleFilter || "all"}`} {...props} />;
}

function ProjectHistory({ projectId, onSelectResult, moduleFilter, initialJobId }: Stage6HistoryProps) {
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [loading, setLoading] = useState(Boolean(projectId));
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selectedJobId, setSelectedJobId] = useState<string | null>(initialJobId || null);
  const resultState = useJobResult(selectedJobId);

  useEffect(() => {
    if (!projectId) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    setLoading(true);
    async function poll() {
      try {
        const response = await listJobs({ projectId, limit: 50, offset, module: moduleFilter, search, status: filter === "all" ? "" : filter === "active" ? "queued,running" : filter === "failed" ? "failed,cancelled,interrupted" : filter });
        if (disposed) return;
        if (!response.success) throw new Error("无法读取任务历史");
        setJobs(response.jobs); setTotal(response.total ?? response.jobs.length); setHasMore(Boolean(response.has_more));
        setError("");
      } catch (reason) {
        if (!disposed) setError(reason instanceof Error ? reason.message : "无法读取任务历史");
      } finally {
        if (!disposed) {
          setLoading(false);
          timer = setTimeout(poll, 5000);
        }
      }
    }
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [projectId, revision, offset, moduleFilter, search, filter]);

  const visibleJobs = jobs;

  return <section style={{ display: "grid", gap: "var(--spacing-lg)" }}>
    <div>
      <h2 style={{ margin: 0 }}>分析历史</h2>
      <p style={{ color: "var(--text-secondary)" }}>查看项目分析历史，按条件检索并打开结果。</p>
    </div>
    {!projectId ? <EmptyState icon={FolderOpen} title="尚未选择项目" description="请先返回数据准备步骤选择项目。" /> : <>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)", alignItems: "end" }}>
        <label style={{ flex: "1 1 220px", minWidth: 0 }}>搜索任务
          <input className="input" type="search" value={search} onChange={event => { setSearch(event.target.value); setOffset(0); }} placeholder="输入模块名称或任务编号" />
        </label>
        <label>任务状态
          <select className="select" value={filter} onChange={event => { setFilter(event.target.value); setOffset(0); }}>
            <option value="all">全部状态</option><option value="active">等待 / 运行中</option>
            <option value="completed">已完成</option><option value="failed">失败 / 取消 / 中断</option>
          </select>
        </label>
        <button className="btn btn-secondary" disabled={loading} onClick={() => setRevision(value => value + 1)}><RefreshCw size={16} />刷新列表</button>
        <button className="btn btn-primary" onClick={() => onSelectResult("")}><Play size={16} />新建分析</button>
      </div>
      {error && <div role="alert" style={{ color: "var(--danger)" }}>任务历史读取失败：{error}。可点击“刷新列表”重试。</div>}
      {!loading && !error && jobs.length === 0 ? <EmptyState icon={History} title="暂无分析历史" description="点击“新建分析”开始当前项目的第一次分析。" /> : <>
        <p role="status" style={{ margin: 0, color: "var(--text-secondary)" }}>共 {total} 项任务 · 第 {Math.floor(offset / 50) + 1} 页</p>
        <JobList jobs={visibleJobs} loading={loading && jobs.length === 0} emptyLabel={error ? "暂时无法显示任务。" : "没有符合条件的任务，请调整搜索或筛选条件。"} onSelectResult={setSelectedJobId} />
      </>}
      <div style={{display:"flex",gap:12}}><button className="btn btn-secondary" disabled={!offset || loading} onClick={() => setOffset(Math.max(0,offset-50))}>上一页</button><button className="btn btn-secondary" disabled={!hasMore || loading} onClick={() => setOffset(offset+50)}>下一页</button></div>
      {selectedJobId && <section aria-label="任务结果" style={{ display: "grid", gap: "var(--spacing-md)", minWidth: 0 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>任务结果</h3>
          <code style={{ overflowWrap: "anywhere" }}>{selectedJobId}</code>
          <button className="btn btn-secondary" onClick={() => setSelectedJobId(null)}>收起结果</button>
        </div>
        {resultState.error && <div role="alert"><p>{resultState.error}</p><button className="btn btn-secondary" onClick={resultState.retry}>重新读取结果</button></div>}
        {(!resultState.error || resultState.result) && <JobResultPanel result={resultState.result} loading={!resultState.result} />}
      </section>}
    </>}
  </section>;
}
