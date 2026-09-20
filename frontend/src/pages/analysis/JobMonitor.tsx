import { Select } from "../../shared/components/Select";
import { analysisLabel } from "../../shared/utils/analysisLabels";
import { useSearchParams } from "react-router-dom";
import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import {
  Activity, Play, CheckCircle2, XCircle, Ban,
  AlertTriangle, Clock, Filter, Trash2,
} from "lucide-react";
import { usePolling } from "../../shared/hooks/usePolling";
import { useJobEvents } from "../../shared/hooks/useJobEvents";
import { bulkDeleteJobs, deleteJob, listJobs, getJob, getJobResults, listJobModules, type JobResultsResponse } from "../../shared/api/jobs";
import { listProjects, listProjectAssets } from "../../shared/api/projects";
import type { JobSummary } from "../../shared/types/domain";
import { PageHeader } from "../../shared/components/PageHeader";
import { Card } from "../../shared/components/Card";
import { MetricCard } from "../../shared/components/MetricCard";
import { SearchBar } from "../../shared/components/SearchBar";
import { JobRow } from "../../features/jobs/JobRow";
import { JobDetailPanel } from "../../features/jobs/JobDetailPanel";
import { Skeleton } from "../../shared/components/Skeleton";
import { EmptyState } from "../../shared/components/EmptyState";
import { useToast } from "../../shared/hooks/useToast";
import { buildAssetSets } from "../../features/assets/assetSets";

/* ── Component ── */

