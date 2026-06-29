import { useState, useCallback, useEffect } from "react";
import { useApi } from "../shared/hooks/useApi";
import { useJobEvents } from "../shared/hooks/useJobEvents";
import { usePolling } from "../shared/hooks/usePolling";
import { listJobs, listJobModules, getJobResults } from "../shared/api/jobs";
import { listProjects } from "../shared/api/projects";
import type { JobResultsResponse } from "../shared/api/jobs";
import { PageHeader } from "../shared/components/PageHeader";
import { JobSubmitForm } from "../features/jobs/JobSubmitForm";
import { JobList } from "../features/jobs/JobList";
import { JobResultPanel } from "../features/jobs/JobResultPanel";

export function ScriptHub() {
  const [resultJobId, setResultJobId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [resultState, setResultState] = useState<{
    result: JobResultsResponse | null;
    loading: boolean;
  }>({ result: null, loading: false });
  const liveJob = useJobEvents(resultJobId);

  const modulesState = useApi(() => listJobModules(), []);
  const modules =
    modulesState.status === "ready" ? modulesState.data.modules : [];

  const projectsState = useApi(() => listProjects(), []);
  const projects =
    projectsState.status === "ready" ? projectsState.data.projects : [];

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

  const handleJobSubmitted = useCallback((jobId: string) => {
    setResultJobId(jobId);
  }, []);

  const handleResultLoaded = useCallback((data: JobResultsResponse) => {
    setResultState({ result: data, loading: false });
  }, []);

  useEffect(() => {
    if (!resultJobId || !liveJob.event) return;
    const event = liveJob.event;
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

  return (
    <>
      <PageHeader
        title="Script Hub"
        subtitle="Submit analysis jobs and monitor results"
      >
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
      </PageHeader>

      <JobSubmitForm
        modules={modules}
        projectId={selectedProjectId}
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
          />
        </div>
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
          <JobResultPanel
            result={resultState.result}
            loading={resultState.loading}
          />
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
        />
      </div>
    </>
  );
}
