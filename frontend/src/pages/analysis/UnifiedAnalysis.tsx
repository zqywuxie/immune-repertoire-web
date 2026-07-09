import { useState, useMemo, useCallback, type DragEvent, type ChangeEvent } from "react";
import {
  FlaskConical, Upload, Play, BarChart3, Table2, AlertTriangle,
  RefreshCw, FileUp, X, ListTree, FolderOpen, CheckCircle2,
} from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import { listProjects, listProjectAssets } from "../../shared/api/projects";
import { listJobModules, submitJob, getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import type { ProjectSummary, JobModule, ProjectAsset } from "../../shared/types/domain";
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

interface FieldMapping {
  file: string;
  column: string;
  role: string;
}

const RESULT_TABS = [
  { key: "charts", label: "Charts" },
  { key: "data", label: "Data" },
];

const FIELD_ROLES = ["cdr3_aa", "cdr3_nt", "v_gene", "j_gene", "count", "frequency", "sample_id", "group"];

const SCHEMES = [
  { key: "bcell_isotype", name: "B-Cell Isotype", desc: "Analyze 6 isotype expression ratios and CDR3 usage", fields: ["sample_id"] },
  { key: "shm_analysis", name: "SHM Analysis", desc: "Somatic hypermutation rate comparison", fields: ["sample_id"] },
  { key: "ig_metrics", name: "IG Metrics", desc: "Diversity metrics: D50, Gini, Shannon, Reads, UCDR3", fields: ["sample_id", "chain"] },
  { key: "sequencing_reads_chart", name: "Sequencing Reads", desc: "TCR/IG chain distribution bar charts", fields: ["sample_id"] },
  { key: "ig_other_isotype", name: "B-Cell Maturation", desc: "Class switch, naive mutated / unmutated %", fields: ["sample_id"] },
  { key: "custom_field_analysis", name: "Custom Fields", desc: "Generic analysis of user-selected numeric fields", fields: [] },
];

const CHAINS = ["IGH", "IGK", "IGL", "TRA", "TRB"];

/* ── Component ── */

export function UnifiedAnalysis() {
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedModule, setSelectedModule] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [fieldMappings, setFieldMappings] = useState<FieldMapping[]>([]);
  const [fileSource, setFileSource] = useState<"upload" | "existing">("upload");
  const [existingAssets, setExistingAssets] = useState<ProjectAsset[]>([]);
  const [selectedExistingFile, setSelectedExistingFile] = useState("");
  const [selectedScheme, setSelectedScheme] = useState("");
  const [selectedChains, setSelectedChains] = useState<string[]>([]);
  const [baselineSample, setBaselineSample] = useState("");
  const [chartWidth, setChartWidth] = useState(16);
  const [chartHeight, setChartHeight] = useState(10);
  const [showValues, setShowValues] = useState(true);
  const [activeResultTab, setActiveResultTab] = useState("charts");
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitMessage, setSubmitMessage] = useState("");
  const [resultState, setResultState] = useState<{
    result: JobResultsResponse | null;
    loading: boolean;
    error: string;
  }>({ result: null, loading: false, error: "" });

  const projects = useApi(() => listProjects(), []);
  const modules = useApi(() => listJobModules(), []);

  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const moduleList = modules.status === "ready" ? modules.data.modules : [];
  const projectsError = projects.status === "error" ? projects.error : null;
  const modulesError = modules.status === "error" ? modules.error : null;
  const loadingProjects = projects.status === "loading";
  const loadingModules = modules.status === "loading";

  // Load existing project assets when fileSource=existing
  const existingAssetsState = useApi(
    () => selectedProjectId && fileSource === "existing"
      ? listProjectAssets(selectedProjectId, { assetType: "profile", pageSize: 50 })
      : Promise.resolve({ assets: [] as ProjectAsset[] }),
    [selectedProjectId, fileSource]
  );

  const toggleChain = (ch: string) => {
    setSelectedChains(prev => prev.includes(ch) ? prev.filter(c => c !== ch) : [...prev, ch]);
  };

  const groupedModules = useMemo(() => {
    const map = new Map<string, JobModule[]>();
    for (const m of moduleList) {
      const cat = m.category || "Other";
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(m);
    }
    return [...map.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [moduleList]);

  const handleFilesAdded = useCallback((incoming: FileList | File[]) => {
    const entries: FileEntry[] = Array.from(incoming).map((f) => ({
      name: f.name,
      size: f.size,
      file: f,
    }));
    setFiles((prev) => [...prev, ...entries]);
  }, []);

  const handleRemoveFile = useCallback((name: string) => {
    setFiles((prev) => prev.filter((f) => f.name !== name));
    setFieldMappings((prev) => prev.filter((m) => m.file !== name));
  }, []);

  const handleDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files.length > 0) handleFilesAdded(e.dataTransfer.files);
  }, [handleFilesAdded]);

  const handleFileInput = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) handleFilesAdded(e.target.files);
  }, [handleFilesAdded]);

  const handleUpsertMapping = useCallback((file: string, column: string, role: string) => {
    setFieldMappings((prev) => {
      const existing = prev.findIndex((m) => m.file === file && m.role === role);
      if (existing >= 0) {
        const next = [...prev];
        next[existing] = { file, column, role };
        return next;
      }
      return [...prev, { file, column, role }];
    });
  }, []);

  const handleRemoveMapping = useCallback((file: string, role: string) => {
    setFieldMappings((prev) => prev.filter((m) => !(m.file === file && m.role === role)));
  }, []);

  const handleSubmit = async () => {
    if (!selectedProjectId || !selectedModule) return;
    setSubmitting(true);
    setSubmitError("");
    setSubmitMessage("");
    try {
      const payload: Record<string, unknown> = {
        project_id: selectedProjectId,
        module: selectedModule || selectedScheme,
        scheme: selectedScheme,
        chains: selectedChains,
        chart_config: { width: chartWidth, height: chartHeight, show_values: showValues },
        baseline_sample: baselineSample || undefined,
      };
      if (files.length > 0) payload.files = files.map((f) => f.name);
      if (selectedExistingFile) payload.file_id = selectedExistingFile;
      if (fieldMappings.length > 0) payload.field_mappings = fieldMappings;
      const res = await submitJob({
        module: selectedModule,
        payload,
        projectId: selectedProjectId,
      });
      setJobId(res.job_id);
      setSubmitMessage(
        res.reused_result
          ? `Reused cached result ${res.result_id || res.job_id}.`
          : `Submitted job ${res.job_id}.`
      );
      if (res.job_id) {
        setResultState({ result: null, loading: true, error: "" });
        try {
          const jobResult = await getJobResults(res.job_id);
          setResultState({ result: jobResult, loading: false, error: "" });
        } catch {
          setResultState({ result: null, loading: false, error: "Failed to load results" });
        }
      }
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Submission failed");
      setResultState({ result: null, loading: false, error: "" });
    } finally {
      setSubmitting(false);
    }
  };

  const noProjects = projects.status === "ready" && projectList.length === 0;

  return (
    <>
      <PageHeader title="Unified Analysis" subtitle="Select scheme, upload files, map fields, and run" />

      {/* Error banners */}
      {projectsError && <ErrorBanner message={projectsError} />}
      {modulesError && <ErrorBanner message={modulesError} />}

      {noProjects ? (
        <EmptyState
          icon={FlaskConical}
          title="No projects available"
          description="Create a project from the Dashboard before running analysis."
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
          {/* ── Left Column: Configuration ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
            {/* Project & Module selectors */}
            <Card>
              <h4 style={{ margin: "0 0 var(--spacing-md)" }}>Scheme Selection</h4>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
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
                <label style={labelStyle}>
                  Analysis Scheme
                  {loadingModules ? (
                    <Skeleton height="38px" />
                  ) : (
                    <select
                      value={selectedModule}
                      onChange={(e) => setSelectedModule(e.target.value)}
                      style={selectStyle}
                    >
                      <option value="">Select a scheme…</option>
                      {groupedModules.map(([cat, mods]) => (
                        <optgroup key={cat} label={cat}>
                          {mods.map((m) => (
                            <option key={m.key} value={m.key}>{m.label}</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  )}
                </label>
              </div>
            </Card>

            {/* File Upload */}
            <Card>
              <h4 style={{ margin: "0 0 var(--spacing-md)" }}>Data Source</h4>
              {/* File source toggle */}
              <div style={{ display: "flex", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-md)" }}>
                <button onClick={() => setFileSource("upload")} style={{
                  flex: 1, padding: "6px 12px", borderRadius: "var(--radius-pill)",
                  border: fileSource === "upload" ? "2px solid var(--accent)" : "1px solid var(--separator)",
                  background: fileSource === "upload" ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent",
                  color: fileSource === "upload" ? "var(--accent)" : "var(--text-secondary)",
                  fontWeight: 500, fontSize: "0.82rem", cursor: "pointer",
                }}><Upload size={14} /> Upload New File</button>
                <button onClick={() => setFileSource("existing")} style={{
                  flex: 1, padding: "6px 12px", borderRadius: "var(--radius-pill)",
                  border: fileSource === "existing" ? "2px solid var(--accent)" : "1px solid var(--separator)",
                  background: fileSource === "existing" ? "color-mix(in srgb, var(--accent) 10%, transparent)" : "transparent",
                  color: fileSource === "existing" ? "var(--accent)" : "var(--text-secondary)",
                  fontWeight: 500, fontSize: "0.82rem", cursor: "pointer",
                }}><FolderOpen size={14} /> Select Existing File</button>
              </div>

              {fileSource === "upload" ? (
                <>
                  <div
                    onDrop={handleDrop}
                    onDragOver={(e) => e.preventDefault()}
                    style={{
                      border: "2px dashed var(--separator)",
                      borderRadius: "var(--radius-panel)",
                      padding: "var(--spacing-2xl)",
                      textAlign: "center",
                      background: "var(--bg-root)",
                      cursor: "pointer",
                    }}
                    onClick={() => document.getElementById("ua-file-input")?.click()}
                  >
                    <Upload size={32} style={{ color: "var(--text-tertiary)", marginBottom: "var(--spacing-sm)" }} />
                    <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                      Drag & drop files here or click to browse
                    </p>
                    <input id="ua-file-input" type="file" multiple onChange={handleFileInput} style={{ display: "none" }} />
                  </div>
                  {files.length > 0 && (
                    <div style={{ marginTop: "var(--spacing-md)", display: "flex", flexDirection: "column", gap: "var(--spacing-xs)" }}>
                      {files.map((f) => (
                        <div key={f.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "var(--spacing-sm) var(--spacing-md)", background: "var(--bg-root)", borderRadius: "var(--radius-control)", fontSize: "0.85rem" }}>
                          <span style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                            <FileUp size={14} style={{ color: "var(--text-tertiary)" }} /> {f.name}
                            <span style={{ color: "var(--text-tertiary)", fontSize: "0.75rem" }}>{(f.size / 1024).toFixed(1)} KB</span>
                          </span>
                          <button onClick={() => handleRemoveFile(f.name)} style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", padding: "2px" }} aria-label={`Remove ${f.name}`}><X size={14} /></button>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <div>
                  {!selectedProjectId ? (
                    <p style={{ color: "var(--text-tertiary)", fontSize: "0.82rem", textAlign: "center", padding: "var(--spacing-md)" }}>Select a project first to browse files.</p>
                  ) : existingAssetsState.status === "loading" ? (
                    <Skeleton height="100px" />
                  ) : existingAssetsState.status === "ready" && existingAssetsState.data.assets.length === 0 ? (
                    <p style={{ color: "var(--text-tertiary)", fontSize: "0.82rem", textAlign: "center", padding: "var(--spacing-md)" }}>No profile assets found in this project.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xs)", maxHeight: "180px", overflow: "auto" }}>
                      {(existingAssetsState.status === "ready" ? existingAssetsState.data.assets : []).map((a: ProjectAsset) => (
                        <button key={a.id} onClick={() => setSelectedExistingFile(a.id)} style={{
                          textAlign: "left", padding: "var(--spacing-sm) var(--spacing-md)",
                          borderRadius: "var(--radius-control)", border: selectedExistingFile === a.id ? "1px solid var(--accent)" : "1px solid var(--separator)",
                          background: selectedExistingFile === a.id ? "color-mix(in srgb, var(--accent) 8%, transparent)" : "var(--bg-root)",
                          cursor: "pointer", display: "flex", alignItems: "center", gap: "var(--spacing-sm)", fontSize: "0.82rem",
                        }}>
                          <FileUp size={14} style={{ color: "var(--text-tertiary)" }} />
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{a.original_name}</span>
                          {selectedExistingFile === a.id && <CheckCircle2 size={14} style={{ color: "var(--accent)", marginLeft: "auto", flexShrink: 0 }} />}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </Card>

            {/* Scheme Selector */}
            <Card>
              <h4 style={{ margin: "0 0 var(--spacing-md)" }}>Analysis Scheme</h4>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "var(--spacing-sm)" }}>
                {SCHEMES.map((s) => (
                  <button key={s.key} onClick={() => setSelectedScheme(s.key)} style={{
                    textAlign: "left", padding: "var(--spacing-md)",
                    borderRadius: "var(--radius-control)", cursor: "pointer",
                    border: selectedScheme === s.key ? "2px solid var(--accent)" : "1px solid var(--separator)",
                    background: selectedScheme === s.key ? "color-mix(in srgb, var(--accent) 8%, transparent)" : "var(--bg-root)",
                    display: "flex", flexDirection: "column", gap: "4px",
                  }}>
                    <span style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--text-primary)" }}>{s.name}</span>
                    <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", lineHeight: 1.3 }}>{s.desc}</span>
                    <span style={{ fontSize: "0.68rem", color: "var(--text-tertiary)", marginTop: "2px" }}>
                      Fields: {s.fields.length > 0 ? s.fields.join(", ") : "any"}
                    </span>
                  </button>
                ))}
              </div>
            </Card>

            {/* Parameter Config */}
            {selectedScheme && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>Parameters</h4>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                  <div>
                    <span style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)", display: "block", marginBottom: "var(--spacing-xs)" }}>Chain Types</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)" }}>
                      {CHAINS.map((ch) => (
                        <button key={ch} onClick={() => toggleChain(ch)} style={{
                          padding: "4px 12px", borderRadius: "var(--radius-pill)", fontSize: "0.78rem", fontWeight: 500, cursor: "pointer",
                          border: selectedChains.includes(ch) ? "1px solid var(--accent)" : "1px solid var(--separator)",
                          background: selectedChains.includes(ch) ? "var(--accent)" : "transparent",
                          color: selectedChains.includes(ch) ? "#fff" : "var(--text-secondary)",
                        }}>{ch}</button>
                      ))}
                    </div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--spacing-md)" }}>
                    <label style={labelStyle}>Chart Width (in)<input type="number" value={chartWidth} onChange={(e) => setChartWidth(Number(e.target.value))} className="input" min={5} max={30} /></label>
                    <label style={labelStyle}>Chart Height (in)<input type="number" value={chartHeight} onChange={(e) => setChartHeight(Number(e.target.value))} className="input" min={5} max={30} /></label>
                  </div>
                  <label style={labelStyle}>Baseline Sample<input type="text" value={baselineSample} onChange={(e) => setBaselineSample(e.target.value)} className="input" placeholder="Optional — sample name for baseline comparison" /></label>
                  <label style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", fontSize: "0.85rem", cursor: "pointer" }}>
                    <input type="checkbox" checked={showValues} onChange={(e) => setShowValues(e.target.checked)} /> Show values on charts
                  </label>
                </div>
              </Card>
            )}

            {/* Field Mapping */}
            {files.length > 0 && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <ListTree size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Field Mapping
                </h4>
                {files.map((f) => (
                  <div key={f.name} style={{ marginBottom: "var(--spacing-md)" }}>
                    <p style={{ fontWeight: 600, fontSize: "0.82rem", margin: "0 0 var(--spacing-sm)", color: "var(--text-secondary)" }}>
                      {f.name}
                    </p>
                    {FIELD_ROLES.map((role) => {
                      const mapping = fieldMappings.find((m) => m.file === f.name && m.role === role);
                      return (
                        <div
                          key={role}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "var(--spacing-sm)",
                            marginBottom: "var(--spacing-xs)",
                            fontSize: "0.82rem",
                          }}
                        >
                          <span style={{ width: "100px", flexShrink: 0, color: "var(--text-secondary)" }}>
                            {role}:
                          </span>
                          <input
                            type="text"
                            placeholder="Column name"
                            value={mapping?.column || ""}
                            onChange={(e) =>
                              handleUpsertMapping(f.name, e.target.value, role)
                            }
                            style={{
                              flex: 1,
                              padding: "6px 10px",
                              borderRadius: "var(--radius-control)",
                              border: "1px solid var(--separator)",
                              background: "var(--bg-elevated)",
                              color: "var(--text-primary)",
                              fontSize: "0.82rem",
                            }}
                          />
                          {mapping && (
                            <button
                              onClick={() => handleRemoveMapping(f.name, role)}
                              style={{
                                background: "none",
                                border: "none",
                                color: "var(--text-tertiary)",
                                cursor: "pointer",
                                padding: "2px",
                              }}
                              aria-label={`Remove mapping for ${role}`}
                            >
                              <X size={12} />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </Card>
            )}

            {/* Run Button */}
            <button
              onClick={handleSubmit}
              disabled={!selectedProjectId || !selectedModule || submitting}
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "var(--spacing-sm)",
                padding: "12px 28px",
                borderRadius: "var(--radius-pill)",
                background: selectedProjectId && selectedModule ? "var(--accent)" : "var(--bg-inset)",
                color: selectedProjectId && selectedModule ? "#fff" : "var(--text-tertiary)",
                fontWeight: 600,
                fontSize: "0.95rem",
                border: "none",
                cursor: selectedProjectId && selectedModule && !submitting ? "pointer" : "not-allowed",
                opacity: submitting ? 0.7 : 1,
                transition: "opacity var(--duration-fast)",
              }}
            >
              {submitting ? (
                <><RefreshCw size={16} style={{ animation: "spin 1s linear infinite" }} /> Submitting…</>
              ) : (
                <><Play size={16} /> Run Analysis</>
              )}
            </button>

            {submitError && <ErrorBanner message={submitError} />}
            {submitMessage && (
              <div style={{
                padding: "var(--spacing-md)",
                borderRadius: "var(--radius-panel)",
                background: "#34c75918",
                color: "var(--success)",
                fontSize: "0.85rem",
                fontWeight: 500,
                border: "1px solid #34c75930",
              }}>
                {submitMessage}
              </div>
            )}
          </div>

          {/* ── Right Column: Results ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
            {/* Tabs */}
            <Tabs tabs={RESULT_TABS} activeKey={activeResultTab} onChange={setActiveResultTab} />

            {/* Charts Tab */}
            {activeResultTab === "charts" && (
              <ResultsContent
                state={resultState}
                jobId={jobId}
                emptyLabel="Submit a job to view charts."
              />
            )}

            {/* Data Tab */}
            {activeResultTab === "data" && (
              <ResultsContent
                state={resultState}
                jobId={jobId}
                emptyLabel="Submit a job to view raw data."
                showData
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}

/* ── Sub-components ── */

function ResultsContent({
  state,
  jobId,
  emptyLabel,
  showData = false,
}: {
  state: { result: JobResultsResponse | null; loading: boolean; error: string };
  jobId: string | null;
  emptyLabel: string;
  showData?: boolean;
}) {
  if (!jobId) {
    return (
      <EmptyState
        icon={showData ? Table2 : BarChart3}
        title="No results yet"
        description={emptyLabel}
      />
    );
  }

  if (state.loading) {
    return (
      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          <Skeleton height="200px" />
          <Skeleton height="100px" />
          <Skeleton height="60px" />
        </div>
      </Card>
    );
  }

  if (state.error) {
    return (
      <div style={{
        padding: "var(--spacing-xl)",
        borderRadius: "var(--radius-panel)",
        background: "#ff3b3018",
        border: "1px solid #ff3b3030",
        color: "var(--danger)",
        display: "flex",
        alignItems: "center",
        gap: "var(--spacing-sm)",
      }}>
        <AlertTriangle size={18} />
        {state.error}
      </div>
    );
  }

  if (!state.result) {
    return (
      <div style={{ color: "var(--text-tertiary)", textAlign: "center", padding: "var(--spacing-xl)" }}>
        No results loaded.
      </div>
    );
  }

  const { result: res } = state;

  if (showData) {
    return (
      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
            <StatusBadge status={res.status} />
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              {res.job.module || "Job Result"}
            </span>
          </div>
          {res.outputs && res.outputs.length > 0 ? (
            <ResultViewer outputs={res.outputs} />
          ) : (
            <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
              No data outputs available.
            </p>
          )}
          {/* JSON result dump */}
          <details style={{ fontSize: "0.82rem" }}>
            <summary style={{ cursor: "pointer", color: "var(--accent)", fontWeight: 500 }}>
              Raw Result JSON
            </summary>
            <pre style={{
              maxHeight: "300px",
              overflow: "auto",
              background: "var(--bg-root)",
              padding: "var(--spacing-md)",
              borderRadius: "var(--radius-sm)",
              fontSize: "0.75rem",
              marginTop: "var(--spacing-sm)",
              fontFamily: '"Cascadia Code", "Consolas", monospace',
            }}>
              {JSON.stringify(res.result, null, 2)}
            </pre>
          </details>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
          <StatusBadge status={res.status} />
          <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            {res.job.module || "Job Result"}
          </span>
        </div>
        {res.outputs && res.outputs.length > 0 ? (
          <ResultViewer outputs={res.outputs} />
        ) : (
          <p style={{ color: "var(--text-tertiary)", fontSize: "0.85rem", textAlign: "center", padding: "var(--spacing-xl)" }}>
            No chart outputs available.
          </p>
        )}
        {res.assets.length > 0 && (
          <div>
            <p style={{ fontWeight: 600, fontSize: "0.78rem", color: "var(--text-secondary)", marginBottom: "var(--spacing-sm)" }}>
              Assets
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
              {res.assets.map((a) => (
                <span key={a.id} style={{
                  padding: "4px 12px",
                  borderRadius: "var(--radius-pill)",
                  background: "var(--bg-root)",
                  fontSize: "0.78rem",
                  border: "1px solid var(--separator)",
                }}>
                  {a.original_name}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div style={{
      padding: "var(--spacing-md) var(--spacing-lg)",
      borderRadius: "var(--radius-panel)",
      background: "#ff3b3018",
      border: "1px solid #ff3b3030",
      color: "var(--danger)",
      fontSize: "0.85rem",
      fontWeight: 500,
      display: "flex",
      alignItems: "center",
      gap: "var(--spacing-sm)",
    }}>
      <AlertTriangle size={16} />
      {message}
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

const selectStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};
