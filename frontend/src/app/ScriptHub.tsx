import { useState, useCallback, useEffect } from "react";
import { useApi } from "../shared/hooks/useApi";
import { useJobEvents } from "../shared/hooks/useJobEvents";
import { usePolling } from "../shared/hooks/usePolling";
import { listJobs, listJobModules, getJob, getJobResults } from "../shared/api/jobs";
import { listProjects } from "../shared/api/projects";
import { listGroupSpecs } from "../shared/api/groupSpecs";
import type { JobResultsResponse } from "../shared/api/jobs";
import type { JobSummary } from "../shared/types/domain";
import { Download, Eye, FlaskConical, RotateCcw } from "lucide-react";
import { PageHeader } from "../shared/components/PageHeader";
import { EmptyState } from "../shared/components/EmptyState";
import { JobSubmitForm } from "../features/jobs/JobSubmitForm";
import { JobList } from "../features/jobs/JobList";
import { JobDetailPanel } from "../features/jobs/JobDetailPanel";

export function ScriptHub() {
  const [resultJobId, setResultJobId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [resultState, setResultState] = useState<{
    result: JobResultsResponse | null;
    loading: boolean;
  }>({ result: null, loading: false });
  const [detailState, setDetailState] = useState<{
    job: JobSummary | null;
    loading: boolean;
  }>({ job: null, loading: false });
  const liveJob = useJobEvents(resultJobId);

  const modulesState = useApi(() => listJobModules(), []);
  const modules =
    modulesState.status === "ready" ? modulesState.data.modules : [];
  const modulesError = modulesState.status === "error" ? modulesState.error : null;

  const projectsState = useApi(() => listProjects(), []);
  const projects =
    projectsState.status === "ready" ? projectsState.data.projects : [];
  const projectsError = projectsState.status === "error" ? projectsState.error : null;

  // Load group specs for the selected project
  const groupSpecsState = useApi(
    () => (selectedProjectId ? listGroupSpecs(selectedProjectId) : Promise.resolve({ group_specs: [] })),
    [selectedProjectId]
  );
  const groupSpecs =
    groupSpecsState.status === "ready" ? groupSpecsState.data.group_specs : [];
  const loadingSpecs = groupSpecsState.status === "loading";

  // Auto-select first project if none selected
  useEffect(() => {
    if (projects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  // Poll jobs filtered by selected project
  const allJobsState = usePolling(
    () => listJobs({ projectId: selectedProjectId || undefined, limit: 20 }),
    3000
  );
  const allJobs = allJobsState.data?.jobs || [];

  const activeJobs = allJobs.filter(
    (j) => j.status === "queued" || j.status === "running"
  );
  const recentJobs = allJobs.filter(
    (j) => j.status === "completed" || j.status === "failed" || j.status === "cancelled"
  );

  const handleSelectResult = useCallback(async (jobId: string) => {
    setResultJobId(jobId);
    setResultState({ result: null, loading: true });
    try {
      const data = await getJobResults(jobId);
      setResultState({ result: data, loading: false });
    } catch {
      setResultState({ result: null, loading: false });
    }
  }, []);

  const handleOpenDetails = useCallback(async (job: JobSummary) => {
    const jobId = job.job_id || job.id;
    setResultJobId(jobId);
    setDetailState({ job, loading: true });
    try {
      const data = await getJob(jobId);
      setDetailState({ job: data.job, loading: false });
    } catch {
      setDetailState({ job, loading: false });
    }
  }, []);

  const handleJobSubmitted = useCallback((jobId: string) => {
    setResultJobId(jobId);
  }, []);

  const handleResultLoaded = useCallback((data: JobResultsResponse) => {
    setResultState({ result: data, loading: false });
  }, []);

  useEffect(() => {
    if (!resultJobId || !liveJob.event) return;
    const event = liveJob.event;
    setDetailState((current) => {
      if (!current.job) return current;
      const currentId = current.job.job_id || current.job.id;
      const eventId = event.job.job_id || event.job.id;
      if (currentId !== eventId) return current;
      return { job: event.job, loading: false };
    });
    if (event.status === "completed") {
      setResultState((current) => ({ ...current, loading: true }));
      getJobResults(resultJobId)
        .then((data) => setResultState({ result: data, loading: false }))
        .catch(() => setResultState((current) => ({ ...current, loading: false })));
      return;
    }
    setResultState((current) => {
      if (!current.result) {
        return { result: null, loading: true };
      }
      return {
        result: {
          ...current.result,
          job: event.job,
          status: event.status,
        },
        loading: false,
      };
    });
  }, [liveJob.event, resultJobId]);

  const noProjects = projectsState.status === "ready" && projects.length === 0;

  return (
    <>
      <PageHeader
        title="Script Hub"
        subtitle="Submit analysis jobs and monitor results"
      >
        {!noProjects && (
        <select
          value={selectedProjectId}
          onChange={(e) => setSelectedProjectId(e.target.value)}
          style={{
            minHeight: "38px",
            padding: "7px 12px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            fontSize: "0.85rem",
          }}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        )}
      </PageHeader>

      {/* Error banners */}
      {projectsError && <div className="error-banner">⚠ {projectsError}</div>}
      {modulesError && <div className="error-banner">⚠ {modulesError}</div>}

      {/* Empty project state */}
      {noProjects ? (
        <EmptyState
          icon={FlaskConical}
          title="No projects available"
          description="Create a project from the Dashboard before submitting analysis jobs."
          action={{ label: "Go to Dashboard", to: "/" }}
        />
      ) : (
      <>
      <JobSubmitForm
        modules={modules}
        projectId={selectedProjectId}
        groupSpecs={groupSpecs}
        loadingSpecs={loadingSpecs}
        onJobSubmitted={handleJobSubmitted}
        onResultLoaded={handleResultLoaded}
      />

      {activeJobs.length > 0 && (
        <div>
          <h3 style={{ marginBottom: "var(--spacing-md)" }}>Active Jobs</h3>
          <JobList
            jobs={activeJobs}
            loading={allJobsState.loading && activeJobs.length === 0}
            emptyLabel="No active jobs."
            onOpenDetails={handleOpenDetails}
          />
        </div>
      )}

      {detailState.job && (
        <JobDetailPanel
          job={detailState.job}
          loading={detailState.loading}
          onClose={() => setDetailState({ job: null, loading: false })}
        />
      )}

      {resultState.result && (
        <div>
          <h3 style={{ marginBottom: "var(--spacing-md)" }}>
            Job Result
            {liveJob.connected && (
              <span
                style={{
                  marginLeft: "var(--spacing-sm)",
                  color: "var(--success)",
                  fontSize: "0.75rem",
                  fontWeight: 500,
                }}
              >
                live
              </span>
            )}
          </h3>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            <button type="button" onClick={() => openFirstOutput(resultState.result!)} style={actionButtonStyle(Boolean(resultState.result.outputs.length))} disabled={!resultState.result.outputs.length}>
              <Eye size={15} /> Open Viewer
            </button>
            <button type="button" onClick={() => openZipOutputs(resultState.result!)} style={actionButtonStyle(Boolean(resultState.result.outputs.length), "var(--success)")} disabled={!resultState.result.outputs.length}>
              <Download size={15} /> Download ZIP
            </button>
            <button type="button" onClick={() => setResultState({ result: null, loading: false })} style={secondaryActionButtonStyle}>
              <RotateCcw size={15} /> Clear
            </button>
          </div>
        </div>
      )}
      {liveJob.error && (
        <p style={{ color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
          {liveJob.error}
        </p>
      )}

      <div>
        <h3 style={{ marginBottom: "var(--spacing-md)" }}>Recent Jobs</h3>
        <JobList
          jobs={recentJobs}
          loading={allJobsState.loading && recentJobs.length === 0}
          emptyLabel="No completed jobs."
          onSelectResult={handleSelectResult}
          onOpenDetails={handleOpenDetails}
        />
      </div>
    </>
  )}
    </>
  );
}

function openFirstOutput(result: JobResultsResponse) {
  const output = result.outputs.find((item) => item.url) || result.outputs[0];
  if (output?.url) window.open(output.url, "_blank");
}

function openZipOutputs(result: JobResultsResponse) {
  const zipOutputs = result.outputs.filter((item) => String(item.kind || item.url || "").toLowerCase().includes("zip"));
  for (const output of (zipOutputs.length ? zipOutputs : result.outputs)) {
    if (output.url) window.open(output.url, "_blank");
  }
}

function actionButtonStyle(enabled: boolean, color = "var(--accent)"): React.CSSProperties {
  return {
    display: "inline-flex",
    alignItems: "center",
    gap: "8px",
    minHeight: "38px",
    padding: "8px 14px",
    borderRadius: "var(--radius-control)",
    border: "none",
    background: enabled ? color : "var(--bg-inset)",
    color: enabled ? "#fff" : "var(--text-tertiary)",
    fontSize: "0.82rem",
    fontWeight: 650,
    cursor: enabled ? "pointer" : "not-allowed",
  };
}

const secondaryActionButtonStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
  minHeight: "38px",
  padding: "8px 14px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.82rem",
  fontWeight: 650,
  cursor: "pointer",
};
