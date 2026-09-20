import { statusLabels } from "../../shared/components/StatusBadge";
import { analysisLabel } from "../../shared/utils/analysisLabels";
import { useMemo, useState, useEffect } from "react";
import { Activity, FileJson2, X, Package } from "lucide-react";
import { type JobResultsResponse } from "../../shared/api/jobs";
import { useJobResult } from "../../shared/hooks/useJobResult";
import { JobResultPanel } from "./JobResultPanel";
import { ProgressBar } from "../../shared/components/ProgressBar";
import { StatusBadge } from "../../shared/components/StatusBadge";

import type { JobSummary } from "../../shared/types/domain";

type Props = {
  job: JobSummary;
  loading?: boolean;
  onClose: () => void;
  result?: JobResultsResponse | null;
  resultLoading?: boolean;
  resultError?: string;
  onRetry?: () => void;
};

export function JobDetailPanel(props: Props) {
  return props.result === undefined ? <StandaloneDetail {...props} /> : <DetailContent key={props.job.job_id || props.job.id} {...props} />;
}
function StandaloneDetail(props: Props) {
  const state = useJobResult(props.job.job_id || props.job.id);
  return <DetailContent key={props.job.job_id || props.job.id} {...props} result={state.result} resultLoading={!state.result && !state.error} resultError={state.error} onRetry={state.retry} />;
}
function DetailContent({ job, loading = false, onClose, result, resultLoading = false, resultError = "", onRetry }: Props) {
  const [activeTab, setActiveTab] = useState<"config" | "progress" | "results">(job.status === "completed" ? "results" : "progress");
  const jobId = job.job_id || job.id;
  useEffect(() => { if (job.status === "completed") setActiveTab("results"); }, [job.status]);
  const moduleConfig = useMemo(() => extractModuleConfig(job), [job]);
  const progressHistory = useMemo(() => extractProgressHistory(job), [job]);
  const hasConfig = Object.keys(moduleConfig).length > 0;

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

        {activeTab === "results" && <div>
          {resultError && <div role="alert"><p>{resultError}</p><button className="btn btn-secondary" onClick={onRetry}>重新读取结果</button></div>}
          <JobResultPanel result={result || null} loading={resultLoading} embedded />
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
