import { batchResultSource, orderBatchDependencies } from "../batchDependencies";
import { isTerminalJobStatus } from "../../jobs/BatchStatus";
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
  submitAnalysisBatch,
} from "../../../shared/api/scriptHub";
import { analysisLabel } from "../../../shared/utils/analysisLabels";
import { StatusBadge, statusLabels } from "../../../shared/components/StatusBadge";
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
  onBatchStatuses?: (statuses: string[]) => void;
  onBatchCreated?: (jobId: string) => void;
  onRunningChange?: (running: boolean) => void;
}

export function Stage4Execution({
  projectId,
  modules,
  baseConfig,
  moduleConfigs,
  jobIds,
  onJobsCreated,
  onComplete,
  onRunningChange,
  onBatchCreated,
  onBatchStatuses,
}: Stage4ExecutionProps) {
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [taskName, setTaskName] = useState(`批量分析_${Date.now()}`);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [jobProgress, setJobProgress] = useState<Record<string, number>>({});
  const [jobStatus, setJobStatus] = useState<Record<string, string>>({});
  const [jobStage, setJobStage] = useState<Record<string, string>>({});
  const [jobModules, setJobModules] = useState<Record<string, string>>({});
  const lastLogBySource = useRef(new Map<string, string>());
  const [logsOpen, setLogsOpen] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const selectedModules = modules.filter(Boolean);
  const [useBatchResult, setUseBatchResult] = useState<Record<string, boolean>>({});
  const payloadFor = (module: string): Record<string, unknown> => ({...baseConfig, ...(moduleConfigs[module] || {})});
  const sourceFor = (module: string) => batchResultSource(module, selectedModules, payloadFor);
  const canBind = (module: string) => Boolean(sourceFor(module));
  const executionModules = orderBatchDependencies(selectedModules, module => useBatchResult[module] ? sourceFor(module) : undefined);

  // Scroll log to bottom
  useEffect(() => {
    if (logsOpen) logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logLines, logsOpen]);

  const addLogLine = useCallback((line: string, source?: string) => {
    if (source && lastLogBySource.current.get(source) === line) return;
    if (source) lastLogBySource.current.set(source, line);
    const timestamp = new Date().toLocaleTimeString();
    setLogLines((prev) => [...prev.slice(-199), `[${timestamp}] ${line}`]);
  }, []);

  const handleRunAnalysis = async () => {
    if (!selectedModules.length) {
      setError("尚未选择分析模块。");
      return;
    }
    setSubmitting(true);
    onRunningChange?.(true);
    setError(null);
    setLogLines([]);
    lastLogBySource.current.clear();
    setJobProgress({});
    setJobStatus({});
    setJobStage({});
    setJobModules({});
    addLogLine(`开始批量分析： ${selectedModules.map(analysisLabel).join("、")}`);
    addLogLine(`项目：${projectId}`);
    addLogLine(`任务名称： ${taskName}`);

    try {
      if (selectedModules.length > 1) {
        const items = executionModules.map((module, index) => {
          const payload: Record<string, unknown> = {...baseConfig, ...(moduleConfigs[module] || {}), _task_name: `${taskName}_${index + 1}`};
          const bind = canBind(module) && useBatchResult[module] === true;
          const sourceIndex = bind ? executionModules.indexOf(sourceFor(module)!) : -1;
          if (bind && module === "go-kegg-enrichment") {
            payload.input_mode = "deg";
            for (const key of ["upstream_artifact_id", "source_job_id", "upstream_input", "expression_path", "transcriptome_path", "deg_directory"]) delete payload[key];
          }
          validatePayload(module, payload, bind);
          return {module, payload, ...(bind ? {upstream_from: sourceIndex, depends_on: [sourceIndex]} : {})};
        });
        const response = await submitAnalysisBatch(projectId, String(baseConfig.asset_set || ""), taskName, items);
        onBatchCreated?.(response.job_id);
        addLogLine("完整分析计划已交给服务端，离开页面不影响后续任务执行。");
        const collected: Record<string, JobResultsResponse> = {};
        while (mounted.current) {
          try {
            const snapshot = await getJob(response.job_id);
            if (!mounted.current) return;
            const parent = snapshot.job as unknown as {status: string; payload?: {items?: Array<{job_id: string; module: string; status: string; error?: string}>}};
            const children = parent.payload?.items || [];
            onBatchStatuses?.(children.map(child => child.status));
            const ids = children.map(child => child.job_id).filter(Boolean);
            onJobsCreated(ids);
            for (const child of children) {
              if (!child.job_id) continue;
              setJobModules(previous => ({...previous, [child.job_id]: child.module}));
              setJobStatus(previous => ({...previous, [child.job_id]: child.status}));
              addLogLine(`[${analysisLabel(child.module)}] ${statusLabels[child.status] || "等待确认"}${child.error ? `：${child.error}` : ""}`, child.job_id);
              if (isTerminalJobStatus(child.status) && !collected[child.job_id]) collected[child.job_id] = await getJobResults(child.job_id);
            }
            onComplete({...collected});
            setError(null);
            if (isTerminalJobStatus(parent.status)) {
              const errors = children.filter(child => child.status !== "completed").map(child => `${analysisLabel(child.module)}：${child.error || statusLabels[child.status] || "未完成"}`);
              if (errors.length) setError(errors.join("；"));
              addLogLine("批次执行已结束，已生成的结果可继续查看。");
              break;
            }
          } catch (reason) {
            if (!mounted.current) return;
            setError("任务状态连接暂时中断，正在重新读取；服务端继续执行。");
            addLogLine("状态连接中断，等待重连。", "connection");
          }
          await new Promise(resolve => setTimeout(resolve, 2000));
        }
        return;
      }
      const createdJobIds: string[] = [];
      const completedResults: Record<string, JobResultsResponse> = {};

      for (const [index, module] of selectedModules.entries()) {
        const payload: Record<string, unknown> = {
          ...baseConfig,
          ...(moduleConfigs[module] || {}),
          _task_name: selectedModules.length === 1 ? taskName : `${taskName}_${index + 1}_${module}`,
        };
        validatePayload(module, payload);

        addLogLine(`[${index + 1}/${selectedModules.length}] 正在提交 ${analysisLabel(module)}`);


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
        addLogLine(`[${analysisLabel(module)}] 任务提交成功，任务编号： ${submittedJobId}`);
        onJobsCreated([...createdJobIds]);

        if (result.reused_result) {
          addLogLine(`[${analysisLabel(module)}] 使用缓存结果： ${result.result_id || submittedJobId}`);
        }

        const moduleResults = legacyModule
          ? await pollLegacyTask(result.task_id || submittedJobId, module, submittedJobId)
          : await pollModernJob(submittedJobId, module);

        completedResults[submittedJobId] = moduleResults;
        onComplete({ ...completedResults });
      }
      addLogLine(`本次任务已结束：${Object.values(completedResults).filter(result => result.status === "completed").length}/${createdJobIds.length} 项成功，其余状态请查看任务记录。`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "提交失败";
      addLogLine(`[错误] ${msg}`);
      setError(msg);
    } finally {
      setSubmitting(false);
      onRunningChange?.(false);
    }
  };

  const pollLegacyTask = async (taskId: string, module: string, jobId: string) => {
    addLogLine(`[${analysisLabel(module)}] 正在读取分析任务： ${taskId}`);
    for (;;) {
      const task = await getLegacyScriptHubTask(taskId);
      const progress = Number(task.progress || 0);
      setJobProgress((prev) => ({ ...prev, [jobId]: progress }));
      setJobStatus((prev) => ({ ...prev, [jobId]: task.status }));
      setJobStage((prev) => ({ ...prev, [jobId]: task.stage || task.detail || "" }));
      addLogLine(`[${analysisLabel(module)}] ${statusLabels[task.status] || "处理中"} ${Math.round(progress)}% ${task.stage || task.detail || ""}`.trim(), jobId);

      if (isTerminalJobStatus(task.status)) {
        return legacyScriptHubTaskToResults(task);
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };

  const pollModernJob = async (jobId: string, module: string) => {
    addLogLine(`[${analysisLabel(module)}] 正在读取任务： ${jobId}`);
    for (;;) {
      const jobResponse = await getJob(jobId);
      const status = jobResponse.job.status;
      setJobProgress((prev) => ({ ...prev, [jobId]: Number(jobResponse.job.progress || 0) }));
      setJobStatus((prev) => ({ ...prev, [jobId]: status }));
      setJobStage((prev) => ({ ...prev, [jobId]: jobResponse.job.stage || jobResponse.job.detail || "" }));
      addLogLine(`[${analysisLabel(module)}] ${statusLabels[status] || "处理中"} ${Math.round(Number(jobResponse.job.progress || 0))}% ${jobResponse.job.stage || jobResponse.job.detail || ""}`.trim(), jobId);

      if (isTerminalJobStatus(status)) {
        addLogLine(`[${analysisLabel(module)}] 最终状态： ${statusLabels[status] || "未知状态"}。正在读取结果。`);
        return getJobResults(jobId);
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };


  const hasJobs = jobIds.length > 0;
  const isRunning = submitting || Object.values(jobStatus).some((status) => status === "queued" || status === "running");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      {/* Header */}
      <div>
        <h2 style={{ margin: 0 }}>第四步：运行分析</h2>
        <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          确认分组和指标后开始运行。完成后可查看报告和下载数据。
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
            关闭提示
          </button>
        </div>
      )}

      {/* Run digest summary chips */}
      <Card>
        <h4 style={{ margin: "0 0 var(--spacing-md) 0", fontSize: "0.85rem", fontWeight: 600 }}>
          运行概览
        </h4>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
          <SummaryChip icon={Layers} label="分析模块" value={selectedModules.length ? selectedModules.map(analysisLabel).join("、") : "未选择"} color="var(--accent)" />
          <SummaryChip icon={FileText} label="项目" value={projectId || "未选择"} color="var(--success)" />
          <SummaryChip icon={Zap} label="任务" value={`${jobIds.length}/${selectedModules.length}`} color="var(--warning)" />
          <SummaryChip icon={Terminal} label="任务" value={taskName} color="#af52de" />
        </div>
      </Card>

      {selectedModules.some(canBind) && <Card>
        <h4>分析结果来源</h4>
        <p style={{color: "var(--text-secondary)", fontSize: 13}}>使用本批次结果时，前序分析成功后自动继续；前序失败则停止对应的下游分析。</p>
        <p aria-label="实际执行顺序" style={{fontSize: 13}}>执行顺序：{executionModules.map(analysisLabel).join(" → ")}</p>
        {selectedModules.map(module => canBind(module) && <label key={module} style={{display: "grid", gap: 6, marginTop: 12}}>
          {analysisLabel(module)} · 输入来源
          <select className="input" disabled={submitting || isRunning || hasJobs} value={useBatchResult[module] ? "batch" : "existing"} onChange={event => setUseBatchResult(previous => ({...previous, [module]: event.target.value === "batch"}))}>
            <option value="existing">使用上一步配置的输入</option>
            <option value="batch">使用本批次{sourceFor(module) === "volcano" ? "差异表达分析" : "克隆共享分析"}的新结果</option>
          </select>
          {useBatchResult[module] && <span style={{fontSize: 13}}>{sourceFor(module) === "volcano" ? "差异表达分析" : "克隆共享分析"} → {analysisLabel(module)}；{sourceFor(module) === "volcano" ? "沿用前序比较条件与差异筛选结果，不重复计算差异。" : "链和分组须与前序设置一致。"}</span>}
        </label>)}
      </Card>}

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
          任务名称
          <input
            type="text"
            value={taskName}
            onChange={(e) => setTaskName(e.target.value)}
            placeholder="请输入本次分析的名称…"
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
            {submitting ? "正在提交…" : selectedModules.length > 1 ? "运行所选模块" : "开始分析"}
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
              const terminal = isTerminalJobStatus(status);
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
                        {analysisLabel(jobModules[jobId] || "分析任务")} · 任务 {jobId.slice(0, 8)}
                      </span>
                      <StatusBadge status={status} />
                    </div>
                    {isRunning && (
                      <a href="/analysis/script-hub/jobs" target="_blank" rel="noreferrer" style={cancelBtnStyle}>
                        查看任务
                      </a>
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

          <details open={logsOpen} onToggle={event => setLogsOpen(event.currentTarget.open)} style={{border: "1px solid var(--separator)", borderRadius: "var(--radius-panel)", padding: "var(--spacing-md)", background: "var(--bg-elevated)"}}>
            <summary>执行日志（最近 {logLines.length} 条变化）</summary>
            <pre style={{whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 280, overflow: "auto", fontSize: "0.8rem"}}>{logLines.length ? logLines.join("\n") : "等待任务状态…"}</pre>
            <div ref={logEndRef} />
          </details>
        </>
      )}
    </div>
  );
}

function validatePayload(module: string, payload: Record<string, unknown>, usesBatchResult = false) {
  if (module === "profile" && (!payload.param_begin || !payload.param_over)) {
    throw new Error("请返回上一步，选择要比较的指标范围。");
  }
  if (Array.isArray(payload.selected_samples) && !payload.selected_samples.filter(Boolean).length) {
    throw new Error(`[${analysisLabel(module)}] 请至少选择一个样本，或点击“全部样本”。`);
  }
  const groupError = validateGroupFields(module, payload);
  if (groupError) throw new Error(`[${analysisLabel(module)}] ${groupError}`);
  const groupValueError = validateGroupValues(module, payload);
  if (groupValueError) throw new Error(`[${analysisLabel(module)}] ${groupValueError}`);
  const groupedSampleError = validateGroupedSamples(module, payload);
  if (groupedSampleError) throw new Error(`[${analysisLabel(module)}] ${groupedSampleError}`);
  const cacheError = usesBatchResult ? "" : validateCacheInputs(module, payload);
  if (cacheError) throw new Error(`[${analysisLabel(module)}] ${cacheError}`);
  if (module === "charts") {
    const selectedSamples = Array.isArray(payload.samples) ? payload.samples.filter(Boolean) : [];
    const selectedChains = Array.isArray(payload.selected_chains) ? payload.selected_chains.filter(Boolean) : [];
    if (!selectedSamples.length) {
      throw new Error("请至少选择一个用于绘图的样本。");
    }
    if (!selectedChains.length) {
      throw new Error("请至少选择一个用于绘图的链类型。");
    }
  }
}

function validateGroupFields(module: string, payload: Record<string, unknown>) {
  const groupRequirements: Record<string, string[]> = {
    "db-alignment": ["categories"],
    profile: ["grouptype_fields", "grouping_begin"],
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
  return hasGroupField ? "" : "请选择分组字段";
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
    return "请选择分组值";
  }
  const hasValue = Object.values(valueMap as Record<string, unknown>).some((item) =>
    Array.isArray(item) && item.some((value) => String(value || "").trim()),
  );
  return hasValue ? "" : "请选择分组值";
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
    return "请在每个分组中选择样本";
  }
  const selectedGroups = payload.selected_group_values;
  if (!selectedGroups || typeof selectedGroups !== "object" || Array.isArray(selectedGroups)) {
    return "请在每个分组中选择样本";
  }
  for (const [field, values] of Object.entries(selectedGroups as Record<string, unknown>)) {
    if (!Array.isArray(values)) continue;
    const groups = (valueMap as Record<string, unknown>)[field];
    if (!groups || typeof groups !== "object" || Array.isArray(groups)) {
      return `请为 ${field} 选择样本`;
    }
    for (const groupValue of values) {
      const key = String(groupValue || "").trim();
      if (!key) continue;
      const samples = (groups as Record<string, unknown>)[key];
      if (!Array.isArray(samples) || !samples.some((sample) => String(sample || "").trim())) {
        return `请为 ${field} = ${key} 选择样本`;
      }
    }
  }
  return "";
}

function validateCacheInputs(module: string, payload: Record<string, unknown>) {
  const hasArtifact = Boolean(String(payload.upstream_artifact_id || "").trim());
  if (module === "go-kegg-enrichment" && payload.input_mode === "deg" && !hasArtifact) return "请选择来源差异表达结果";
  if (module === "volcano" && String(payload.input_mode || "") === "usage" && !hasArtifact && !String(payload.data_dir || "").trim()) {
    return "请选择克隆 V/J 基因使用缓存";
  }
  if (module === "umapin" && !hasArtifact && !String(payload.data_path || "").trim()) {
    return "请选择克隆特征降维缓存";
  }
  if (module === "mait-nkt") {
    const source = String(payload.tra_source || "upload");
    if (source === "pep_analysis" && !hasArtifact && !String(payload.tra_path || payload.source_job_id || "").trim()) {
      return "请选择受体 α 链缓存";
    }
    if (source === "upload" && !String(payload.tra_path || "").trim()) {
      return "请选择受体 α 链数据文件";
    }
    if (payload.mait_nkt_inspect_ok === false) {
      return "特征检查失败，请先选择有效的受体 α 链数据来源";
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
