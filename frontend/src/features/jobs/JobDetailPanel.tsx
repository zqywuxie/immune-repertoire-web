import { statusLabels } from "../../shared/components/StatusBadge";
import { analysisLabel } from "../../shared/utils/analysisLabels";
import { useMemo, useState, useEffect, useRef } from "react";
import { Activity, FileJson2, X, Package, Download, ExternalLink } from "lucide-react";
import { getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import { useJobEvents } from "../../shared/hooks/useJobEvents";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { Skeleton } from "../../shared/components/Skeleton";
import type { JobSummary } from "../../shared/types/domain";

type Props = {
  job: JobSummary;
  loading?: boolean;
  onClose: () => void;
};

export function JobDetailPanel({ job, loading = false, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<"config" | "progress" | "results">("results");
  const jobId = job.job_id || job.id;
  const liveJob = useJobEvents(jobId);
  const fetchedRef = useRef<string | null>(null);

  // Results state
  const [resultsState, setResultsState] = useState<{ result: JobResultsResponse | null; loading: boolean; error: string }>({ result: null, loading: false, error: "" });

  useEffect(() => {
    if (!jobId || fetchedRef.current === jobId) return;
    fetchedRef.current = jobId;
    setResultsState({ result: null, loading: true, error: "" });
    getJobResults(jobId)
      .then((r) => setResultsState({ result: r, loading: false, error: "" }))
      .catch((err) => setResultsState({ result: null, loading: false, error: err.message || "读取结果失败" }));
  }, [jobId]);

  // Refresh on SSE event
  useEffect(() => {
    if (!liveJob.event || !jobId) return;
    if (liveJob.event.status === "completed") {
      getJobResults(jobId)
        .then((r) => setResultsState({ result: r, loading: false, error: "" }))
        .catch(() => {});
    }
  }, [liveJob.event, jobId]);

  const moduleConfig = useMemo(() => extractModuleConfig(job), [job]);
  const progressHistory = useMemo(() => extractProgressHistory(job), [job]);
  const hasConfig = Object.keys(moduleConfig).length > 0;
  const resultOutputs = resultsState.result?.outputs || [];
  const viewerOutput = useMemo(() => preferredViewerOutput(resultOutputs), [resultOutputs]);
  const zipOutputs = useMemo(() => resultOutputs.filter(isArchiveOutput), [resultOutputs]);

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
            <h3 style={{ margin: 0, fontSize: "0.95rem" }}>任务</h3>
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

      <div style={{ padding: "var(--spacing-lg)", display: "grid", gap: "var(--spacing-lg)" }}>
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

        {activeTab === "config" && (
          <div>
            <div style={sectionLabelStyle}>分析模块配置</div>
            {hasConfig ? (
            <pre
              style={{
                margin: 0,
                padding: "var(--spacing-md)",
                borderRadius: "var(--radius-control)",
                border: "1px solid var(--separator)",
                background: "var(--bg-root)",
                color: "var(--text-primary)",
                fontSize: "0.78rem",
                lineHeight: 1.55,
                maxHeight: "360px",
                overflow: "auto",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
              }}
            >
              {JSON.stringify(moduleConfig, null, 2)}
            </pre>
            ) : (
            <div
              style={{
                padding: "var(--spacing-md)",
                borderRadius: "var(--radius-control)",
                background: "var(--bg-root)",
                color: "var(--text-tertiary)",
                fontSize: "0.82rem",
              }}
            >
              尚未记录分析模块配置。
            </div>
            )}
          </div>
        )}

        {activeTab === "progress" && (
          <div style={{ display: "grid", gap: "var(--spacing-lg)" }}>
            <div style={{ display: "grid", gap: "var(--spacing-sm)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--spacing-md)" }}>
                <div>
                  <div style={sectionLabelStyle}>任务进度</div>
                  <div style={{ color: "var(--text-tertiary)", fontSize: "0.76rem" }}>
                    {job.stage || job.detail || "等待更新"}
                  </div>
                </div>
                <StatusBadge status={job.status} />
              </div>
              <ProgressBar value={Number(job.progress || 0)} />
              <div style={{ color: "var(--text-secondary)", fontSize: "0.82rem", fontWeight: 600 }}>
                {Number(job.progress || 0).toFixed(0)}%
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                gap: "var(--spacing-sm)",
              }}
            >
              <DetailItem label="分析模块" value={analysisLabel(job.module)} />
              <DetailItem label="状态" value={statusLabels[job.status] || "未知状态"} />
              <DetailItem label="运行阶段" value={job.stage || "-"} />
              <DetailItem label="详情" value={job.detail || "-"} />
              <DetailItem label="创建时间" value={formatDate(job.created_at)} />
              <DetailItem label="更新时间" value={formatDate(job.updated_at)} />
              <DetailItem label="开始时间" value={formatDate(job.started_at)} />
              <DetailItem label="已完成" value={formatDate(job.completed_at)} />
            </div>

            {job.error && (
              <div
                style={{
                  padding: "var(--spacing-md)",
                  borderRadius: "var(--radius-control)",
                  border: "1px solid color-mix(in srgb, var(--danger) 40%, var(--separator))",
                  background: "color-mix(in srgb, var(--danger) 10%, var(--bg-root))",
                  color: "var(--danger)",
                  fontSize: "0.8rem",
                  lineHeight: 1.5,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {job.error}
              </div>
            )}

            <div style={{ display: "grid", gap: "var(--spacing-sm)" }}>
              <div style={sectionLabelStyle}>进度记录</div>
              {progressHistory.length > 0 ? (
                <div style={{ display: "grid", gap: "8px" }}>
                  {progressHistory.map((entry, index) => (
                    <div
                      key={`${entry.timestamp || ""}-${index}`}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "58px minmax(0, 1fr)",
                        gap: "10px",
                        padding: "10px 12px",
                        borderRadius: "var(--radius-control)",
                        background: "var(--bg-root)",
                        border: "1px solid var(--separator)",
                      }}
                    >
                      <div style={{ color: "var(--accent)", fontSize: "0.82rem", fontWeight: 750 }}>
                        {entry.progress.toFixed(0)}%
                      </div>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--spacing-sm)" }}>
                          <span style={{ color: "var(--text-primary)", fontSize: "0.82rem", fontWeight: 650 }}>
                            {entry.stage || "-"}
                          </span>
                          <span style={{ color: "var(--text-tertiary)", fontSize: "0.72rem", whiteSpace: "nowrap" }}>
                            {formatDate(entry.timestamp)}
                          </span>
                        </div>
                        {entry.detail && (
                          <div style={{ marginTop: "3px", color: "var(--text-secondary)", fontSize: "0.76rem", lineHeight: 1.45 }}>
                            {entry.detail}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  style={{
                    padding: "var(--spacing-md)",
                    borderRadius: "var(--radius-control)",
                    background: "var(--bg-root)",
                    color: "var(--text-tertiary)",
                    fontSize: "0.82rem",
                  }}
                >
                  暂无进度记录。
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === "results" && (
          <div style={{ display: "grid", gap: "var(--spacing-lg)" }}>
            <div style={sectionLabelStyle}>任务输出</div>

            {resultsState.loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
                <Skeleton height="120px" /><Skeleton height="80px" />
              </div>
            ) : resultsState.error ? (
              <div style={{ padding: "var(--spacing-lg)", borderRadius: "var(--radius-control)", background: "rgba(255,59,48,0.06)", color: "var(--danger)", fontSize: "0.85rem" }}>
                {resultsState.error}
              </div>
            ) : resultsState.result ? (
              <>
                <div
                  style={{
                    display: "grid",
                    gap: "var(--spacing-md)",
                    padding: "var(--spacing-lg)",
                    borderRadius: "var(--radius-control)",
                    background: "var(--bg-root)",
                    border: "1px solid var(--separator)",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--spacing-md)", flexWrap: "wrap" }}>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>
                        {analysisLabel(resultsState.result.job.module || job.module)}
                      </div>
                      <div style={{ color: "var(--text-secondary)", fontSize: "0.78rem", marginTop: "3px" }}>
                        {resultOutputs.length} 输出 可供查看，请打开报告查看图表和数据。
                      </div>
                    </div>
                    <StatusBadge status={resultsState.result.status} />
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
                    <a
                      href={viewerOutput?.url || "#"}
                      target="_blank"
                      rel="noreferrer"
                      aria-disabled={!viewerOutput}
                      style={{
                        ...primaryLinkButtonStyle,
                        opacity: viewerOutput ? 1 : 0.5,
                        pointerEvents: viewerOutput ? "auto" : "none",
                      }}
                    >
                      <ExternalLink size={15} />
                      查看报告
                    </a>
                    {zipOutputs.length > 0 ? (
                      zipOutputs.map((output, index) => (
                        <a
                          key={`${output.url}-${index}`}
                          href={(output as { download_url?: string | null }).download_url || output.url}
                          target="_blank"
                          rel="noreferrer"
                          download
                          style={secondaryLinkButtonStyle}
                          title={output.label || "下载 ZIP"}
                        >
                          <Download size={15} />
                          {output.label || `下载压缩包 ${index + 1}`}
                        </a>
                      ))
                    ) : (
                      resultOutputs.slice(0, 4).map((output, index) => (
                        <a
                          key={`${output.url}-${index}`}
                          href={(output as { download_url?: string | null }).download_url || output.url}
                          target="_blank"
                          rel="noreferrer"
                          download
                          style={secondaryLinkButtonStyle}
                          title={output.label || "下载输出文件"}
                        >
                          <Download size={15} />
                          {output.label || `Download ${index + 1}`}
                        </a>
                      ))
                    )}
                  </div>
                </div>
                {resultsState.result.assets && resultsState.result.assets.length > 0 && (
                  <div>
                    <div style={sectionLabelStyle}>已登记数据（{resultsState.result.assets.length})</div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
                      {resultsState.result.assets.map((a: any) => (
                        <a key={a.id} href={`/api/assets/${a.id}/download`} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: "4px", padding: "6px 12px", borderRadius: "var(--radius-pill)", border: "1px solid var(--separator)", fontSize: "0.78rem", color: "var(--accent)", textDecoration: "none" }}>
                          <Download size={12} /> {a.original_name || a.id}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div style={{ padding: "var(--spacing-lg)", borderRadius: "var(--radius-control)", background: "var(--bg-root)", color: "var(--text-tertiary)", fontSize: "0.82rem", textAlign: "center" }}>
                {job.status === "running" || job.status === "queued" ? "等待任务完成…" : "暂无结果。"}
              </div>
            )}
          </div>
        )}

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

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        minWidth: 0,
        padding: "10px 12px",
        borderRadius: "var(--radius-control)",
        background: "var(--bg-root)",
      }}
    >
      <div style={{ color: "var(--text-tertiary)", fontSize: "0.7rem", marginBottom: "4px" }}>
        {label}
      </div>
      <div style={{ color: "var(--text-primary)", fontSize: "0.82rem", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {value}
      </div>
    </div>
  );
}

function formatDate(value: unknown): string {
  if (!value) return "-";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function extractModuleConfig(job: JobSummary): Record<string, unknown> {
  const payload = job.payload && typeof job.payload === "object" ? job.payload : {};
  const directConfig = recordValue(payload._module_config);
  if (directConfig) return directConfig;

  const configJson = recordValue(payload.config_json);
  if (configJson) {
    const preferredKeys = [
      "selected_modules",
      "selected_chains",
      "field_mapping",
      "group_fields",
      "optional_steps",
      "pvalue_threshold",
      "min_sample_threshold",
      "sample_keys",
    ];
    const picked: Record<string, unknown> = {};
    for (const key of preferredKeys) {
      if (configJson[key] !== undefined) picked[key] = configJson[key];
    }
    return Object.keys(picked).length ? picked : configJson;
  }

  const hiddenKeys = new Set([
    "_project_id",
    "_task_name",
    "analysis_signature",
    "asset_set",
    "config_json",
    "force_rerun",
    "input_assets",
    "pep_paths",
    "profile_path",
    "project_id",
    "transcriptome_path",
  ]);
  const fallback: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (hiddenKeys.has(key)) continue;
    if (key === "samples" && Array.isArray(value)) {
      fallback.samples = value
        .map((item) => {
          if (item && typeof item === "object") {
            const record = item as Record<string, unknown>;
            return record.sample_key || record.display_name || record.original_name;
          }
          return item;
        })
        .filter(Boolean);
      continue;
    }
    fallback[key] = value;
  }
  return fallback;
}

function extractProgressHistory(job: JobSummary): Array<{
  progress: number;
  stage: string;
  detail: string;
  timestamp: string;
}> {
  const history = (job as JobSummary & { history?: unknown }).history;
  if (!Array.isArray(history)) return [];
  return history
    .map((entry) => {
      const record = entry && typeof entry === "object" ? entry as Record<string, unknown> : {};
      return {
        progress: Number(record.progress || 0),
        stage: String(record.stage || ""),
        detail: String(record.detail || ""),
        timestamp: String(record.timestamp || record.updated_at || ""),
      };
    })
    .filter((entry) => entry.stage || entry.detail || entry.progress > 0)
    .slice(-20)
    .reverse();
}

function recordValue(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function preferredViewerOutput(outputs: JobResultsResponse["outputs"]) {
  const withUrl = outputs.filter((output) => String(output.url || "").trim());
  return (
    withUrl.find((output) => String(output.kind || "").toLowerCase() === "html") ||
    withUrl.find((output) => /viewer|report/i.test(String(output.label || output.url || ""))) ||
    withUrl.find((output) => !isArchiveOutput(output)) ||
    withUrl[0] ||
    null
  );
}

function isArchiveOutput(output: JobResultsResponse["outputs"][number]) {
  const kind = String(output.kind || "").toLowerCase();
  const url = String(output.url || "").toLowerCase();
  return kind === "zip" || url.includes(".zip") || /zip|archive|bundle/i.test(String(output.label || ""));
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

const sectionLabelStyle: React.CSSProperties = {
  fontSize: "0.78rem",
  color: "var(--text-secondary)",
  fontWeight: 700,
  marginBottom: "var(--spacing-sm)",
};

const primaryLinkButtonStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "9px 14px",
  borderRadius: "var(--radius-control)",
  background: "var(--accent)",
  color: "#fff",
  textDecoration: "none",
  fontSize: "0.82rem",
  fontWeight: 650,
};

const secondaryLinkButtonStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "9px 14px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  textDecoration: "none",
  fontSize: "0.82rem",
  fontWeight: 600,
  maxWidth: "220px",
  overflow: "hidden",
  textOverflow: "ellipsis",
  whiteSpace: "nowrap",
};
