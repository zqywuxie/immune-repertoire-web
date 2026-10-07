import { validateAnalysisPayload } from "../configurationValidation";
import { batchResultSource, orderBatchDependencies } from "../batchDependencies";
import { isTerminalJobStatus } from "../../jobs/BatchStatus";
import { BatchExecutionProgress, batchItemStatus, type BatchItem } from "../../jobs/BatchExecutionProgress";
import type { JobSummary } from "../../../shared/types/domain";
import { preferLatestJobSnapshot } from "../../../shared/utils/jobState";
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
import { analysisLabel, jobTextLabel } from "../../../shared/utils/analysisLabels";
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
  const [connectionNotice, setConnectionNotice] = useState<string | null>(null);
  const [lastReadAt, setLastReadAt] = useState("");
  const [taskName, setTaskName] = useState(`${modules.length === 1 ? analysisLabel(modules[0]) : "组合分析"}_${new Date().toLocaleDateString("sv-SE")}`);
  const [logLines, setLogLines] = useState<string[]>([]);
  const [jobProgress, setJobProgress] = useState<Record<string, number>>({});
  const [jobStatus, setJobStatus] = useState<Record<string, string>>({});
  const [jobStage, setJobStage] = useState<Record<string, string>>({});
  const [jobModules, setJobModules] = useState<Record<string, string>>({});
  const [batchPlan, setBatchPlan] = useState<BatchItem[]>([]);
  const [batchJobs, setBatchJobs] = useState<Record<string, JobSummary>>({});
  const [batchReadErrors, setBatchReadErrors] = useState<Record<string, string>>({});
  const batchSnapshots = useRef<Record<string, JobSummary>>({});
  const batchResults = useRef<Record<string, JobResultsResponse>>({});
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

  // Retry reads of the existing task; submission is never part of reconnection.
  const readTaskState = async <T,>(read: () => Promise<T>): Promise<T | undefined> => {
    while (mounted.current) {
      try {
        const snapshot = await read();
        if (!mounted.current) return;
        setConnectionNotice(null);
        setLastReadAt(new Date().toLocaleTimeString("zh-CN", {hour12: false}));
        return snapshot;
      } catch (reason) {
        if (!mounted.current) return;
        const status = (reason as {status?: number})?.status;
        if (status && status < 500 && status !== 408 && status !== 429) {
          setConnectionNotice(null);
          throw reason;
        }
        setConnectionNotice("任务状态连接暂时中断，正在重新读取；服务端继续执行。");
        addLogLine("状态连接中断，等待重连。", "connection");
        await new Promise(resolve => setTimeout(resolve, 1500));
      }
    }
  };

  const readBatchChild = async (child: BatchItem) => {
    const id = child.job_id;
    if (!id || !mounted.current || batchResults.current[id]) return;
    const remember = (job: JobSummary) => {
      batchSnapshots.current[id] = preferLatestJobSnapshot(batchSnapshots.current[id] || null, job);
      setBatchJobs({...batchSnapshots.current});
    };
    try {
      const response = await getJob(id);
      if (!mounted.current) return;
      remember(response.job);
      if (isTerminalJobStatus(response.job.status)) {
        const result = await getJobResults(id);
        if (!mounted.current) return;
        remember(result.job);
        batchResults.current[id] = result;
        onComplete({...batchResults.current});
      }
      setBatchReadErrors(previous => {
        const next = {...previous}; delete next[id]; return next;
      });
    } catch {
      if (!mounted.current) return;
      setBatchReadErrors(previous => ({...previous, [id]: "此项状态或结果暂时读取失败，保留最近记录。服务端任务不受影响。"}));
    }
  };

  const handleRunAnalysis = async () => {
    if (!selectedModules.length) {
      setError("尚未选择分析模块。");
      return;
    }
    setSubmitting(true);
    onRunningChange?.(true);
    setError(null);
    setConnectionNotice(null);
    setLastReadAt("");
    setLogLines([]);
    lastLogBySource.current.clear();
    setJobProgress({});
    setJobStatus({});
    setJobStage({});
    setJobModules({});
    setBatchPlan([]);
    setBatchJobs({});
    setBatchReadErrors({});
    batchSnapshots.current = {};
    batchResults.current = {};
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
          validateAnalysisPayload(module, payload, bind);
          return {module, payload, ...(bind ? {upstream_from: sourceIndex, depends_on: [sourceIndex]} : {})};
        });
        const response = await submitAnalysisBatch(projectId, String(baseConfig.asset_set || ""), taskName, items);
        if (!mounted.current) return;
        setBatchPlan(items.map(item => ({...item, status: "queued"})));
        onBatchCreated?.(response.job_id);
        addLogLine("完整分析计划已交给服务端，离开页面不影响后续任务执行。");
        while (mounted.current) {
          const snapshot = await readTaskState(() => getJob(response.job_id));
          if (!snapshot || !mounted.current) return;
          const parent = snapshot.job as unknown as {status: string; payload?: {items?: BatchItem[]}};
          const children = parent.payload?.items || [];
          setBatchPlan(children);
          onJobsCreated(children.map(child => child.job_id).filter((id): id is string => Boolean(id)));
          await Promise.all(children.map(readBatchChild));
          if (!mounted.current) return;
          const statuses = children.map(child => batchItemStatus(child, batchSnapshots.current[child.job_id || ""]));
          onBatchStatuses?.(statuses);
          children.forEach((child, index) => {
            const job = batchSnapshots.current[child.job_id || ""];
            addLogLine("[" + analysisLabel(child.module) + "] " + (statusLabels[statuses[index]] || "等待确认")
              + (job?.stage ? " · " + jobTextLabel(job.stage) : "")
              + (child.error ? "：" + child.error : ""), child.job_id || "batch-item-" + index);
          });
          if (isTerminalJobStatus(parent.status)) {
            const errors = children.filter(child => child.status !== "completed").map(child => analysisLabel(child.module) + "：" + (child.error || statusLabels[child.status] || "未完成"));
            if (errors.length) setError(errors.join("；"));
            addLogLine("批次执行已结束，已生成的结果可继续查看。");
            break;
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
        validateAnalysisPayload(module, payload);

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

        if (!mounted.current) return;
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

        if (!moduleResults || !mounted.current) return;
        completedResults[submittedJobId] = moduleResults;
        onComplete({ ...completedResults });
      }
      addLogLine(`本次任务已结束：${Object.values(completedResults).filter(result => result.status === "completed").length}/${createdJobIds.length} 项成功，其余状态请查看任务记录。`);
    } catch (err) {
      if (!mounted.current) return;
      const msg = err instanceof Error ? err.message : "提交失败";
      addLogLine(`[错误] ${msg}`);
      setError(msg);
    } finally {
      if (mounted.current) {
        setSubmitting(false);
        onRunningChange?.(false);
      }
    }
  };

  const pollLegacyTask = async (taskId: string, module: string, jobId: string) => {
    addLogLine(`[${analysisLabel(module)}] 正在读取分析任务： ${taskId}`);
    while (mounted.current) {
      const task = await readTaskState(() => getLegacyScriptHubTask(taskId));
      if (!task) return;
      const progress = Number(task.progress || 0);
      setJobProgress((prev) => ({ ...prev, [jobId]: progress }));
      setJobStatus((prev) => ({ ...prev, [jobId]: task.status }));
      setJobStage((prev) => ({ ...prev, [jobId]: jobTextLabel(task.stage || task.detail || "") }));
      addLogLine(`[${analysisLabel(module)}] ${statusLabels[task.status] || "处理中"} ${Math.round(progress)}% ${jobTextLabel(task.stage || task.detail || "")}`.trim(), jobId);

      if (isTerminalJobStatus(task.status)) {
        return legacyScriptHubTaskToResults(task);
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };

  const pollModernJob = async (jobId: string, module: string) => {
    addLogLine(`[${analysisLabel(module)}] 正在读取任务： ${jobId}`);
    while (mounted.current) {
      const jobResponse = await readTaskState(() => getJob(jobId));
      if (!jobResponse) return;
      const status = jobResponse.job.status;
      setJobProgress((prev) => ({ ...prev, [jobId]: Number(jobResponse.job.progress || 0) }));
      setJobStatus((prev) => ({ ...prev, [jobId]: status }));
      setJobStage((prev) => ({ ...prev, [jobId]: jobTextLabel(jobResponse.job.stage || jobResponse.job.detail || "") }));
      addLogLine(`[${analysisLabel(module)}] ${statusLabels[status] || "处理中"} ${Math.round(Number(jobResponse.job.progress || 0))}% ${jobTextLabel(jobResponse.job.stage || jobResponse.job.detail || "")}`.trim(), jobId);

      if (isTerminalJobStatus(status)) {
        addLogLine(`[${analysisLabel(module)}] 最终状态： ${statusLabels[status] || "未知状态"}。正在读取结果。`);
        return readTaskState(() => getJobResults(jobId));
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  };


  const hasJobs = jobIds.length > 0 || batchPlan.length > 0;
  const isRunning = submitting || Object.values(jobStatus).some((status) => status === "queued" || status === "running");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      {/* Header */}
      <div>
        <h2 style={{ margin: 0 }}>运行分析</h2>
        <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          确认分组和指标后开始运行。完成后可查看报告和下载数据。
        </p>
      </div>

      {connectionNotice && <div role="status" aria-label="任务状态连接" style={{
        padding: "var(--spacing-md) var(--spacing-lg)", border: "1px solid var(--separator)",
        borderRadius: "var(--radius-control)", background: "var(--bg-elevated)", overflowWrap: "anywhere",
      }}>
        <strong>{connectionNotice}</strong>
        <p style={{margin: "6px 0 0", color: "var(--text-secondary)", fontSize: "0.85rem"}}>
          {lastReadAt ? "最后读取时间：" + lastReadAt : "尚未取得任务状态。"} 保留最近进度，恢复后继续查看同一任务。
        </p>
      </div>}

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

      {selectedModules.length > 1 && <Card>
        <h4>分析结果来源</h4>
        <p style={{color: "var(--text-secondary)", fontSize: 13}}>使用本批次结果时，前序分析成功后自动继续；前序失败则停止对应的下游分析。</p>
        <ol aria-label="分析依赖关系" style={{display:"grid",gap:12,paddingLeft:24}}>{executionModules.map(module => {
          const source = useBatchResult[module] ? sourceFor(module) : undefined;
          return <li key={module}><strong>{analysisLabel(module)}</strong><p style={{fontSize:13,color:"var(--text-secondary)",margin:"4px 0"}}>{source ? `等待${analysisLabel(source)}完成 → 使用其输出；前序失败时停止此项` : payloadFor(module).upstream_artifact_id ? "复用已选择的历史分析结果" : "使用本项配置的输入，无本批次前置依赖"}</p></li>;
        })}</ol>
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
          {batchPlan.length > 0 ? <BatchExecutionProgress items={batchPlan} jobs={batchJobs} readErrors={batchReadErrors} onRetry={item => { void readBatchChild(item); }}/> :
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
                        {analysisLabel(jobModules[jobId] || "分析任务")} · 任务 {jobId.slice(-8)}
                      </span>
                      <StatusBadge status={status} />
                    </div>
                    {isRunning && (
                      <a href={"/analysis/script-hub/jobs?job=" + encodeURIComponent(jobId)} target="_blank" rel="noreferrer" style={taskLinkStyle}>
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
          </div>}

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

const taskLinkStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "8px 16px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "transparent",
  color: "var(--accent)",
  fontWeight: 500,
  fontSize: "0.82rem",
  cursor: "pointer",
};