export function JobMonitor() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedRef = useRef<string | null>(null);
  const resultVersion = useRef(0);
  const pendingResults = useRef(new Map<string, Promise<JobResultsResponse>>());
  const [readError, setReadError] = useState("");
  useEffect(() => () => { selectedRef.current = null; resultVersion.current += 1; }, []);
  const filterStatus = searchParams.get("status") || "";
  const filterModule = searchParams.get("module") || "";
  const filterProjectId = searchParams.get("project") || "";
  const filterAssetSet = searchParams.get("asset_set") || "";
  const searchTerm = searchParams.get("q") || "";
  const offset = Math.max(0, Number(searchParams.get("offset")) || 0);
  const updateFilter = (key: string, value: string) => setSearchParams(previous => {
    const next = new URLSearchParams(previous);
    if (value) next.set(key, value); else next.delete(key);
    next.delete("offset");
    if (key === "project") next.delete("asset_set");
    return next;
  }, { replace: true });
  const setFilterStatus = (value: string) => updateFilter("status", value);
  const setFilterModule = (value: string) => updateFilter("module", value);
  const setFilterProjectId = (value: string) => updateFilter("project", value);
  const setFilterAssetSet = (value: string) => updateFilter("asset_set", value);
  const setSearchTerm = (value: string) => updateFilter("q", value);
  const changePage = (value: number) => setSearchParams(previous => {
    const next = new URLSearchParams(previous); next.set("offset", String(value)); return next;
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshTick, setRefreshTick] = useState(0);
  const [selectedJobIds, setSelectedJobIds] = useState<Set<string>>(new Set());
  const [deleteResults, setDeleteResults] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [jobDetailState, setJobDetailState] = useState<{
    job: JobSummary | null;
    loading: boolean;
  }>({ job: null, loading: false });
  const [detailState, setDetailState] = useState<{
    result: JobResultsResponse | null;
    loading: boolean;
  }>({ result: null, loading: false });

  const liveJob = useJobEvents(selectedJobId);
  const { addToast } = useToast();
  const lastResultFetchKeyRef = useRef("");

  // Poll jobs with auto-refresh toggle
  const jobsState = usePolling(
    () => {
      void refreshTick;
      return listJobs({ projectId: filterProjectId || undefined, status: filterStatus, module: filterModule, assetSet: filterAssetSet, search: searchTerm, offset, limit: 50 });
    },
    autoRefresh ? 3000 : null, [filterProjectId, filterStatus, filterModule, filterAssetSet, searchTerm, offset, refreshTick]
  );
  const jobs = jobsState.data?.jobs || [];
  const jobsLoading = jobsState.loading;
  const jobsError = jobsState.error;

  // Load modules for filter dropdown
  const [modules, setModules] = useState<{ key: string; label: string }[]>([]);
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => {
    listJobModules()
      .then((res) => setModules(res.modules))
      .catch(() => {});
    listProjects()
      .then((res) => setProjects(res.projects.map((p) => ({ id: p.id, name: p.name }))))
      .catch(() => {});
  }, []);

  const [assetSets, setAssetSets] = useState<string[]>([]);
  useEffect(() => {
    if (!filterProjectId) {
      setAssetSets([]);
      return;
    }
    listProjectAssets(filterProjectId, { pageSize: 200 })
      .then((res) => setAssetSets(buildAssetSets(res.assets).map((set) => set.name)))
      .catch(() => setAssetSets([]));
  }, [filterProjectId]);

  const filteredJobs = jobs;
  const stats = { running: 0, completed: 0, failed: 0, cancelled: 0, ...jobsState.data?.counts };
  const moduleOptions = [...new Map([...modules, ...(jobsState.data?.modules || []).map(key => ({key, label: analysisLabel(key)}))].map(item => [item.key, item])).values()];

  const selectedJobs = useMemo(
    () => filteredJobs.filter((job) => selectedJobIds.has(job.job_id || job.id)),
    [filteredJobs, selectedJobIds]
  );
  const terminalSelectedJobs = useMemo(
    () => selectedJobs.filter((job) => isTerminalJob(job)),
    [selectedJobs]
  );
  const allVisibleSelected = filteredJobs.length > 0 && filteredJobs.every((job) => selectedJobIds.has(job.job_id || job.id));

  const fetchJobResults = useCallback(async (jobId: string) => {
    const version = ++resultVersion.current;
    setReadError("");
    setDetailState((current) => ({ result: current.result, loading: true }));
    try {
      let request = pendingResults.current.get(jobId);
      if (!request) {
        request = getJobResults(jobId);
        pendingResults.current.set(jobId, request);
      }
      let data: JobResultsResponse;
      try { data = await request; }
      finally { if (pendingResults.current.get(jobId) === request) pendingResults.current.delete(jobId); }
      if (selectedRef.current !== jobId || version !== resultVersion.current) return;
      setDetailState({ result: data, loading: false });
      setJobDetailState({ job: data.job, loading: false });
      lastResultFetchKeyRef.current = `${jobId}:${data.job.status}:${data.job.updated_at || data.job.completed_at || data.job.progress}`;
    } catch (reason) {
      if (selectedRef.current !== jobId || version !== resultVersion.current) return;
      setReadError(reason instanceof Error ? reason.message : "结果读取失败");
      lastResultFetchKeyRef.current = "";
      setDetailState((current) => ({ result: current.result, loading: false }));
    }
  }, []);

  const handleSelectJob = useCallback(async (jobId: string) => {
    selectedRef.current = jobId;
    resultVersion.current += 1;
    setReadError("");
    setSearchParams(previous => { const next = new URLSearchParams(previous); next.set("job", jobId); return next; }, { replace: true });
    setSelectedJobId(jobId);
    lastResultFetchKeyRef.current = "";
    setJobDetailState({ job: null, loading: true });
    setDetailState({ result: null, loading: true });
    try {
      const data = await getJob(jobId);
      if (selectedRef.current !== jobId) return;
      setJobDetailState({ job: data.job, loading: false });
    } catch (reason) {
      if (selectedRef.current !== jobId) return;
      setReadError(reason instanceof Error ? reason.message : "任务读取失败");
      setJobDetailState({ job: null, loading: false });
      setDetailState({ result: null, loading: false });
      return;
    }
    await fetchJobResults(jobId);
  }, [fetchJobResults, setSearchParams]);

  useEffect(() => {
    const id = searchParams.get("job");
    if (id && selectedRef.current !== id) void handleSelectJob(id);
  }, [searchParams, handleSelectJob]);

  const handleOpenDetails = useCallback((job: JobSummary) => {
    const jobId = job.job_id || job.id;
    setJobDetailState({ job, loading: true });
    void handleSelectJob(jobId);
  }, [handleSelectJob]);

  const handleToggleSelected = useCallback((job: JobSummary) => {
    const jobId = job.job_id || job.id;
    setSelectedJobIds((current) => {
      const next = new Set(current);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  }, []);

  const handleSelectVisible = useCallback(() => {
    setSelectedJobIds((current) => {
      if (allVisibleSelected) {
        const next = new Set(current);
        filteredJobs.forEach((job) => next.delete(job.job_id || job.id));
        return next;
      }
      const next = new Set(current);
      filteredJobs.forEach((job) => next.add(job.job_id || job.id));
      return next;
    });
  }, [allVisibleSelected, filteredJobs]);

  const clearDeletedState = useCallback((deletedIds: string[]) => {
    setSelectedJobIds((current) => {
      const next = new Set(current);
      deletedIds.forEach((id) => next.delete(id));
      return next;
    });
    if (selectedJobId && deletedIds.includes(selectedJobId)) {
      selectedRef.current = null;
      resultVersion.current += 1;
      setSearchParams(previous => { const next = new URLSearchParams(previous); next.delete("job"); return next; }, { replace: true });
      setSelectedJobId(null);
      setJobDetailState({ job: null, loading: false });
      setDetailState({ result: null, loading: false });
    }
    setRefreshTick((tick) => tick + 1);
  }, [selectedJobId, setSearchParams]);

  const handleDeleteOne = useCallback(async (job: JobSummary) => {
    if (!isTerminalJob(job)) {
      addToast("请取消任务或等待任务结束后再删除。", "warning");
      return;
    }
    const jobId = job.job_id || job.id;
    const suffix = deleteResults ? " 及关联结果文件" : "";
    if (!confirm(`删除任务 ${job.module || jobId}${suffix}?`)) return;
    setDeleting(true);
    try {
      await deleteJob(jobId, { deleteResults });
      clearDeletedState([jobId]);
      addToast("任务已删除。", "success");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "删除任务失败。", "error");
    } finally {
      setDeleting(false);
    }
  }, [addToast, clearDeletedState, deleteResults]);

  const handleDeleteSelected = useCallback(async () => {
    if (terminalSelectedJobs.length === 0) {
      addToast("未选择已结束的任务，请先取消运行中的任务。", "warning");
      return;
    }
    const skipped = selectedJobs.length - terminalSelectedJobs.length;
    const suffix = deleteResults ? " 及关联结果文件" : "";
    const message = [
      `删除 ${terminalSelectedJobs.length} 个已选任务${suffix}?`,
      skipped > 0 ? `${skipped} 个运行中或等待中的任务将被跳过。` : "",
    ].filter(Boolean).join("\n");
    if (!confirm(message)) return;
    setDeleting(true);
    const ids = terminalSelectedJobs.map((job) => job.job_id || job.id);
    try {
      const response = await bulkDeleteJobs(ids, { deleteResults });
      const deletedIds = response.results.filter((item) => item.success).map((item) => item.job_id);
      clearDeletedState(deletedIds);
      const failed = response.results.length - deletedIds.length;
      addToast(failed ? `已删除 ${deletedIds.length} 项，${failed} 项失败。` : `已删除 ${deletedIds.length} 项任务。`, failed ? "warning" : "success");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "删除所选任务失败。", "error");
    } finally {
      setDeleting(false);
    }
  }, [addToast, clearDeletedState, deleteResults, selectedJobs.length, terminalSelectedJobs]);

  // Refresh detail when live job event arrives
  useEffect(() => {
    if (!selectedJobId || !liveJob.event || (liveJob.event.job.job_id || liveJob.event.job.id) !== selectedJobId) return;
    const event = liveJob.event;
    setJobDetailState((prev) => {
      if (!prev.job) return prev;
      const selectedId = prev.job.job_id || prev.job.id;
      const eventId = event.job.job_id || event.job.id;
      if (selectedId !== eventId) return prev;
      return { job: event.job, loading: false };
    });
    if (event.status === "completed" || event.status === "failed" || event.status === "cancelled") {
      const key = `${selectedJobId}:${event.status}:${event.job.updated_at || event.job.completed_at || event.job.progress}`;
      if (lastResultFetchKeyRef.current === key) return;
      lastResultFetchKeyRef.current = key;
      void fetchJobResults(selectedJobId);
      return;
    }
    // Update the status in-place for in-progress jobs
    setDetailState((prev) => {
      if (!prev.result) return prev;
      return {
        result: { ...prev.result, job: event.job, status: event.status },
        loading: false,
      };
    });
  }, [fetchJobResults, liveJob.event, selectedJobId]);

  // Keep the right detail panel in sync with the left list polling. This is
  // the fallback path when SSE disconnects or a terminal event is missed.
  useEffect(() => {
    if (!selectedJobId) return;
    const polledJob = jobs.find((job) => (job.job_id || job.id) === selectedJobId);
    if (!polledJob) return;

    setJobDetailState((current) => {
      const currentId = current.job ? current.job.job_id || current.job.id : "";
      if (currentId && currentId !== selectedJobId) return current;
      return { job: polledJob, loading: false };
    });
    setDetailState((current) => {
      if (!current.result) return current;
      return {
        result: { ...current.result, job: polledJob, status: polledJob.status },
        loading: current.loading,
      };
    });

    if (!isTerminalJob(polledJob)) {
      lastResultFetchKeyRef.current = "";
      return;
    }

    const fetchKey = `${selectedJobId}:${polledJob.status}:${polledJob.updated_at || polledJob.completed_at || polledJob.progress}`;
    if (lastResultFetchKeyRef.current === fetchKey) return;
    lastResultFetchKeyRef.current = fetchKey;
    void fetchJobResults(selectedJobId);
  }, [fetchJobResults, jobs, selectedJobId]);

  return (
    <>
      <PageHeader title="任务与结果" subtitle="跟踪分析进度，查看配置和结果">
        <label style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", fontSize: "0.85rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          自动刷新
        </label>
      </PageHeader>

      {readError && <div role="alert"><p>{readError}</p><button className="btn btn-secondary" onClick={() => selectedJobId && handleSelectJob(selectedJobId)}>重新读取任务</button></div>}
      {/* Error banner */}
      {jobsError && (
        <div style={{
          padding: "var(--spacing-md) var(--spacing-lg)", borderRadius: "var(--radius-panel)",
          background: "#ff3b3018", border: "1px solid #ff3b3030",
          color: "var(--danger)", fontSize: "0.85rem", display: "flex",
          alignItems: "center", gap: "var(--spacing-sm)",
        }}>
          <AlertTriangle size={16} /> {jobsError}
        </div>
      )}

      {/* Stats bar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "var(--spacing-lg)" }}>
        <MetricCard icon={Play} label="运行中" value={stats.running} color="var(--warning)" />
        <MetricCard icon={CheckCircle2} label="已完成" value={stats.completed} color="var(--success)" />
        <MetricCard icon={XCircle} label="失败" value={stats.failed} color="var(--danger)" />
        <MetricCard icon={Ban} label="已取消" value={stats.cancelled} color="#aeaeb2" />
      </div>

      {/* Filter toolbar */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
          <Filter size={16} style={{ color: "var(--text-tertiary)" }} />
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            项目：
            <Select ariaLabel="筛选项目" value={filterProjectId} onChange={setFilterProjectId} style={{minWidth:150}} options={[{value:"",label:"全部"},...projects.map(p=>({value:p.id,label:p.name}))]} />
          </label>
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            数据集：
            <Select ariaLabel="筛选数据集" value={filterAssetSet} onChange={setFilterAssetSet} disabled={!filterProjectId} style={{minWidth:120}} options={[{value:"",label:"全部"},...assetSets.map(value=>({value,label:value}))]} />
          </label>
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            状态：
            <Select ariaLabel="筛选状态" value={filterStatus} onChange={setFilterStatus} style={{minWidth:110}} options={[{value:"",label:"全部"},{value:"queued",label:"等待中"},{value:"running",label:"运行中"},{value:"completed",label:"已完成"},{value:"failed",label:"失败"},{value:"cancelled",label:"已取消"},{value:"interrupted",label:"已中断"}]} />
          </label>
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            模块：
            <Select ariaLabel="筛选模块" value={filterModule} onChange={setFilterModule} style={{minWidth:150}} options={[{value:"",label:"全部"},...moduleOptions.map(m=>({value:m.key,label:m.label}))]} />
          </label>
          <div style={{ flex: 1, minWidth: "200px" }}>
            <SearchBar
              placeholder="搜索任务名称或编号…"
              value={searchTerm}
              onChange={setSearchTerm}
              onClear={() => setSearchTerm("")}
            />
          </div>
          <button
            onClick={() => {
              setSearchParams(selectedJobId ? {job: selectedJobId} : {});
              setSelectedJobIds(new Set());
            }}
            style={{
              padding: "6px 14px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--separator)",
              background: "var(--bg-elevated)",
              color: "var(--text-secondary)",
              fontSize: "0.8rem",
              cursor: "pointer",
            }}
          >
            清空
          </button>
        </div>
      </Card>

      <nav aria-label="任务分页" style={{display:"flex", alignItems:"center", gap:12, flexWrap:"wrap"}}>
        <span role="status">共 {jobsState.data?.total ?? jobs.length} 项任务 · 第 {Math.floor(offset / 50) + 1} 页</span>
        <button className="btn btn-secondary" disabled={offset === 0 || jobsLoading} onClick={() => changePage(Math.max(0, offset - 50))}>上一页</button>
        <button className="btn btn-secondary" disabled={!jobsState.data?.has_more || jobsLoading} onClick={() => changePage(offset + 50)}>下一页</button>
      </nav>
      {/* Two-panel layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(min(420px, 100%), 1fr))",
          gap: "var(--spacing-lg)",
          alignItems: "start",
        }}
      >
        {/* Left: Job list */}
        <div>
          {filteredJobs.length > 0 && (
            <Card>
              <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
                <button
                  type="button"
                  onClick={handleSelectVisible}
                  disabled={deleting}
                  style={smallButtonStyle}
                >
                  {allVisibleSelected ? "取消选中筛选结果" : "选中筛选结果"}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedJobIds(new Set())}
                  disabled={deleting || selectedJobIds.size === 0}
                  style={smallButtonStyle}
                >
                  清空
                </button>
                <label style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--text-secondary)", fontSize: "0.78rem" }}>
                  <input
                    type="checkbox"
                    checked={deleteResults}
                    onChange={(event) => setDeleteResults(event.target.checked)}
                    disabled={deleting}
                  />
                  同时删除关联结果
                </label>
                <span style={{ color: "var(--text-tertiary)", fontSize: "0.78rem" }}>
                  {selectedJobIds.size} 已选择 · {terminalSelectedJobs.length} 可删除
                </span>
                <button
                  type="button"
                  onClick={handleDeleteSelected}
                  disabled={deleting || terminalSelectedJobs.length === 0}
                  style={{
                    ...smallButtonStyle,
                    marginLeft: "auto",
                    borderColor: "color-mix(in srgb, var(--danger) 55%, var(--separator))",
                    color: "var(--danger)",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  <Trash2 size={14} />
                  {deleting ? "正在删除…" : "删除所选"}
                </button>
              </div>
            </Card>
          )}
          {jobsLoading && filteredJobs.length === 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
              {[1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} height="72px" />
              ))}
            </div>
          ) : filteredJobs.length === 0 ? (
            <EmptyState
              icon={Clock}
              title="暂无任务"
              description={filterStatus || filterModule || filterProjectId || filterAssetSet || searchTerm ? "请调整筛选条件。" : "请先进入分析中心提交任务。"}
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
              {filteredJobs.map((job) => (
                <JobRow
                  key={job.job_id || job.id}
                  job={job}
                  onOpenDetails={handleOpenDetails}
                  selected={selectedJobIds.has(job.job_id || job.id)}
                  onToggleSelected={handleToggleSelected}
                  onDelete={handleDeleteOne}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right: Job detail with SSE */}
        <div style={{ position: "sticky", top: "var(--spacing-lg)", minWidth: 0 }}>
          {!selectedJobId ? (
            <Card>
              <EmptyState
                icon={Activity}
                title="选择任务"
                description="点击任务查看配置、运行状态及结果。"
              />
            </Card>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
              {/* Live connection indicator */}
              {liveJob.connected && (
                <div style={{
                  display: "flex", alignItems: "center", gap: "var(--spacing-xs)",
                  padding: "var(--spacing-sm) var(--spacing-md)",
                  borderRadius: "var(--radius-pill)",
                  background: "#34c75918",
                  color: "var(--success)",
                  fontSize: "0.78rem",
                  fontWeight: 500,
                  border: "1px solid #34c75930",
                }}>
                  <span style={{
                    width: "6px", height: "6px", borderRadius: "50%",
                    background: "var(--success)", animation: "pulse 2s infinite",
                  }} />
                  实时更新
                </div>
              )}
              {liveJob.error && (
                <div style={{
                  padding: "var(--spacing-sm) var(--spacing-md)",
                  borderRadius: "var(--radius-pill)",
                  background: "#ff3b3018",
                  color: "var(--danger)",
                  fontSize: "0.78rem",
                  border: "1px solid #ff3b3030",
                }}>
                  {liveJob.error}
                </div>
              )}
              {jobDetailState.job && (
                <JobDetailPanel
                  job={jobDetailState.job}
                  result={detailState.result}
                  resultLoading={detailState.loading}
                  resultError={readError}
                  onRetry={() => selectedJobId && void fetchJobResults(selectedJobId)}
                  loading={jobDetailState.loading}
                  onClose={() => {
                    selectedRef.current = null;
            setSearchParams(previous => { const next = new URLSearchParams(previous); next.delete("job"); return next; }, { replace: true });
            setSelectedJobId(null);
                    setJobDetailState({ job: null, loading: false });
                    setDetailState({ result: null, loading: false });
                  }}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

const labelStyle: React.CSSProperties = {
  display: "flex",
  fontSize: "0.78rem",
  fontWeight: 500,
  color: "var(--text-secondary)",
};


const smallButtonStyle: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-secondary)",
  fontSize: "0.78rem",
  fontWeight: 500,
  cursor: "pointer",
};

function isTerminalJob(job: JobSummary): boolean {
  return ["completed", "failed", "cancelled", "interrupted"].includes(job.status);
}
