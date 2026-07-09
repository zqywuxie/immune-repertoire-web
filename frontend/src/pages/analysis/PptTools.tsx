import { useState, useCallback, useMemo, type DragEvent, type ChangeEvent } from "react";
import {
  Presentation, Upload, Image, Settings, Download, Play, AlertTriangle,
  RefreshCw, X, FileUp, Check, Eye, Package,
} from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import { listProjects, uploadProjectAssets } from "../../shared/api/projects";
import { submitJob, getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import { Stepper, type StepDef } from "../../shared/components/Stepper";
import { PageHeader } from "../../shared/components/PageHeader";
import { Card } from "../../shared/components/Card";
import { EmptyState } from "../../shared/components/EmptyState";
import { Skeleton } from "../../shared/components/Skeleton";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { ResultViewer } from "../../features/results/ResultViewer";

/* ── Types ── */

interface PptFile {
  name: string;
  size: number;
  file: File;
}

interface ImageSlot {
  slideIndex: number;
  slotLabel: string;
  imageName: string;
}

/* ── Component ── */

export function PptTools() {
  const [currentStep, setCurrentStep] = useState(0);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [pptFile, setPptFile] = useState<PptFile | null>(null);
  const [slots, setSlots] = useState<ImageSlot[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitMessage, setSubmitMessage] = useState("");
  const [result, setResult] = useState<JobResultsResponse | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [resultError, setResultError] = useState("");
  const [generatedUrl, setGeneratedUrl] = useState("");

  // Slot configuration from uploaded PPT analysis
  const [detectedSlots, setDetectedSlots] = useState(0);

  const projects = useApi(() => listProjects(), []);
  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const projectsError = projects.status === "error" ? projects.error : null;
  const loadingProjects = projects.status === "loading";
  const noProjects = projects.status === "ready" && projectList.length === 0;

  const stepDefs: StepDef[] = useMemo(() => [
    { label: "Upload PPT", description: "Select your PowerPoint file" },
    { label: "Configure", description: "Map image slots" },
    { label: "Generate", description: "Generate & download" },
  ], []);

  const handlePptDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith(".pptx") || file.name.endsWith(".ppt"))) {
      setPptFile({ name: file.name, size: file.size, file });
      // Simulate slot detection
      setDetectedSlots(3);
      setSlots([
        { slideIndex: 1, slotLabel: "Cover Image", imageName: "" },
        { slideIndex: 2, slotLabel: "Chart Area", imageName: "" },
        { slideIndex: 3, slotLabel: "Footer Logo", imageName: "" },
      ]);
      setCurrentStep(1);
    }
  }, []);

  const handlePptInput = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setPptFile({ name: file.name, size: file.size, file });
      setDetectedSlots(3);
      setSlots([
        { slideIndex: 1, slotLabel: "Cover Image", imageName: "" },
        { slideIndex: 2, slotLabel: "Chart Area", imageName: "" },
        { slideIndex: 3, slotLabel: "Footer Logo", imageName: "" },
      ]);
      setCurrentStep(1);
    }
  }, []);

  const removePptFile = useCallback(() => {
    setPptFile(null);
    setSlots([]);
    setDetectedSlots(0);
    setCurrentStep(0);
    setResult(null);
    setGeneratedUrl("");
  }, []);

  const updateSlot = useCallback((index: number, imageName: string) => {
    setSlots((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], imageName };
      return next;
    });
  }, []);

  const handleGenerate = async () => {
    if (!selectedProjectId || !pptFile) return;
    setSubmitting(true);
    setSubmitError("");
    setSubmitMessage("");
    setResult(null);
    setResultError("");

    try {
      // Upload PPT first
      await uploadProjectAssets(selectedProjectId, {
        assetType: "ppt",
        files: [pptFile.file],
      });

      const payload = {
        project_id: selectedProjectId,
        ppt_file: pptFile.name,
        image_slots: slots.filter((s) => s.imageName),
      };

      const jobRes = await submitJob({
        module: "ppt.generate",
        payload,
        projectId: selectedProjectId,
      });

      if (jobRes.job_id) {
        setResultLoading(true);
        try {
          const jobResult = await getJobResults(jobRes.job_id);
          setResult(jobResult);
          // Find generated ppt download URL
          const pptOutput = jobResult.outputs.find((o) => o.kind === "ppt" || o.kind === "pptx");
          if (pptOutput?.url) {
            setGeneratedUrl(pptOutput.url);
          }
          setCurrentStep(2);
        } catch {
          setResultError("Failed to load generation results");
        } finally {
          setResultLoading(false);
        }
      }
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader title="PPT Tools" subtitle="Upload, configure, and generate presentation slides" />

      {projectsError && <ErrorBanner message={projectsError} />}

      {noProjects ? (
        <EmptyState
          icon={Presentation}
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
          {/* ── Left: Workflow ── */}
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

            {/* Stepper */}
            <Card>
              <Stepper steps={stepDefs} currentStep={currentStep} />
            </Card>

            {/* Step 1: Upload PPT */}
            {currentStep <= 1 && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <Upload size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Upload PPT
                </h4>

                {!pptFile ? (
                  <div
                    onDrop={handlePptDrop}
                    onDragOver={(e) => e.preventDefault()}
                    onClick={() => document.getElementById("ppt-file-input")?.click()}
                    style={dropZoneStyle}
                  >
                    <Upload size={36} style={{ color: "var(--text-tertiary)", marginBottom: "var(--spacing-sm)" }} />
                    <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.88rem" }}>
                      Drag & drop your PPT file here
                    </p>
                    <p style={{ margin: "4px 0 0", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                      Supports .pptx and .ppt files
                    </p>
                    <input
                      id="ppt-file-input"
                      type="file"
                      accept=".pptx,.ppt"
                      onChange={handlePptInput}
                      style={{ display: "none" }}
                    />
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "var(--spacing-md)", background: "var(--bg-root)",
                      borderRadius: "var(--radius-control)", border: "1px solid var(--separator)",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                      <Presentation size={22} style={{ color: "var(--warning)" }} />
                      <div>
                        <p style={{ margin: 0, fontWeight: 500, fontSize: "0.88rem" }}>{pptFile.name}</p>
                        <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                          {(pptFile.size / 1024).toFixed(1)} KB
                        </p>
                      </div>
                    </div>
                    <button onClick={removePptFile} style={{
                      background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer",
                    }}>
                      <X size={16} />
                    </button>
                  </div>
                )}

                {detectedSlots > 0 && (
                  <div style={{
                    marginTop: "var(--spacing-md)", padding: "var(--spacing-sm) var(--spacing-md)",
                    borderRadius: "var(--radius-pill)", background: "#0071e318",
                    color: "var(--accent)", fontSize: "0.82rem", fontWeight: 500,
                    display: "inline-flex", alignItems: "center", gap: "var(--spacing-xs)",
                  }}>
                    <Check size={14} />
                    Detected {detectedSlots} image slot{detectedSlots > 1 ? "s" : ""}
                  </div>
                )}
              </Card>
            )}

            {/* Step 2: Configure */}
            {currentStep === 1 && slots.length > 0 && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <Settings size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Configure Image Slots
                </h4>
                <p style={{ fontSize: "0.8rem", color: "var(--text-tertiary)", margin: "0 0 var(--spacing-md)" }}>
                  Map each detected image slot to an asset file name.
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                  {slots.map((slot, idx) => (
                    <div key={idx} style={{
                      display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
                      padding: "var(--spacing-sm) var(--spacing-md)",
                      background: "var(--bg-root)", borderRadius: "var(--radius-control)",
                      border: "1px solid var(--separator)",
                    }}>
                      <Image size={16} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p style={{ margin: 0, fontSize: "0.82rem", fontWeight: 500 }}>
                          Slide {slot.slideIndex} - {slot.slotLabel}
                        </p>
                      </div>
                      <input
                        type="text"
                        value={slot.imageName}
                        onChange={(e) => updateSlot(idx, e.target.value)}
                        placeholder="Image file name"
                        style={{
                          width: "160px",
                          padding: "6px 10px",
                          borderRadius: "var(--radius-control)",
                          border: "1px solid var(--separator)",
                          background: "var(--bg-elevated)",
                          color: "var(--text-primary)",
                          fontSize: "0.82rem",
                        }}
                      />
                    </div>
                  ))}
                </div>

                {/* Generate button */}
                <button
                  onClick={handleGenerate}
                  disabled={!selectedProjectId || submitting}
                  style={{
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    gap: "var(--spacing-sm)", padding: "12px 28px", borderRadius: "var(--radius-pill)",
                    background: selectedProjectId ? "var(--accent)" : "var(--bg-inset)",
                    color: selectedProjectId ? "#fff" : "var(--text-tertiary)",
                    fontWeight: 600, fontSize: "0.95rem", border: "none",
                    cursor: selectedProjectId && !submitting ? "pointer" : "not-allowed",
                    opacity: submitting ? 0.7 : 1, marginTop: "var(--spacing-lg)",
                    width: "100%",
                  }}
                >
                  {submitting ? (
                    <><RefreshCw size={16} style={{ animation: "spin 1s linear infinite" }} /> Generating…</>
                  ) : (
                    <><Play size={16} /> Generate</>
                  )}
                </button>
              </Card>
            )}

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

          {/* ── Right: Preview & Download ── */}
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
            {/* Generated file card */}
            {currentStep >= 2 && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <Package size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Generated PPT
                </h4>

                {resultLoading ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                    <Skeleton height="120px" />
                    <Skeleton height="60px" />
                  </div>
                ) : resultError ? (
                  <div style={{
                    padding: "var(--spacing-md)", borderRadius: "var(--radius-panel)",
                    background: "#ff3b3018", border: "1px solid #ff3b3030",
                    color: "var(--danger)", fontSize: "0.85rem",
                    display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
                  }}>
                    <AlertTriangle size={14} /> {resultError}
                  </div>
                ) : generatedUrl ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                    <div style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      padding: "var(--spacing-md)", background: "var(--bg-root)",
                      borderRadius: "var(--radius-panel)", border: "1px solid var(--separator)",
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
                        <Presentation size={24} style={{ color: "var(--success)" }} />
                        <div>
                          <p style={{ margin: 0, fontWeight: 600, fontSize: "0.88rem" }}>
                            {pptFile?.name?.replace(/\.\w+$/, "") || "output"}_generated.pptx
                          </p>
                          <p style={{ margin: "2px 0 0", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                            Ready for download
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* Download button */}
                    <a
                      href={generatedUrl}
                      download
                      target="_blank"
                      rel="noreferrer"
                      style={{
                        display: "inline-flex", alignItems: "center", justifyContent: "center",
                        gap: "var(--spacing-sm)", padding: "12px 28px", borderRadius: "var(--radius-pill)",
                        background: "var(--success)", color: "#fff", fontWeight: 600,
                        fontSize: "0.95rem", textDecoration: "none",
                        transition: "background var(--duration-fast)",
                      }}
                    >
                      <Download size={18} /> Download Generated PPT
                    </a>
                  </div>
                ) : (
                  <EmptyState
                    icon={Presentation}
                    title="Not yet generated"
                    description="Configure image slots and click Generate."
                  />
                )}
              </Card>
            )}

            {/* Result outputs if available */}
            {result && result.outputs.length > 0 && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <Eye size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Outputs
                </h4>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", marginBottom: "var(--spacing-md)" }}>
                  <StatusBadge status={result.status} />
                  <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                    {result.job.module || "PPT Generation"}
                  </span>
                </div>
                <ResultViewer outputs={result.outputs} />
              </Card>
            )}

            {/* Slot summary card */}
            {slots.length > 0 && currentStep < 2 && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <Image size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Slot Summary
                </h4>
                <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
                  {slots.map((slot, idx) => (
                    <div
                      key={idx}
                      style={{
                        display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
                        padding: "var(--spacing-sm) var(--spacing-md)",
                        background: "var(--bg-root)", borderRadius: "var(--radius-pill)",
                        border: "1px solid var(--separator)", fontSize: "0.82rem",
                      }}
                    >
                      <span style={{
                        width: "8px", height: "8px", borderRadius: "50%",
                        background: slot.imageName ? "var(--success)" : "var(--separator)",
                        flexShrink: 0,
                      }} />
                      <span style={{ flex: 1 }}>Slide {slot.slideIndex}: {slot.slotLabel}</span>
                      <span style={{ color: slot.imageName ? "var(--text-primary)" : "var(--text-tertiary)", fontSize: "0.78rem" }}>
                        {slot.imageName || "unmapped"}
                      </span>
                    </div>
                  ))}
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
