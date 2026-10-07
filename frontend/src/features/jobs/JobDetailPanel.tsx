import { useState, useEffect } from "react";
import { Activity, FileJson2, X, Package } from "lucide-react";
import { type JobResultsResponse } from "../../shared/api/jobs";
import { useJobResult } from "../../shared/hooks/useJobResult";
import { JobResultPanel } from "./JobResultPanel";
import { BatchExecutionProgress, batchItemsForJob } from "./BatchExecutionProgress";
import { useBatchJobSnapshots, type BatchJobSnapshots } from "./useBatchJobSnapshots";
import { JobProgressPanel } from "./JobProgressPanel";
import { JobConfigurationPanel } from "./JobConfigurationPanel";
import { taskName } from "./jobConfiguration";

import type { JobSummary } from "../../shared/types/domain";

type Props = {
  job: JobSummary;
  loading?: boolean;
  onClose: () => void;
  result?: JobResultsResponse | null;
  resultLoading?: boolean;
  resultError?: string;
  resultFocus?: string;
  onRetry?: () => void;
};

export function JobDetailPanel(props: Props) {
  return props.result === undefined ? <StandaloneDetail {...props} /> : <DetailContent key={props.job.job_id || props.job.id} {...props} />;
}
function StandaloneDetail(props: Props) {
  const state = useJobResult(props.job.job_id || props.job.id);
  return <DetailContent key={props.job.job_id || props.job.id} {...props} result={state.result} resultLoading={!state.result && !state.error} resultError={state.error} onRetry={state.retry} />;
}
function DetailContent(props: Props) {
  return props.job.module === "analysis-batch" ? <BatchDetailContent {...props}/> : <TaskDetailContent {...props}/>;
}
function BatchDetailContent(props: Props) {
  const progress = useBatchJobSnapshots(props.job.id, props.job.status, batchItemsForJob(props.job));
  return <TaskDetailContent {...props} batchProgress={progress}/>;
}
function TaskDetailContent({ job, loading = false, onClose, result, resultLoading = false, resultError = "", resultFocus, onRetry, batchProgress }: Props & {batchProgress?: BatchJobSnapshots}) {
  const [activeTab, setActiveTab] = useState<"config" | "progress" | "results">(resultFocus || job.status === "completed" ? "results" : "progress");
  const jobId = job.job_id || job.id;
  useEffect(() => { if (resultFocus) setActiveTab("results"); }, [resultFocus]);
  useEffect(() => { if (job.status === "completed") setActiveTab("results"); }, [job.status]);

  return (
    <section
      style={{
        border: "1px solid var(--separator)",
        borderRadius: "var(--radius-panel)",
        background: "var(--bg-elevated)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--spacing-md)",
          padding: "var(--spacing-md) var(--spacing-lg)",
          borderBottom: "1px solid var(--separator)",
          background: "var(--bg-root)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", minWidth: 0 }}>
          <FileJson2 size={18} color="var(--accent)" />
          <div style={{ minWidth: 0 }}>
            <h3 style={{ margin: 0, fontSize: "0.95rem", overflowWrap: "anywhere" }}>{taskName(job)}</h3>
            <p style={{ margin: "2px 0 0", color: "var(--text-tertiary)", fontSize: "0.76rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {jobId}
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          title="关闭任务详情"
          aria-label="关闭任务详情"
          style={{
            width: "32px",
            height: "32px",
            border: "1px solid var(--separator)",
            borderRadius: "var(--radius-control)",
            background: "var(--bg-elevated)",
            color: "var(--text-secondary)",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
          }}
        >
          <X size={16} />
        </button>
      </div>

      <div style={{ padding: "var(--spacing-lg)", display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "var(--spacing-lg)", minWidth: 0 }}>
        {loading && (
          <div style={{ color: "var(--text-tertiary)", fontSize: "0.82rem" }}>
            正在读取最新任务详情…
          </div>
        )}

        <div style={tabListStyle} role="tablist" aria-label="任务详情分区">
          <TabButton active={activeTab === "config"} onClick={() => setActiveTab("config")}>
            <FileJson2 size={14} />
            配置
          </TabButton>
          <TabButton active={activeTab === "progress"} onClick={() => setActiveTab("progress")}>
            <Activity size={14} />
            进度
          </TabButton>
          <TabButton active={activeTab === "results"} onClick={() => setActiveTab("results")}>
            <Package size={14} />
            结果
          </TabButton>
        </div>

        {activeTab === "config" && <JobConfigurationPanel job={job}/>}

        {activeTab === "progress" && <>
          <JobProgressPanel job={job}/>
          {batchProgress && <BatchExecutionProgress items={batchItemsForJob(job)} jobs={batchProgress.jobs}
            readErrors={batchProgress.readErrors} onRetry={item => batchProgress.retry(item.job_id!)}/>}
        </>}

        {activeTab === "results" && <div>
          {resultError && <div role="alert"><p>{resultError}</p><button className="btn btn-secondary" onClick={onRetry}>重新读取结果</button></div>}
          <JobResultPanel result={result || null} loading={resultLoading} batchProgress={batchProgress} embedded />
        </div>}

      </div>
    </section>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      style={{
        minHeight: "34px",
        padding: "6px 12px",
        borderRadius: "var(--radius-control)",
        border: `1px solid ${active ? "var(--accent)" : "transparent"}`,
        background: active ? "var(--bg-elevated)" : "transparent",
        color: active ? "var(--accent)" : "var(--text-secondary)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "6px",
        fontSize: "0.8rem",
        fontWeight: 650,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

const tabListStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "1fr 1fr 1fr",
  gap: "4px",
  padding: "4px",
  borderRadius: "var(--radius-control)",
  background: "var(--bg-root)",
  border: "1px solid var(--separator)",
};
