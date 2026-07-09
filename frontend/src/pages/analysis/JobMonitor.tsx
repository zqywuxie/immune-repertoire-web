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
  const [filterStatus, setFilterStatus] = useState("");
  const [filterModule, setFilterModule] = useState("");
  const [filterProjectId, setFilterProjectId] = useState("");
  const [filterAssetSet, setFilterAssetSet] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
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
      return listJobs({ projectId: filterProjectId || undefined, limit: 100 });
    },
    autoRefresh ? 3000 : 999999
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
    setFilterAssetSet("");
    if (!filterProjectId) {
      setAssetSets([]);
      return;
    }
    listProjectAssets(filterProjectId, { pageSize: 200 })
      .then((res) => setAssetSets(buildAssetSets(res.assets).map((set) => set.name)))
      .catch(() => setAssetSets([]));
  }, [filterProjectId]);

  // Filter jobs
  const filteredJobs = useMemo(() => {
    return jobs.filter((j) => {
      const statusMatch = !filterStatus || j.status === filterStatus;
      const moduleMatch = !filterModule || (j.module || "").toLowerCase().includes(filterModule.toLowerCase());
      const setMatch = !filterAssetSet || String((j.payload || {}).asset_set || "").toLowerCase() === filterAssetSet.toLowerCase();
      const searchMatch = !searchTerm || (j.job_id || j.id || "").toLowerCase().includes(searchTerm.toLowerCase());
      return statusMatch && moduleMatch && setMatch && searchMatch;
    });
  }, [jobs, filterStatus, filterModule, filterAssetSet, searchTerm]);

  // Stats
  const stats = useMemo(() => {
    const counts = { running: 0, completed: 0, failed: 0, cancelled: 0 };
    for (const j of jobs) {
      if (j.status in counts) counts[j.status as keyof typeof counts]++;
    }
    return counts;
  }, [jobs]);

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
    setDetailState((current) => ({ result: current.result, loading: true }));
    try {
      const data = await getJobResults(jobId);
      setDetailState({ result: data, loading: false });
      setJobDetailState({ job: data.job, loading: false });
    } catch {
      lastResultFetchKeyRef.current = "";
      setDetailState((current) => ({ result: current.result, loading: false }));
    }
  }, []);

  const handleSelectJob = useCallback(async (jobId: string) => {
    setSelectedJobId(jobId);
    lastResultFetchKeyRef.current = "";
    setJobDetailState((current) => ({ job: current.job, loading: true }));
    setDetailState({ result: null, loading: true });
    try {
      const data = await getJob(jobId);
      setJobDetailState({ job: data.job, loading: false });
    } catch {
      setJobDetailState((current) => ({ job: current.job, loading: false }));
    }
    await fetchJobResults(jobId);
  }, [fetchJobResults]);

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
      setSelectedJobId(null);
      setJobDetailState({ job: null, loading: false });
      setDetailState({ result: null, loading: false });
    }
    setRefreshTick((tick) => tick + 1);
  }, [selectedJobId]);

  const handleDeleteOne = useCallback(async (job: JobSummary) => {
    if (!isTerminalJob(job)) {
      addToast("Cancel or wait for the job to finish before deleting it.", "warning");
      return;
    }
    const jobId = job.job_id || job.id;
    const suffix = deleteResults ? " and attached result files/assets" : "";
    if (!confirm(`Delete job ${job.module || jobId}${suffix}?`)) return;
    setDeleting(true);
    try {
      await deleteJob(jobId, { deleteResults });
      clearDeletedState([jobId]);
      addToast("Job deleted.", "success");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Failed to delete job.", "error");
    } finally {
      setDeleting(false);
    }
  }, [addToast, clearDeletedState, deleteResults]);

  const handleDeleteSelected = useCallback(async () => {
    if (terminalSelectedJobs.length === 0) {
      addToast("No terminal jobs selected. Cancel running jobs first.", "warning");
      return;
    }
    const skipped = selectedJobs.length - terminalSelectedJobs.length;
    const suffix = deleteResults ? " and attached result files/assets" : "";
    const message = [
      `Delete ${terminalSelectedJobs.length} selected job(s)${suffix}?`,
      skipped > 0 ? `${skipped} running/queued job(s) will be skipped.` : "",
    ].filter(Boolean).join("\n");
    if (!confirm(message)) return;
    setDeleting(true);
    const ids = terminalSelectedJobs.map((job) => job.job_id || job.id);
    try {
      const response = await bulkDeleteJobs(ids, { deleteResults });
      const deletedIds = response.results.filter((item) => item.success).map((item) => item.job_id);
      clearDeletedState(deletedIds);
      const failed = response.results.length - deletedIds.length;
      addToast(failed ? `Deleted ${deletedIds.length}; ${failed} failed.` : `Deleted ${deletedIds.length} job(s).`, failed ? "warning" : "success");
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Failed to delete selected jobs.", "error");
    } finally {
      setDeleting(false);
    }
  }, [addToast, clearDeletedState, deleteResults, selectedJobs.length, terminalSelectedJobs]);

  // Refresh detail when live job event arrives
  useEffect(() => {
    if (!selectedJobId || !liveJob.event) return;
    const event = liveJob.event;
    setJobDetailState((prev) => {
      if (!prev.job) return prev;
      const selectedId = prev.job.job_id || prev.job.id;
      const eventId = event.job.job_id || event.job.id;
      if (selectedId !== eventId) return prev;
      return { job: event.job, loading: false };
    });
    if (event.status === "completed" || event.status === "failed" || event.status === "cancelled") {
      lastResultFetchKeyRef.current = `${selectedJobId}:${event.status}:${event.job.updated_at || event.job.completed_at || ""}`;
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
      <PageHeader title="Job Monitor" subtitle="Track, inspect, and manage analysis jobs">
        <label style={{ display: "flex", alignItems: "center", gap: "var(--spacing-xs)", fontSize: "0.85rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={autoRefresh}
            onChange={(e) => setAutoRefresh(e.target.checked)}
          />
          Auto-refresh
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
        <MetricCard icon={Play} label="Running" value={stats.running} color="var(--warning)" />
        <MetricCard icon={CheckCircle2} label="Completed" value={stats.completed} color="var(--success)" />
        <MetricCard icon={XCircle} label="Failed" value={stats.failed} color="var(--danger)" />
        <MetricCard icon={Ban} label="Cancelled" value={stats.cancelled} color="#aeaeb2" />
      </div>

      {/* Filter toolbar */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
          <Filter size={16} style={{ color: "var(--text-tertiary)" }} />
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            Project:
            <select
              value={filterProjectId}
              onChange={(e) => setFilterProjectId(e.target.value)}
              style={{ ...selectStyle, minHeight: "32px", fontSize: "0.8rem", minWidth: "150px" }}
            >
              <option value="">All</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </label>
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            Dataset:
            <select
              value={filterAssetSet}
              onChange={(e) => setFilterAssetSet(e.target.value)}
              disabled={!filterProjectId}
              style={{ ...selectStyle, minHeight: "32px", fontSize: "0.8rem", minWidth: "120px" }}
            >
              <option value="">All</option>
              {assetSets.map((set) => (
                <option key={set} value={set}>{set}</option>
              ))}
            </select>
          </label>
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            Status:
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value)}
              style={{ ...selectStyle, minHeight: "32px", fontSize: "0.8rem" }}
            >
              <option value="">All</option>
              <option value="queued">Queued</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </label>
          <label style={{ ...labelStyle, flexDirection: "row", alignItems: "center", gap: "var(--spacing-xs)" }}>
            Module:
            <select
              value={filterModule}
              onChange={(e) => setFilterModule(e.target.value)}
              style={{ ...selectStyle, minHeight: "32px", fontSize: "0.8rem" }}
            >
              <option value="">All</option>
              {modules.map((m) => (
                <option key={m.key} value={m.key}>{m.label}</option>
              ))}
            </select>
          </label>
          <div style={{ flex: 1, minWidth: "200px" }}>
            <SearchBar
              placeholder="Search job ID…"
              value={searchTerm}
              onChange={setSearchTerm}
              onClear={() => setSearchTerm("")}
            />
          </div>
          <button
            onClick={() => {
              setFilterStatus("");
              setFilterModule("");
              setFilterProjectId("");
              setFilterAssetSet("");
              setSearchTerm("");
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
            Clear
          </button>
        </div>
      </Card>

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
                  {allVisibleSelected ? "Unselect visible" : "Select visible"}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedJobIds(new Set())}
                  disabled={deleting || selectedJobIds.size === 0}
                  style={smallButtonStyle}
                >
                  Clear
                </button>
                <label style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--text-secondary)", fontSize: "0.78rem" }}>
                  <input
                    type="checkbox"
                    checked={deleteResults}
                    onChange={(event) => setDeleteResults(event.target.checked)}
                    disabled={deleting}
                  />
                  Delete attached results
                </label>
                <span style={{ color: "var(--text-tertiary)", fontSize: "0.78rem" }}>
                  {selectedJobIds.size} selected · {terminalSelectedJobs.length} deletable
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
                  {deleting ? "Deleting..." : "Delete selected"}
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
              title="No jobs found"
              description={filterStatus || filterModule || filterProjectId || filterAssetSet || searchTerm ? "Try adjusting your filters." : "Submit a job from ScriptHub to get started."}
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
                title="Select a job"
                description="Click on a job from the list to view its configuration and results."
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
                  Live updates
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
                  loading={jobDetailState.loading}
                  onClose={() => {
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

const selectStyle: React.CSSProperties = {
  padding: "5px 8px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
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
