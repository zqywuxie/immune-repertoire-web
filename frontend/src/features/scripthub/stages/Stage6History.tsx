import { useState, useCallback } from "react";
import {
  History,
  Play,
  RotateCcw,
  AlertCircle,
  FolderOpen,
} from "lucide-react";
import { usePolling } from "../../../shared/hooks/usePolling";
import { listJobs } from "../../../shared/api/jobs";
import { JobList } from "../../jobs/JobList";
import { JobRow } from "../../jobs/JobRow";
import { JobResultPanel } from "../../jobs/JobResultPanel";
import { getJobResults, type JobResultsResponse } from "../../../shared/api/jobs";
import { Card } from "../../../shared/components/Card";
import { Skeleton } from "../../../shared/components/Skeleton";
import { EmptyState } from "../../../shared/components/EmptyState";

interface Stage6HistoryProps {
  projectId: string;
  onSelectResult: (jobId: string) => void;
}

export function Stage6History({ projectId, onSelectResult }: Stage6HistoryProps) {
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [result, setResult] = useState<JobResultsResponse | null>(null);

  // Poll jobs for the selected project
  const jobsState = usePolling(
    () =>
      projectId
        ? listJobs({ projectId, limit: 50 })
        : Promise.resolve({ success: true, jobs: [] }),
    5000,
  );

  const allJobs = jobsState.data?.jobs || [];
  const jobsLoading = jobsState.loading;
  const jobsError = jobsState.error;

  const activeJobs = allJobs.filter(
    (j) => j.status === "queued" || j.status === "running",
  );
  const completedJobs = allJobs.filter(
    (j) => j.status === "completed",
  );
  const failedJobs = allJobs.filter(
    (j) => j.status === "failed" || j.status === "cancelled",
  );

  const handleViewResults = useCallback(async (jobId: string) => {
    setSelectedJobId(jobId);
    setResultLoading(true);
    try {
      const data = await getJobResults(jobId);
      setResult(data);
    } catch {
      // best effort
    } finally {
      setResultLoading(false);
    }
  }, []);

  const handleRunNew = () => {
    onSelectResult("");
  };

  if (!projectId) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
        <div>
          <h2 style={{ margin: 0 }}>Stage 6: History</h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            View past analysis runs for this project.
          </p>
        </div>
        <EmptyState
          icon={FolderOpen}
          title="No project selected"
          description="Select a project from the Data Intake stage first."
        />
      </div>
    );
  }

  if (jobsError) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
        <div>
          <h2 style={{ margin: 0 }}>Stage 6: History</h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            View past analysis runs for this project.
          </p>
        </div>
        <div
          style={{
            padding: "var(--spacing-xl)",
            borderRadius: "var(--radius-panel)",
            background: "var(--danger)",
            color: "#fff",
            textAlign: "center",
          }}
        >
          <AlertCircle size={32} style={{ marginBottom: "var(--spacing-sm)" }} />
          <p style={{ margin: 0 }}>Failed to load job history: {jobsError}</p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      {/* Header */}
      <div>
        <h2 style={{ margin: 0 }}>Stage 6: History</h2>
        <p
          style={{
            margin: "4px 0 0",
            color: "var(--text-secondary)",
            fontSize: "0.875rem",
          }}
        >
          View past analysis runs for project{" "}
          <code style={{ background: "var(--bg-inset)", padding: "1px 6px", borderRadius: "4px" }}>
            {projectId.slice(0, 8)}
          </code>{" "}
          — {allJobs.length} job{allJobs.length !== 1 ? "s" : ""} found.
        </p>
      </div>

      {/* Action Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
        }}
      >
        <button
          onClick={handleRunNew}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "10px 22px",
            borderRadius: "var(--radius-control)",
            background: "var(--accent)",
            color: "#fff",
            fontWeight: 500,
            fontSize: "0.85rem",
            border: "none",
            cursor: "pointer",
          }}
        >
          <Play size={16} />
          Run New Analysis
        </button>
      </div>

      {/* Active Jobs */}
      {activeJobs.length > 0 && (
        <div>
          <h4
            style={{
              margin: "0 0 var(--spacing-md) 0",
              fontSize: "0.82rem",
              fontWeight: 600,
              color: "var(--warning)",
              textTransform: "uppercase",
              display: "flex",
              alignItems: "center",
              gap: "var(--spacing-sm)",
            }}
          >
            <div
              style={{
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                background: "var(--warning)",
                animation: "pulse 1.5s ease-in-out infinite",
              }}
            />
            Active ({activeJobs.length})
          </h4>
          <JobList
            jobs={activeJobs}
            loading={jobsLoading && activeJobs.length === 0}
            emptyLabel="No active jobs."
            onSelectResult={handleViewResults}
          />
        </div>
      )}

      {/* Completed Jobs */}
      {completedJobs.length > 0 && (
        <div>
          <h4
            style={{
              margin: "0 0 var(--spacing-md) 0",
              fontSize: "0.82rem",
              fontWeight: 600,
              color: "var(--success)",
              textTransform: "uppercase",
            }}
          >
            Completed ({completedJobs.length})
          </h4>
          <JobList
            jobs={completedJobs}
            loading={jobsLoading && completedJobs.length === 0}
            emptyLabel="No completed jobs."
            onSelectResult={handleViewResults}
          />
        </div>
      )}

      {/* Failed Jobs */}
      {failedJobs.length > 0 && (
        <div>
          <h4
            style={{
              margin: "0 0 var(--spacing-md) 0",
              fontSize: "0.82rem",
              fontWeight: 600,
              color: "var(--danger)",
              textTransform: "uppercase",
            }}
          >
            Failed / Cancelled ({failedJobs.length})
          </h4>
          <JobList
            jobs={failedJobs}
            loading={jobsLoading && failedJobs.length === 0}
            emptyLabel="No failed jobs."
            onSelectResult={handleViewResults}
          />
        </div>
      )}

      {/* Empty state */}
      {allJobs.length === 0 && !jobsLoading && (
        <EmptyState
          icon={History}
          title="No analysis history"
          description="No jobs have been run for this project yet. Start a new analysis to see results here."
          action={{ label: "Run New Analysis", to: "#" }}
        />
      )}

      {/* Loading */}
      {jobsLoading && allJobs.length === 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          <Skeleton height="72px" />
          <Skeleton height="72px" />
          <Skeleton height="72px" />
        </div>
      )}

      {/* Results Viewer */}
      {selectedJobId && (
        <div>
          <h4
            style={{
              margin: "0 0 var(--spacing-md) 0",
              fontSize: "0.85rem",
              fontWeight: 600,
              color: "var(--text-secondary)",
              textTransform: "uppercase",
            }}
          >
            Job Results
          </h4>
          <JobResultPanel result={result} loading={resultLoading} />
        </div>
      )}
    </div>
  );
}
