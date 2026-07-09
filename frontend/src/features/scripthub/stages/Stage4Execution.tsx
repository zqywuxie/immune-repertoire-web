import { useState, useEffect, useRef, useCallback } from "react";
import {
  Play,
  Square,
  Terminal,
  CheckCircle2,
  AlertCircle,
  Clock,
  Zap,
  FileText,
  Layers,
} from "lucide-react";
import { submitJob, getJob, getJobResults, type JobResultsResponse } from "../../../shared/api/jobs";
import {
  getLegacyScriptHubTask,
  isLegacyScriptHubModule,
  legacyScriptHubTaskToResults,
  submitLegacyScriptHubJob,
} from "../../../shared/api/scriptHub";
import { StatusBadge } from "../../../shared/components/StatusBadge";
import { ProgressBar } from "../../../shared/components/ProgressBar";
import { Card } from "../../../shared/components/Card";

interface Stage4ExecutionProps {
  projectId: string;
  modules: string[];
  baseConfig: Record<string, unknown>;
  moduleConfigs: Record<string, Record<string, unknown>>;
  jobIds: string[];
  onJobsCreated: (jobIds: string[]) => void;
  onComplete: (resultsByJobId: Record<string, JobResultsResponse>) => void;
}

export function Stage4Execution({
  projectId,
  modules,
  baseConfig,
  moduleConfigs,
  jobIds,
  onJobsCreated,
  onComplete,
}: Stage4ExecutionProps) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskName, setTaskName] = useState(`script_hub_batch_${Date.now()}`);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [jobProgress, setJobProgress] = useState<Record<string, number>>({});
  const [jobStatus, setJobStatus] = useState<Record<string, string>>({});
  const [jobStage, setJobStage] = useState<Record<string, string>>({});
  const [jobModules, setJobModules] = useState<Record<string, string>>({});
  const logEndRef = useRef<HTMLDivElement>(null);
  const selectedModules = modules.filter(Boolean);

  // Scroll log to bottom
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logLines]);

  const addLogLine = useCallback((line: string) => {
    const timestamp = new Date().toLocaleTimeString();
    setLogLines((prev) => [...prev, `[${timestamp}] ${line}`]);
  }, []);

  const handleRunAnalysis = async () => {
    if (!selectedModules.length) {
      setError("No modules selected.");
      return;
    }
    setSubmitting(true);
    setError(null);
    setLogLines([]);
    setJobProgress({});
    setJobStatus({});
    setJobStage({});
    setJobModules({});
    addLogLine(`Starting Script Hub batch: ${selectedModules.join(", ")}`);
    addLogLine(`Project: ${projectId}`);
    addLogLine(`Task name: ${taskName}`);

    try {
      const createdJobIds: string[] = [];
      const completedResults: Record<string, JobResultsResponse> = {};

      for (const [index, module] of selectedModules.entries()) {
        const payload: Record<string, unknown> = {
          ...baseConfig,
          ...(moduleConfigs[module] || {}),
          _task_name: selectedModules.length === 1 ? taskName : `${taskName}_${index + 1}_${module}`,
        };
        validatePayload(module, payload);

        addLogLine(`[${index + 1}/${selectedModules.length}] Submitting ${module}`);
        addLogLine(`[${module}] Payload preview: ${JSON.stringify(payload, null, 2).slice(0, 220)}...`);

        const submitModule = module === "charts" ? "charts.combined" : module;
        const legacyModule = isLegacyScriptHubModule(module);
        const result = legacyModule
          ? await submitLegacyScriptHubJob({ module, payload, projectId, forceRerun: false })
          : await submitJob({
              module: submitModule,
              payload,
              projectId,
              forceRerun: false,
            });

        const submittedJobId = result.job_id;
        createdJobIds.push(submittedJobId);
        setJobModules((prev) => ({ ...prev, [submittedJobId]: module }));
        setJobStatus((prev) => ({ ...prev, [submittedJobId]: result.status || "queued" }));
        addLogLine(`[${module}] Job submitted successfully. Job ID: ${submittedJobId}`);
        onJobsCreated([...createdJobIds]);

        if (result.reused_result) {
          addLogLine(`[${module}] Using cached result: ${result.result_id || submittedJobId}`);
        }

        const moduleResults = legacyModule
          ? await pollLegacyTask(result.task_id || submittedJobId, module, submittedJobId)
          : await pollModernJob(submittedJobId, module);

        completedResults[submittedJobId] = moduleResults;
        onComplete({ ...completedResults });
      }
      addLogLine(`Batch completed. ${createdJobIds.length} job(s) submitted.`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Submission failed";
      addLogLine(`[ERROR] ${msg}`);
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const pollLegacyTask = async (taskId: string, module: string, jobId: string) => {
    addLogLine(`[${module}] Polling Script Hub task: ${taskId}`);
    for (;;) {
      const task = await getLegacyScriptHubTask(taskId);
      const progress = Number(task.progress || 0);
      setJobProgress((prev) => ({ ...prev, [jobId]: progress }));
      setJobStatus((prev) => ({ ...prev, [jobId]: task.status }));
      setJobStage((prev) => ({ ...prev, [jobId]: task.stage || task.detail || "" }));
      addLogLine(`[${module}] ${task.status} ${Math.round(progress)}% ${task.stage || task.detail || ""}`.trim());

      if (task.status === "completed" || task.status === "failed" || task.status === "cancelled") {
        return legacyScriptHubTaskToResults(task);
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };

  const pollModernJob = async (jobId: string, module: string) => {
    addLogLine(`[${module}] Polling job: ${jobId}`);
    for (;;) {
      const jobResponse = await getJob(jobId);
      const status = jobResponse.job.status;
      setJobProgress((prev) => ({ ...prev, [jobId]: Number(jobResponse.job.progress || 0) }));
      setJobStatus((prev) => ({ ...prev, [jobId]: status }));
      setJobStage((prev) => ({ ...prev, [jobId]: jobResponse.job.stage || jobResponse.job.detail || "" }));
      addLogLine(`[${module}] ${status} ${Math.round(Number(jobResponse.job.progress || 0))}% ${jobResponse.job.stage || jobResponse.job.detail || ""}`.trim());

      if (status === "completed" || status === "failed" || status === "cancelled") {
        addLogLine(`[${module}] Terminal status: ${status}. Loading results.`);
        return getJobResults(jobId);
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };

  const handleCancel = () => {
    addLogLine(`Job cancellation requested. Cancellation is available from the Tasks page for submitted jobs.`);
  };

  const hasJobs = jobIds.length > 0;
  const isRunning = submitting || Object.values(jobStatus).some((status) => status === "queued" || status === "running");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      {/* Header */}
      <div>
        <h2 style={{ margin: 0 }}>Stage 4: Execution</h2>
        <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          Configure the run and start the analysis pipeline.
        </p>
      </div>

      {/* Error banner */}
      {error && (
        <div
          style={{
            padding: "var(--spacing-md) var(--spacing-lg)",
            borderRadius: "var(--radius-control)",
            background: "var(--danger)",
            color: "#fff",
            fontSize: "0.85rem",
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
          }}
        >
          <AlertCircle size={16} />
          {error}
          <button
            onClick={() => setError(null)}
            style={{
              marginLeft: "auto",
              background: "rgba(255,255,255,0.2)",
              border: "none",
              color: "#fff",
              padding: "4px 10px",
              borderRadius: "var(--radius-pill)",
              cursor: "pointer",
              fontSize: "0.75rem",
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Run digest summary chips */}
      <Card>
        <h4 style={{ margin: "0 0 var(--spacing-md) 0", fontSize: "0.85rem", fontWeight: 600 }}>
          Run Summary
        </h4>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
          <SummaryChip icon={Layers} label="Modules" value={selectedModules.length ? selectedModules.join(", ") : "none"} color="var(--accent)" />
          <SummaryChip icon={FileText} label="Project" value={projectId || "none"} color="var(--success)" />
          <SummaryChip icon={Zap} label="Jobs" value={`${jobIds.length}/${selectedModules.length}`} color="var(--warning)" />
          <SummaryChip icon={Terminal} label="Task" value={taskName} color="#af52de" />
        </div>
      </Card>

      {/* Task name input */}
      <div
        style={{
          background: "var(--bg-elevated)",
          borderRadius: "var(--radius-panel)",
          border: "1px solid var(--separator)",
          padding: "var(--spacing-lg)",
        }}
      >
        <label style={labelStyle}>
          Task Name
          <input
            type="text"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            placeholder="Enter a name for this analysis run..."
            disabled={submitting || isRunning}
            style={inputStyle}
          />
        </label>
      </div>

      {/* Run button (pre-execution) */}
      {!hasJobs && (
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            paddingTop: "var(--spacing-md)",
          }}
        >
          <button
            onClick={handleRunAnalysis}
            disabled={submitting || !selectedModules.length}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "var(--spacing-sm)",
              padding: "14px 40px",
              borderRadius: "var(--radius-control)",
              background: submitting || !selectedModules.length ? "var(--bg-inset)" : "var(--accent)",
              color: submitting || !selectedModules.length ? "var(--text-tertiary)" : "#fff",
              fontWeight: 600,
              fontSize: "1rem",
              border: "none",
              cursor: submitting || !selectedModules.length ? "not-allowed" : "pointer",
              opacity: submitting ? 0.7 : 1,
            }}
          >
            <Play size={18} />
            {submitting ? "Submitting..." : selectedModules.length > 1 ? "Run Selected Modules" : "Run Analysis"}
          </button>
        </div>
      )}

      {/* Live progress (post-execution) */}
      {hasJobs && (
        <>
          {/* Status bar */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
            {jobIds.map((jobId) => {
              const status = jobStatus[jobId] || "queued";
              const running = status === "queued" || status === "running";
              const terminal = status === "completed" || status === "failed" || status === "cancelled";
              return (
                <Card key={jobId}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "var(--spacing-md)",
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                      <div
                        style={{
                          width: "10px",
                          height: "10px",
                          borderRadius: "50%",
                          background: running
                            ? "var(--warning)"
                            : terminal
                              ? status === "completed"
                                ? "var(--success)"
                                : "var(--danger)"
                              : "var(--text-tertiary)",
                          animation: running ? "pulse 1.5s ease-in-out infinite" : "none",
                        }}
                      />
                      <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>
                        {jobModules[jobId] || "module"} · Job {jobId.slice(0, 8)}
                      </span>
                      <StatusBadge status={status} />
                    </div>
                    {isRunning && (
                      <button onClick={handleCancel} style={cancelBtnStyle}>
                        <Square size={14} /> Cancel
                      </button>
                    )}
                  </div>
                  <div style={{ marginTop: "var(--spacing-sm)" }}>
                    <ProgressBar value={Number(jobProgress[jobId] || 0)} />
                    {jobStage[jobId] && (
                      <div style={{ marginTop: "var(--spacing-xs)", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                        {jobStage[jobId]}
                      </div>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>

          {/* Execution Log */}
          <div
            style={{
              background: "#1a1a2e",
              borderRadius: "var(--radius-panel)",
              border: "1px solid #2a2a4e",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--spacing-sm)",
                padding: "var(--spacing-sm) var(--spacing-md)",
                background: "#16213e",
                borderBottom: "1px solid #2a2a4e",
              }}
            >
              <Terminal size={14} style={{ color: "#0f0" }} />
              <span style={{ fontWeight: 600, fontSize: "0.78rem", color: "#aaa" }}>
                Execution Log
              </span>
              <span style={{ marginLeft: "auto", fontSize: "0.65rem", color: "#666" }}>
                {logLines.length} lines
              </span>
            </div>
            <pre
              style={{
                margin: 0,
                padding: "var(--spacing-md)",
                fontSize: "0.75rem",
                fontFamily: "'Cascadia Code', 'Consolas', 'Fira Code', monospace",
                color: "#c0c0c0",
                lineHeight: 1.6,
                maxHeight: "300px",
                overflow: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-all",
              }}
            >
              {logLines.length === 0 ? (
                <span style={{ color: "#555" }}>Waiting for execution to start...</span>
              ) : (
                logLines.join("\n")
              )}
              <div ref={logEndRef} />
            </pre>
          </div>
        </>
      )}
    </div>
  );
}

function validatePayload(module: string, payload: Record<string, unknown>) {
  if (Array.isArray(payload.selected_samples) && !payload.selected_samples.filter(Boolean).length) {
    throw new Error(`[${module}] Please select at least one sample, or use All samples.`);
  }
  const groupError = validateGroupFields(module, payload);
  if (groupError) throw new Error(`[${module}] ${groupError}`);
  const groupValueError = validateGroupValues(module, payload);
  if (groupValueError) throw new Error(`[${module}] ${groupValueError}`);
  const groupedSampleError = validateGroupedSamples(module, payload);
  if (groupedSampleError) throw new Error(`[${module}] ${groupedSampleError}`);
  const cacheError = validateCacheInputs(module, payload);
  if (cacheError) throw new Error(`[${module}] ${cacheError}`);
  if (module === "charts") {
    const selectedSamples = Array.isArray(payload.samples) ? payload.samples.filter(Boolean) : [];
    const selectedChains = Array.isArray(payload.selected_chains) ? payload.selected_chains.filter(Boolean) : [];
    if (!selectedSamples.length) {
      throw new Error("[charts] Please select at least one sample for combined charts.");
    }
    if (!selectedChains.length) {
      throw new Error("[charts] Please select at least one chain for combined charts.");
    }
  }
}

function validateGroupFields(module: string, payload: Record<string, unknown>) {
  const groupRequirements: Record<string, string[]> = {
    "db-alignment": ["categories"],
    profile: ["grouptype_fields", "group_fields", "grouping_begin"],
    "pep-analysis": ["group_fields", "grouptype_fields"],
    "pgen-analysis": ["distribution_category_col", "group_field"],
    topclone: ["group_field"],
    umap: ["group_field", "classification_begin"],
    umapin: ["category_col"],
    "ml-analysis": ["label_col"],
    "mait-nkt": ["group_field"],
  };
  const keys = groupRequirements[module] || [];
  if (!keys.length) return "";
  const hasGroupField = keys.some((key) => {
    const value = payload[key];
    if (Array.isArray(value)) return value.some((item) => String(item || "").trim());
    return String(value || "").trim();
  });
  return hasGroupField ? "" : "Please select group field / 请选择分组字段";
}

function validateGroupValues(module: string, payload: Record<string, unknown>) {
  const modulesRequiringGroupValues = new Set([
    "db-alignment",
    "profile",
    "pep-analysis",
    "pgen-analysis",
    "topclone",
    "umap",
    "ml-analysis",
    "mait-nkt",
  ]);
  if (!modulesRequiringGroupValues.has(module)) return "";
  const valueMap = payload.selected_group_values;
  if (!valueMap || typeof valueMap !== "object" || Array.isArray(valueMap)) {
    return "Please select group value / 请选择分组值";
  }
  const hasValue = Object.values(valueMap as Record<string, unknown>).some((item) =>
    Array.isArray(item) && item.some((value) => String(value || "").trim()),
  );
  return hasValue ? "" : "Please select group value / 请选择分组值";
}

function validateGroupedSamples(module: string, payload: Record<string, unknown>) {
  const modulesRequiringGroupSamples = new Set([
    "db-alignment",
    "profile",
    "pep-analysis",
    "pgen-analysis",
    "topclone",
    "umap",
    "ml-analysis",
    "mait-nkt",
  ]);
  if (!modulesRequiringGroupSamples.has(module)) return "";
  const valueMap = payload.selected_samples_by_group;
  if (!valueMap || typeof valueMap !== "object" || Array.isArray(valueMap)) {
    return "Please select samples for each group / 请在每个分组中选择样本";
  }
  const selectedGroups = payload.selected_group_values;
  if (!selectedGroups || typeof selectedGroups !== "object" || Array.isArray(selectedGroups)) {
    return "Please select samples for each group / 请在每个分组中选择样本";
  }
  for (const [field, values] of Object.entries(selectedGroups as Record<string, unknown>)) {
    if (!Array.isArray(values)) continue;
    const groups = (valueMap as Record<string, unknown>)[field];
    if (!groups || typeof groups !== "object" || Array.isArray(groups)) {
      return `Please select samples for ${field} / 请为 ${field} 选择样本`;
    }
    for (const groupValue of values) {
      const key = String(groupValue || "").trim();
      if (!key) continue;
      const samples = (groups as Record<string, unknown>)[key];
      if (!Array.isArray(samples) || !samples.some((sample) => String(sample || "").trim())) {
        return `Please select samples for ${field} = ${key} / 请为 ${field} = ${key} 选择样本`;
      }
    }
  }
  return "";
}

function validateCacheInputs(module: string, payload: Record<string, unknown>) {
  if (module === "volcano" && String(payload.input_mode || "") === "usage" && !String(payload.data_dir || "").trim()) {
    return "Please select a PEP VJ usage cache / 请选择 PEP VJ usage 缓存";
  }
  if (module === "umapin" && !String(payload.data_path || "").trim()) {
    return "Please select a PEP UMAPin cache / 请选择 PEP UMAPin 缓存";
  }
  if (module === "mait-nkt") {
    const source = String(payload.tra_source || "upload");
    if (source === "pep_analysis" && !String(payload.tra_path || payload.source_job_id || "").trim()) {
      return "Please select a PEP TRA cache / 请选择 PEP TRA 缓存";
    }
    if (source === "upload" && !String(payload.tra_path || "").trim()) {
      return "Please enter a TRA CSV path / 请输入 TRA CSV 路径";
    }
    if (payload.mait_nkt_inspect_ok === false) {
      return "MAIT/NKT inspect failed. Please select a valid TRA source before running / MAIT/NKT 检查失败，请先选择有效 TRA 来源";
    }
  }
  return "";
}

/* ── Summary Chip ── */
function SummaryChip({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof Play;
  label: string;
  value: string;
  color: string;
}) {
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "6px",
        padding: "6px 14px",
        borderRadius: "var(--radius-pill)",
        background: `${color}14`,
        border: `1px solid ${color}30`,
        fontSize: "0.78rem",
      }}
    >
      <Icon size={14} style={{ color }} />
      <span style={{ color: "var(--text-secondary)" }}>{label}:</span>
      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{value}</span>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  fontSize: "0.75rem",
  fontWeight: 600,
  textTransform: "uppercase",
  color: "var(--text-secondary)",
};

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 12px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
  outline: "none",
  width: "100%",
  boxSizing: "border-box",
};

const cancelBtnStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "8px 16px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--danger)",
  background: "transparent",
  color: "var(--danger)",
  fontWeight: 500,
  fontSize: "0.82rem",
  cursor: "pointer",
};
