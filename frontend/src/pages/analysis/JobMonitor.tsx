import { ApiError } from "../../shared/api/client";
import { Select } from "../../shared/components/Select";
import { isTerminalJobStatus, preferLatestJobSnapshot } from "../../shared/utils/jobState";
import { analysisLabel } from "../../shared/utils/analysisLabels";
import { clearResultAddress } from "../../features/results/resultAddress";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import {
  Activity, Play, CheckCircle2, XCircle, Ban,
  AlertTriangle, Clock, Filter, Trash2, PackageCheck, ArrowLeft,
} from "lucide-react";
import { usePolling } from "../../shared/hooks/usePolling";
import { useJobEvents } from "../../shared/hooks/useJobEvents";
import { bulkDeleteJobs, deleteJob, downloadResultArchive, listJobs, getJob, getJobResults, listJobModules, type JobResultsResponse } from "../../shared/api/jobs";
import { listProjectDatasets } from "../../shared/api/projects";
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
import { ProjectPicker } from "../../features/projects/ProjectPicker";
import "./JobMonitor.css";

/* ── Component ── */

export function JobMonitor() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const selectedRef = useRef<string | null>(null);
  const detailElement = useRef<HTMLDivElement>(null);
  const listElement = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const restoreListFocus = useRef(false);
  const selectedSnapshot = useRef<JobSummary | null>(null);
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
  const [downloadingResults, setDownloadingResults] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [jobDetailState, setJobDetailState] = useState<{
    job: JobSummary | null;
    loading: boolean;
  }>({ job: null, loading: false });
  const [detailState, setDetailState] = useState<{
    result: JobResultsResponse | null;
    loading: boolean;
  }>({ result: null, loading: false });

  const liveJob = useJobEvents(readError && !jobDetailState.job && !jobDetailState.loading ? null : selectedJobId);
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
  useEffect(() => {
    listJobModules()
      .then((res) => setModules(res.modules))
      .catch(() => {});
  }, []);

  const [assetSets, setAssetSets] = useState<string[]>([]);
  useEffect(() => {
    if (!filterProjectId) {
      setAssetSets([]);
      return;
    }
    let active = true;
    listProjectDatasets(filterProjectId)
      .then((res) => { if (active) setAssetSets(res.datasets.map(dataset => dataset.name)); })
      .catch(() => { if (active) setAssetSets([]); });
    return () => { active = false; };
  }, [filterProjectId]);

  const filteredJobs = useMemo(() => jobs.map(job => {
    if (!jobDetailState.job || (job.job_id || job.id) !== selectedJobId) return job;
    return preferLatestJobSnapshot(jobDetailState.job, job);
  }), [jobs, jobDetailState.job, selectedJobId]);
  const stats = { queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0, interrupted: 0, ...jobsState.data?.counts };
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

  const fetchJobResults = useCallback(async (jobId: string, forceFresh = false) => {
    const version = ++resultVersion.current;
    setReadError("");
    setDetailState((current) => ({ result: current.result, loading: true }));
    try {
      let request = forceFresh ? undefined : pendingResults.current.get(jobId);
      if (!request) {
        request = getJobResults(jobId, { forceFresh });
        pendingResults.current.set(jobId, request);
      }
      let data: JobResultsResponse;
      try { data = await request; }
      finally { if (pendingResults.current.get(jobId) === request) pendingResults.current.delete(jobId); }
      if (selectedRef.current !== jobId || version !== resultVersion.current) return;
      const job = preferLatestJobSnapshot(selectedSnapshot.current, data.job);
      selectedSnapshot.current = job;
      setDetailState({ result: { ...data, job, status: job.status }, loading: false });
      setJobDetailState({ job, loading: false });
      lastResultFetchKeyRef.current = `${jobId}:${job.status}:${job.updated_at || job.completed_at || job.progress}`;
    } catch (reason) {
      if (selectedRef.current !== jobId || version !== resultVersion.current) return;
      setReadError(jobReadMessage(reason, "结果读取失败"));
      lastResultFetchKeyRef.current = "";
      setDetailState((current) => ({ result: current.result, loading: false }));
    }
  }, []);

  const handleSelectJob = useCallback(async (jobId: string) => {
    const active = document.activeElement;
    if (active instanceof HTMLElement && active !== document.body && !detailElement.current?.contains(active)) returnFocus.current = active;
    if (selectedRef.current === jobId) detailElement.current?.focus({ preventScroll: true });
    selectedRef.current = jobId;
    selectedSnapshot.current = null;
    resultVersion.current += 1;
    setReadError("");
    if (searchParams.get("job") !== jobId) {
      const next = clearResultAddress(searchParams);
      next.set("job", jobId);
      navigate({pathname:location.pathname,search:"?"+next,hash:location.hash},{replace:true});
    }
    setSelectedJobId(jobId);
    lastResultFetchKeyRef.current = "";
    setJobDetailState({ job: null, loading: true });
    setDetailState({ result: null, loading: true });
    try {
      const data = await getJob(jobId);
      if (selectedRef.current !== jobId) return;
      const job = preferLatestJobSnapshot(selectedSnapshot.current, data.job);
      selectedSnapshot.current = job;
      setJobDetailState({ job, loading: false });
    } catch (reason) {
      if (selectedRef.current !== jobId) return;
      setReadError(jobReadMessage(reason, "任务读取失败"));
      setJobDetailState({ job: null, loading: false });
      setDetailState({ result: null, loading: false });
      return;
    }
    await fetchJobResults(jobId);
  }, [fetchJobResults, searchParams, navigate, location.pathname, location.hash]);

  useEffect(() => {
    const id = searchParams.get("job");
    if (id && selectedRef.current !== id) void handleSelectJob(id);
  }, [searchParams, handleSelectJob]);

  const handleCloseDetails = useCallback(() => {
    selectedRef.current = null;
    selectedSnapshot.current = null;
    resultVersion.current += 1;
    restoreListFocus.current = true;
    const next = clearResultAddress(searchParams);
    next.delete("job");
    navigate({pathname:location.pathname,search:next.toString() ? "?"+next : "",hash:location.hash},{replace:true});
    setSelectedJobId(null);
    setJobDetailState({ job: null, loading: false });
    setDetailState({ result: null, loading: false });
    setReadError("");
  }, [searchParams, navigate, location.pathname, location.hash]);

  useEffect(() => {
    if (selectedJobId) {
      detailElement.current?.focus({ preventScroll: true });
      if (window.matchMedia?.("(max-width: 1100px)").matches) detailElement.current?.scrollIntoView({ block: "start", behavior: "instant" });
    } else if (restoreListFocus.current) {
      restoreListFocus.current = false;
      const target = returnFocus.current?.isConnected ? returnFocus.current : listElement.current;
      returnFocus.current = null;
      target?.focus();
    }
  }, [selectedJobId]);

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
      handleCloseDetails();
    }
    setRefreshTick((tick) => tick + 1);
  }, [selectedJobId, handleCloseDetails]);

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

  const handleDownloadSelectedResults = useCallback(async () => {
    if (!terminalSelectedJobs.length) {
      addToast("请选择已结束且有结果的任务。", "warning");
      return;
    }
    setDownloadingResults(true);
    try {
      const results = await Promise.all(terminalSelectedJobs.map((job) => getJobResults(job.job_id || job.id)));
      const items = results.flatMap((result) => {
        const jobId = result.job.job_id || result.job.id;
        return [
          ...(result.outputs || []).flatMap((output) => output.url ? [{ job_id: jobId, url: output.url }] : []),
          ...(result.assets || []).flatMap((asset) => [asset.download_url, asset.preview_url].filter((url): url is string => Boolean(url)).map((url) => ({ job_id: jobId, url }))),
        ];
      });
      const uniqueItems = [...new Map(items.map((item) => [`${item.job_id}:${item.url}`, item])).values()];
      if (!uniqueItems.length) {
        addToast("所选任务没有可打包的结果文件。", "warning");
        return;
      }
      if (uniqueItems.length > 200) {
        addToast(`共找到 ${uniqueItems.length} 个文件，单次最多打包 200 个，请减少所选任务。`, "warning");
        return;
      }
      await downloadResultArchive(uniqueItems);
      addToast(`已开始下载 ${uniqueItems.length} 个结果文件。`, "success");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "读取所选任务结果失败。", "error");
    } finally {
      setDownloadingResults(false);
    }
  }, [addToast, terminalSelectedJobs]);

  // Refresh detail when live job event arrives
  useEffect(() => {
    if (!selectedJobId || !liveJob.event || (liveJob.event.job.job_id || liveJob.event.job.id) !== selectedJobId) return;
    if (selectedRef.current !== selectedJobId) return;
    const job = preferLatestJobSnapshot(selectedSnapshot.current, liveJob.event.job);
    selectedSnapshot.current = job;
    const event = { ...liveJob.event, job, status: job.status };
    setJobDetailState((prev) => {
      if (!prev.job) return prev;
      const selectedId = prev.job.job_id || prev.job.id;
      const eventId = event.job.job_id || event.job.id;
      if (selectedId !== eventId) return prev;
      return { job: preferLatestJobSnapshot(prev.job, event.job), loading: false };
    });
    if (isTerminalJobStatus(event.status)) {
      const key = `${selectedJobId}:${event.status}:${event.job.updated_at || event.job.completed_at || event.job.progress}`;
      if (lastResultFetchKeyRef.current === key) return;
      lastResultFetchKeyRef.current = key;
      void fetchJobResults(selectedJobId, true);
      return;
    }
    // Update the status in-place for in-progress jobs
    setDetailState((prev) => {
      if (!prev.result) return prev;
      return {
        result: { ...prev.result, job: preferLatestJobSnapshot(prev.result.job, event.job), status: preferLatestJobSnapshot(prev.result.job, event.job).status },
        loading: false,
      };
    });
  }, [fetchJobResults, liveJob.event, selectedJobId]);

  // Keep the right detail panel in sync with the left list polling. This is
  // the fallback path when SSE disconnects or a terminal event is missed.
  useEffect(() => {
    if (!selectedJobId) return;
    const polledJob = jobs.find((job) => (job.job_id || job.id) === selectedJobId);
    if (!polledJob || selectedRef.current !== selectedJobId) return;
    const latest = preferLatestJobSnapshot(selectedSnapshot.current, polledJob);
    selectedSnapshot.current = latest;

    setJobDetailState((current) => {
      const currentId = current.job ? current.job.job_id || current.job.id : "";
      if (currentId && currentId !== selectedJobId) return current;
      return { job: preferLatestJobSnapshot(current.job, latest), loading: false };
    });
    setDetailState((current) => {
      if (!current.result) return current;
      return {
        result: { ...current.result, job: preferLatestJobSnapshot(current.result.job, latest), status: preferLatestJobSnapshot(current.result.job, latest).status },
        loading: current.loading,
      };
    });

    if (!isTerminalJob(latest)) {
      lastResultFetchKeyRef.current = "";
      return;
    }

    const fetchKey = `${selectedJobId}:${latest.status}:${latest.updated_at || latest.completed_at || latest.progress}`;
    if (lastResultFetchKeyRef.current === fetchKey) return;
    lastResultFetchKeyRef.current = fetchKey;
    void fetchJobResults(selectedJobId, true);
  }, [fetchJobResults, jobs, selectedJobId]);

  return (
    <div className="job-monitor" data-detail-open={Boolean(selectedJobId)}>
      <div className="job-monitor-overview">
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
        <MetricCard icon={Clock} label="等待中" value={stats.queued} color="var(--accent)" />
        <MetricCard icon={Play} label="运行中" value={stats.running} color="var(--warning)" />
        <MetricCard icon={CheckCircle2} label="已完成" value={stats.completed} color="var(--success)" />
        <MetricCard icon={XCircle} label="失败" value={stats.failed} color="var(--danger)" />
        <MetricCard icon={Ban} label="已取消" value={stats.cancelled} color="#aeaeb2" />
        <MetricCard icon={AlertTriangle} label="已中断" value={stats.interrupted} color="var(--danger)" />
      </div>

      {/* Filter toolbar */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
          <Filter size={16} style={{ color: "var(--text-tertiary)" }} />
          <div style={{ minWidth: 180, maxWidth: "100%" }}><ProjectPicker label="筛选项目" value={filterProjectId} onChange={setFilterProjectId} allowAll /></div>
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
      </div>
      {/* Two-panel layout */}
      <div className="job-monitor-panels">
        {/* Left: Job list */}
        <div className="job-monitor-list" ref={listElement} role="region" aria-label="任务列表" tabIndex={-1}>
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
                  onClick={handleDownloadSelectedResults}
                  disabled={downloadingResults || terminalSelectedJobs.length === 0}
                  style={{ ...smallButtonStyle, display: "inline-flex", alignItems: "center", gap: "6px" }}
                >
                  <PackageCheck size={14} />
                  {downloadingResults ? "正在整理结果…" : "打包所选结果"}
                </button>
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
                  onJobChanged={() => setRefreshTick(value => value + 1)}
                  onRetried={newJobId => { addToast("已创建新的重试任务，原任务记录保留。", "success"); void handleSelectJob(newJobId); }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Right: Job detail with SSE */}
        <div className="job-monitor-details" ref={detailElement} role="region" aria-label="任务详情" tabIndex={-1}>
          {selectedJobId && <div className="job-monitor-mobile-navigation"><button className="btn btn-secondary" type="button" onClick={handleCloseDetails}><ArrowLeft size={16}/>返回任务列表</button></div>}
          {readError && <div className="job-monitor-read-error" role="alert"><strong>任务信息读取失败</strong><p>{readError}</p><button className="btn btn-secondary" onClick={() => selectedJobId && handleSelectJob(selectedJobId)}>重新读取任务</button></div>}
          {selectedJobId && !jobDetailState.job && jobDetailState.loading && <Card><p role="status">正在读取任务详情…</p><Skeleton height="120px"/></Card>}
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
                  resultFocus={searchParams.get("result_job") || undefined}
                  result={detailState.result}
                  resultLoading={detailState.loading}
                  resultError={readError}
                  onRetry={() => selectedJobId && void fetchJobResults(selectedJobId)}
                  loading={jobDetailState.loading}
                  onClose={handleCloseDetails}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
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
  return isTerminalJobStatus(job.status);
}
function jobReadMessage(reason: unknown, fallback: string) {
  if (reason instanceof ApiError && reason.status === 404 && reason.payload !== null && typeof reason.payload === "object" && "error" in reason.payload && reason.payload.error === "JOB_NOT_FOUND") {
    return "无法找到该任务，请返回任务列表核对。";
  }
  return reason instanceof Error ? reason.message : fallback;
}
