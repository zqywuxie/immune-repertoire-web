import { useState, useCallback, type DragEvent, type ChangeEvent } from "react";
import {
  BarChart3, Upload, Play, Table2, X, FileUp, AlertTriangle, RefreshCw,
  FileText, ListFilter,
} from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import { listProjects } from "../../shared/api/projects";
import { submitJob, getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import { PageHeader } from "../../shared/components/PageHeader";
import { Card } from "../../shared/components/Card";
import { Tabs } from "../../shared/components/Tabs";
import { EmptyState } from "../../shared/components/EmptyState";
import { Skeleton } from "../../shared/components/Skeleton";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { ResultViewer } from "../../features/results/ResultViewer";

/* ── Types ── */

interface FileEntry {
  name: string;
  size: number;
  file: File;
}

interface SingleConfig {
  valueColumn: string;
  groupColumn: string;
}

interface MultiFileConfig {
  valueColumn: string;
  groupColumn: string;
  files: string[];
}

const COMPARISON_TABS = [
  { key: "single", label: "Single File" },
  { key: "multi", label: "Multi File" },
];

const STAT_TABLES = [
  { key: "kruskal", label: "Kruskal-Wallis" },
  { key: "dunn", label: "Dunn's Test" },
  { key: "boxplot", label: "Box Plot" },
];

/* ── Component ── */

export function StatisticalComparison() {
  const [activeTab, setActiveTab] = useState("single");
  const [activeStatTab, setActiveStatTab] = useState("kruskal");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [singleFile, setSingleFile] = useState<FileEntry | null>(null);
  const [multiFiles, setMultiFiles] = useState<FileEntry[]>([]);
  const [singleConfig, setSingleConfig] = useState<SingleConfig>({
    valueColumn: "",
    groupColumn: "",
  });
  const [multiConfig, setMultiConfig] = useState<MultiFileConfig>({
    valueColumn: "",
    groupColumn: "",
    files: [],
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitMessage, setSubmitMessage] = useState("");
  const [result, setResult] = useState<JobResultsResponse | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [resultError, setResultError] = useState("");
  const [fileSource, setFileSource] = useState<"upload" | "existing">("upload");
  const [singleGroupOrder, setSingleGroupOrder] = useState("");
  const [singleChartTitle, setSingleChartTitle] = useState("");
  const [multiGroupOrder, setMultiGroupOrder] = useState("");
  const [multiChartTitle, setMultiChartTitle] = useState("");
  const [correctionMode, setCorrectionMode] = useState("per_dataset");

  const projects = useApi(() => listProjects(), []);
  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const projectsError = projects.status === "error" ? projects.error : null;
  const loadingProjects = projects.status === "loading";
  const noProjects = projects.status === "ready" && projectList.length === 0;

  const handleSingleFileDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) setSingleFile({ name: file.name, size: file.size, file });
  }, []);

  const handleSingleFileInput = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setSingleFile({ name: file.name, size: file.size, file });
  }, []);

  const handleMultiFileAdded = useCallback((incoming: FileList | File[]) => {
    const entries: FileEntry[] = Array.from(incoming).map((f) => ({
      name: f.name,
      size: f.size,
      file: f,
    }));
    setMultiFiles((prev) => [...prev, ...entries]);
    setMultiConfig((prev) => ({
      ...prev,
      files: [...prev.files, ...entries.map((e) => e.name)],
    }));
  }, []);

  const handleMultiFileDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) handleMultiFileAdded(e.dataTransfer.files);
  }, [handleMultiFileAdded]);

  const handleMultiFileInput = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) handleMultiFileAdded(e.target.files);
  }, [handleMultiFileAdded]);

  const removeMultiFile = useCallback((name: string) => {
    setMultiFiles((prev) => prev.filter((f) => f.name !== name));
    setMultiConfig((prev) => ({
      ...prev,
      files: prev.files.filter((f) => f !== name),
    }));
  }, []);

  const handleSubmit = async () => {
    if (!selectedProjectId) return;
    setSubmitting(true);
    setSubmitError("");
    setSubmitMessage("");
    setResult(null);
    setResultError("");

    const isSingle = activeTab === "single";

    try {
      const payload: Record<string, unknown> = {
        project_id: selectedProjectId,
        comparison_type: isSingle ? "single_file" : "multi_file",
        ...(isSingle ? singleConfig : multiConfig),
        group_order: isSingle ? (singleGroupOrder || undefined) : (multiGroupOrder || undefined),
        chart_title: isSingle ? (singleChartTitle || undefined) : (multiChartTitle || undefined),
        correction_mode: isSingle ? undefined : correctionMode,
      };

      if (isSingle && singleFile) {
        payload.file = singleFile.name;
      }
      if (!isSingle) {
        payload.files = multiConfig.files;
      }

      const res = await submitJob({
        module: "statistical.comparison",
        payload,
        projectId: selectedProjectId,
      });

      setSubmitMessage(
        res.reused_result
          ? `Reused cached result ${res.result_id || res.job_id}.`
          : `Submitted job ${res.job_id}.`
      );

      if (res.job_id) {
        setResultLoading(true);
        try {
          const jobResult = await getJobResults(res.job_id);
          setResult(jobResult);
        } catch {
          setResultError("Failed to load results");
        } finally {
          setResultLoading(false);
        }
      }
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Submission failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader title="Statistical Comparison" subtitle="Kruskal-Wallis, Dunn's test, and boxplot visualization" />

      {projectsError && <ErrorBanner message={projectsError} />}

      {noProjects ? (
        <EmptyState
          icon={BarChart3}
          title="No projects available"
          description="Create a project from the Dashboard first."
          action={{ label: "Go to Dashboard", to: "/" }}
        />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)",
            gap: "var(--spacing-lg)",
            alignItems: "start",
          }}
        >
          {/* ── Left: Input Configuration ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
            {/* Project selector */}
            <Card>
              <label style={labelStyle}>
                Project
                {loadingProjects ? (
                  <Skeleton height="38px" />
                ) : (
                  <select
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    style={selectStyle}
                  >
                    <option value="">Select a project…</option>
                    {projectList.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                )}
              </label>
            </Card>

            {/* Tabs: Single vs Multi */}
            <Tabs tabs={COMPARISON_TABS} activeKey={activeTab} onChange={setActiveTab} />

            {/* Single File Tab */}
            {activeTab === "single" && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <FileText size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Single File
                </h4>

                {/* File source toggle */}
                <div style={{ display: "flex", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-md)" }}>
                  <button onClick={() => setFileSource("upload")} style={{
                    flex: 1, padding: "6px 12px", borderRadius: "var(--radius-pill)",
                    border: fileSource === "upload" ? "2px solid var(--accent)" : "1px solid var(--separator)",
                    background: fileSource === "upload" ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent",
                    color: fileSource === "upload" ? "var(--accent)" : "var(--text-secondary)", fontWeight: 500, fontSize: "0.82rem", cursor: "pointer",
                  }}><Upload size={14} /> Upload New</button>
                  <button onClick={() => setFileSource("existing")} style={{
                    flex: 1, padding: "6px 12px", borderRadius: "var(--radius-pill)",
                    border: fileSource === "existing" ? "2px solid var(--accent)" : "1px solid var(--separator)",
                    background: fileSource === "existing" ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent",
                    color: fileSource === "existing" ? "var(--accent)" : "var(--text-secondary)", fontWeight: 500, fontSize: "0.82rem", cursor: "pointer",
                  }}><ListFilter size={14} /> Select Existing</button>
                </div>

                {/* File upload */}
                <div
                  onDrop={handleSingleFileDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => document.getElementById("sc-single-input")?.click()}
                  style={dropZoneStyle}
                >
                  <Upload size={28} style={{ color: "var(--text-tertiary)", marginBottom: "var(--spacing-sm)" }} />
                  <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                    {singleFile ? singleFile.name : "Drop file or click to browse"}
                  </p>
                  {singleFile && (
                    <p style={{ margin: "2px 0 0", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                      {(singleFile.size / 1024).toFixed(1)} KB
                    </p>
                  )}
                  <input
                    id="sc-single-input"
                    type="file"
                    onChange={handleSingleFileInput}
                    style={{ display: "none" }}
                  />
                  {singleFile && (
                    <button
                      onClick={(e) => { e.stopPropagation(); setSingleFile(null); }}
                      style={{
                        position: "absolute", top: "8px", right: "8px",
                        background: "none", border: "none", color: "var(--text-tertiary)",
                        cursor: "pointer",
                      }}
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>

                {/* Column config */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)", marginTop: "var(--spacing-md)" }}>
                  <label style={labelStyle}>
                    Value Column
                    <input
                      type="text"
                      value={singleConfig.valueColumn}
                      onChange={(e) => setSingleConfig((c) => ({ ...c, valueColumn: e.target.value }))}
                      style={inputStyle}
                      placeholder="e.g. diversity_shannon"
                    />
                  </label>
                  <label style={labelStyle}>
                    Group Column
                    <input
                      type="text"
                      value={singleConfig.groupColumn}
                      onChange={(e) => setSingleConfig((c) => ({ ...c, groupColumn: e.target.value }))}
                      style={inputStyle}
                      placeholder="e.g. condition"
                    />
                  </label>
                </div>

                {/* Extra fields */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)", marginTop: "var(--spacing-md)" }}>
                  <label style={labelStyle}>Group Order<input type="text" value={singleGroupOrder} onChange={(e) => setSingleGroupOrder(e.target.value)} style={inputStyle} placeholder="e.g. Control,Treatment" /></label>
                  <label style={labelStyle}>Chart Title<input type="text" value={singleChartTitle} onChange={(e) => setSingleChartTitle(e.target.value)} style={inputStyle} placeholder="Optional" /></label>
                </div>
              </Card>
            )}

            {/* Multi File Tab */}
            {activeTab === "multi" && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <ListFilter size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Multi File
                </h4>

                {/* Files upload */}
                <div
                  onDrop={handleMultiFileDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => document.getElementById("sc-multi-input")?.click()}
                  style={dropZoneStyle}
                >
                  <Upload size={28} style={{ color: "var(--text-tertiary)", marginBottom: "var(--spacing-sm)" }} />
                  <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                    Drop files or click to browse
                  </p>
                  <input
                    id="sc-multi-input"
                    type="file"
                    multiple
                    onChange={handleMultiFileInput}
                    style={{ display: "none" }}
                  />
                </div>

                {/* File list */}
                {multiFiles.length > 0 && (
                  <div style={{ marginTop: "var(--spacing-md)", display: "flex", flexDirection: "column", gap: "var(--spacing-xs)" }}>
                    {multiFiles.map((f) => (
                      <div
                        key={f.name}
                        style={{
                          display: "flex", alignItems: "center", justifyContent: "space-between",
                          padding: "var(--spacing-sm) var(--spacing-md)",
                          background: "var(--bg-root)", borderRadius: "var(--radius-control)",
                          fontSize: "0.85rem",
                        }}
                      >
                        <span style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                          <FileUp size={14} style={{ color: "var(--text-tertiary)" }} />
                          {f.name}
                        </span>
                        <button onClick={() => removeMultiFile(f.name)} style={{
                          background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer",
                        }}>
                          <X size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Column config */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)", marginTop: "var(--spacing-md)" }}>
                  <label style={labelStyle}>
                    Value Column
                    <input
                      type="text"
                      value={multiConfig.valueColumn}
                      onChange={(e) => setMultiConfig((c) => ({ ...c, valueColumn: e.target.value }))}
                      style={inputStyle}
                      placeholder="e.g. diversity_shannon"
                    />
                  </label>
                  <label style={labelStyle}>
                    Group Column
                    <input
                      type="text"
                      value={multiConfig.groupColumn}
                      onChange={(e) => setMultiConfig((c) => ({ ...c, groupColumn: e.target.value }))}
                      style={inputStyle}
                      placeholder="e.g. condition"
                    />
                  </label>
                </div>

                {/* Extra multi-file params */}
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)", marginTop: "var(--spacing-md)" }}>
                  <label style={labelStyle}>Group Order<input type="text" value={multiGroupOrder} onChange={(e) => setMultiGroupOrder(e.target.value)} style={inputStyle} placeholder="e.g. Control,Treatment" /></label>
                  <label style={labelStyle}>Chart Title<input type="text" value={multiChartTitle} onChange={(e) => setMultiChartTitle(e.target.value)} style={inputStyle} placeholder="Optional" /></label>
                  <label style={labelStyle}>
                    P-value Correction
                    <select value={correctionMode} onChange={(e) => setCorrectionMode(e.target.value)} style={inputStyle}>
                      <option value="per_dataset">Per Dataset</option>
                      <option value="global">Global</option>
                    </select>
                  </label>
                </div>
              </Card>
            )}

            {/* Run button */}
            <button
              onClick={handleSubmit}
              disabled={!selectedProjectId || submitting}
              style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                gap: "var(--spacing-sm)", padding: "12px 28px", borderRadius: "var(--radius-pill)",
                background: selectedProjectId ? "var(--accent)" : "var(--bg-inset)",
                color: selectedProjectId ? "#fff" : "var(--text-tertiary)",
                fontWeight: 600, fontSize: "0.95rem", border: "none",
                cursor: selectedProjectId && !submitting ? "pointer" : "not-allowed",
                opacity: submitting ? 0.7 : 1, transition: "opacity var(--duration-fast)",
              }}
            >
              {submitting ? (
                <><RefreshCw size={16} style={{ animation: "spin 1s linear infinite" }} /> Running…</>
              ) : (
                <><Play size={16} /> Run Comparison</>
              )}
            </button>

            {submitError && <ErrorBanner message={submitError} />}
            {submitMessage && (
              <div style={{
                padding: "var(--spacing-md)", borderRadius: "var(--radius-panel)",
                background: "#34c75918", border: "1px solid #34c75930",
                color: "var(--success)", fontSize: "0.85rem", fontWeight: 500,
              }}>
                {submitMessage}
              </div>
            )}
          </div>

          {/* ── Right: Results ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
            {/* Statistical result tabs */}
            <Tabs tabs={STAT_TABLES} activeKey={activeStatTab} onChange={setActiveStatTab} />

            {resultLoading ? (
              <Card>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                  <Skeleton height="200px" />
                  <Skeleton height="100px" />
                  <Skeleton height="60px" />
                </div>
              </Card>
            ) : resultError ? (
              <div style={{
                padding: "var(--spacing-xl)", borderRadius: "var(--radius-panel)",
                background: "#ff3b3018", border: "1px solid #ff3b3030",
                color: "var(--danger)", display: "flex", alignItems: "center",
                gap: "var(--spacing-sm)",
              }}>
                <AlertTriangle size={18} /> {resultError}
              </div>
            ) : result ? (
              <Card>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                    <StatusBadge status={result.status} />
                    <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                      {result.job.module || "Statistical Result"}
                    </span>
                  </div>

                  {/* Content per active stat tab */}
                  {activeStatTab === "kruskal" && (
                    <div>
                      <h5 style={{ margin: "0 0 var(--spacing-sm)", fontSize: "0.9rem" }}>
                        Kruskal-Wallis Test
                      </h5>
                      {result.outputs && result.outputs.length > 0 ? (
                        <ResultViewer outputs={result.outputs} />
                      ) : (
                        <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", padding: "var(--spacing-lg)", textAlign: "center" }}>
                          No results available.
                        </p>
                      )}
                    </div>
                  )}

                  {activeStatTab === "dunn" && (
                    <div>
                      <h5 style={{ margin: "0 0 var(--spacing-sm)", fontSize: "0.9rem" }}>
                        Dunn's Post-hoc Test
                      </h5>
                      {result.outputs && result.outputs.length > 0 ? (
                        <ResultViewer outputs={result.outputs} />
                      ) : (
                        <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", padding: "var(--spacing-lg)", textAlign: "center" }}>
                          No results available. Run Kruskal-Wallis significance first.
                        </p>
                      )}
                    </div>
                  )}

                  {activeStatTab === "boxplot" && (
                    <div>
                      <h5 style={{ margin: "0 0 var(--spacing-sm)", fontSize: "0.9rem" }}>
                        Box Plot
                      </h5>
                      {result.outputs && result.outputs.length > 0 ? (
                        <ResultViewer outputs={result.outputs} />
                      ) : (
                        <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", padding: "var(--spacing-lg)", textAlign: "center" }}>
                          No plot image available. Ensure results include image output.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </Card>
            ) : (
              <EmptyState
                icon={BarChart3}
                title="No results"
                description="Configure input and click Run Comparison to start."
              />
            )}

            {/* Summary grid for multi-file */}
            {result && activeTab === "multi" && result.outputs.length > 0 && (
              <Card>
                <h5 style={{ margin: "0 0 var(--spacing-md)", fontSize: "0.9rem" }}>
                  <Table2 size={14} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Summary Grid
                </h5>
                <div style={{ overflow: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--separator)" }}>
                        <th style={{ textAlign: "left", padding: "8px", fontWeight: 600 }}>File</th>
                        <th style={{ textAlign: "right", padding: "8px", fontWeight: 600 }}>H-statistic</th>
                        <th style={{ textAlign: "right", padding: "8px", fontWeight: 600 }}>p-value</th>
                        <th style={{ textAlign: "right", padding: "8px", fontWeight: 600 }}>Significant</th>
                      </tr>
                    </thead>
                    <tbody>
                      {multiConfig.files.map((fname) => (
                        <tr key={fname} style={{ borderBottom: "1px solid var(--separator)" }}>
                          <td style={{ padding: "8px" }}>{fname}</td>
                          <td style={{ padding: "8px", textAlign: "right", color: "var(--text-secondary)" }}>—</td>
                          <td style={{ padding: "8px", textAlign: "right", color: "var(--text-secondary)" }}>—</td>
                          <td style={{ padding: "8px", textAlign: "right" }}><StatusBadge status="queued" /></td>
                        </tr>
                      ))}
                      {result && (
                        <tr>
                          <td colSpan={4} style={{ padding: "8px", textAlign: "center", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                            Results loaded — view in output panel for detailed statistics.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      padding: "var(--spacing-md) var(--spacing-lg)", borderRadius: "var(--radius-panel)",
      background: "#ff3b3018", border: "1px solid #ff3b3030",
      color: "var(--danger)", fontSize: "0.85rem", fontWeight: 500,
      display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
    }}>
      <AlertTriangle size={16} /> {message}
    </div>
  );
}

const dropZoneStyle: React.CSSProperties = {
  border: "2px dashed var(--separator)",
  borderRadius: "var(--radius-panel)",
  padding: "var(--spacing-2xl)",
  textAlign: "center",
  background: "var(--bg-root)",
  cursor: "pointer",
  position: "relative",
  transition: "border-color var(--duration-fast)",
};

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  fontSize: "0.75rem",
  fontWeight: 600,
  textTransform: "uppercase",
  color: "var(--text-secondary)",
};

const selectStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};
