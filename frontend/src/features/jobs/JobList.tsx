import { JobRow } from "./JobRow";
import { Skeleton } from "../../shared/components/Skeleton";
import type { JobSummary } from "../../shared/types/domain";

type Props = {
  jobs: JobSummary[];
  loading: boolean;
  emptyLabel?: string;
  onSelectResult?: (jobId: string) => void;
  onOpenDetails?: (job: JobSummary) => void;
  selectedJobIds?: Set<string>;
  onToggleSelected?: (job: JobSummary) => void;
  onDelete?: (job: JobSummary) => void;
};

export function JobList({
  jobs,
  loading,
  emptyLabel = "No jobs found.",
  onOpenDetails,
  selectedJobIds,
  onToggleSelected,
  onDelete,
}: Props) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
      {loading &&
        [1, 2, 3].map((i) => <Skeleton key={i} height="72px" />)}
      {!loading && jobs.length === 0 && (
        <p
          style={{
            color: "var(--text-tertiary)",
            textAlign: "center",
            padding: "var(--spacing-xl)",
          }}
        >
          {emptyLabel}
        </p>
      )}
      {jobs.map((job) => (
        <JobRow
          key={job.job_id || job.id}
          job={job}
          onOpenDetails={onOpenDetails}
          selected={selectedJobIds?.has(job.job_id || job.id)}
          onToggleSelected={onToggleSelected}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
