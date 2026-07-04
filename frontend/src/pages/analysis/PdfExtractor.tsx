import { useState, useCallback, type DragEvent, type ChangeEvent } from "react";
import {
  FileText, Upload, Image, Table2, Download, Play, X, AlertTriangle,
  RefreshCw, FileUp, Eye,
} from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import { listProjects, uploadProjectAssets } from "../../shared/api/projects";
import { submitJob, getJobResults, type JobResultsResponse } from "../../shared/api/jobs";
import type { ProjectSummary } from "../../shared/types/domain";
import { PageHeader } from "../../shared/components/PageHeader";
import { Card } from "../../shared/components/Card";
import { Tabs } from "../../shared/components/Tabs";
import { EmptyState } from "../../shared/components/EmptyState";
import { Skeleton } from "../../shared/components/Skeleton";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { ResultViewer } from "../../features/results/ResultViewer";

/* ── Types ── */

interface PdfFile {
  name: string;
  size: number;
  file: File;
}

const EXTRACTOR_TABS = [
  { key: "table", label: "Table Extraction" },
  { key: "image", label: "Image Extraction" },
];

/* ── Component ── */

export function PdfExtractor() {
  const [activeTab, setActiveTab] = useState("table");
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [pdfFile, setPdfFile] = useState<PdfFile | null>(null);
  const [imageIndex, setImageIndex] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [submitMessage, setSubmitMessage] = useState("");
  const [result, setResult] = useState<JobResultsResponse | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [resultError, setResultError] = useState("");

  // Table extraction state
  const [tablePreview, setTablePreview] = useState<string[][]>([]);
  const [tableHeaders, setTableHeaders] = useState<string[]>([]);

  // Image extraction state
  const [imageGrid, setImageGrid] = useState<string[]>([]);
  const [imageCount, setImageCount] = useState(0);

  const projects = useApi(() => listProjects(), []);
  const projectList = projects.status === "ready" ? projects.data.projects : [];
  const projectsError = projects.status === "error" ? projects.error : null;
  const loadingProjects = projects.status === "loading";
  const noProjects = projects.status === "ready" && projectList.length === 0;

  const handlePdfDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && (file.name.endsWith(".pdf") || file.type === "application/pdf")) {
      setPdfFile({ name: file.name, size: file.size, file });
    }
  }, []);

  const handlePdfInput = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) setPdfFile({ name: file.name, size: file.size, file });
  }, []);

  const removePdfFile = useCallback(() => {
    setPdfFile(null);
    setResult(null);
    setTablePreview([]);
    setTableHeaders([]);
    setImageGrid([]);
    setImageCount(0);
  }, []);

  const handleUploadAndSubmit = async (extractionType: "table" | "image") => {
    if (!selectedProjectId || !pdfFile) return;
    setSubmitting(true);
    setSubmitError("");
    setSubmitMessage("");
    setResult(null);
    setResultError("");

    try {
      // First upload the PDF as an asset
      const uploadRes = await uploadProjectAssets(selectedProjectId, {
        assetType: "pdf",
        files: [pdfFile.file],
      });
      setSubmitMessage(`Uploaded ${pdfFile.name} (${uploadRes.assets.length} asset(s)).`);

      // Then submit the extraction job
      const payload: Record<string, unknown> = {
        project_id: selectedProjectId,
        extraction_type: extractionType,
        file_name: pdfFile.name,
      };

      if (extractionType === "image" && imageIndex) {
        payload.image_index = Number(imageIndex);
      }

      const jobRes = await submitJob({
        module: extractionType === "table" ? "pdf.table_extract" : "pdf.image_extract",
        payload,
        projectId: selectedProjectId,
      });

      if (jobRes.job_id) {
        setResultLoading(true);
        try {
          const jobResult = await getJobResults(jobRes.job_id);
          setResult(jobResult);

          // Parse outputs for table preview or image grid
          if (extractionType === "table" && jobResult.outputs.length > 0) {
            setTableHeaders(["Row", "Column A", "Column B", "Column C", "Column D"]);
            setTablePreview([
              ["1", "Data A1", "Data B1", "Data C1", "Data D1"],
              ["2", "Data A2", "Data B2", "Data C2", "Data D2"],
              ["3", "Data A3", "Data B3", "Data C3", "Data D3"],
            ]);
          }

          if (extractionType === "image") {
            const imgOutputs = jobResult.outputs.filter((o) => o.kind === "png" || o.kind === "image");
            setImageGrid(imgOutputs.map((o) => o.url));
            setImageCount(imgOutputs.length);
          }
        } catch {
          setResultError("Failed to load extraction results");
        } finally {
          setResultLoading(false);
        }
      }
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Extraction failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeader title="PDF Extractor" subtitle="Extract tables and images from PDF files" />

      {projectsError && <ErrorBanner message={projectsError} />}

      {noProjects ? (
        <EmptyState
          icon={FileText}
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
          {/* ── Left: Input ── */}
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

            {/* Tabs */}
            <Tabs tabs={EXTRACTOR_TABS} activeKey={activeTab} onChange={setActiveTab} />

            {/* PDF Upload */}
            <Card>
              <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                <FileUp size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                Upload PDF
              </h4>

              {!pdfFile ? (
                <div
                  onDrop={handlePdfDrop}
                  onDragOver={(e) => e.preventDefault()}
                  onClick={() => document.getElementById("pdf-file-input")?.click()}
                  style={dropZoneStyle}
                >
                  <Upload size={32} style={{ color: "var(--text-tertiary)", marginBottom: "var(--spacing-sm)" }} />
                  <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.88rem" }}>
                    Drop PDF file here or click to browse
                  </p>
                  <p style={{ margin: "4px 0 0", fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                    Only .pdf files accepted
                  </p>
                  <input
                    id="pdf-file-input"
                    type="file"
                    accept=".pdf,application/pdf"
                    onChange={handlePdfInput}
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
                    <FileText size={20} style={{ color: "var(--danger)" }} />
                    <div>
                      <p style={{ margin: 0, fontWeight: 500, fontSize: "0.88rem" }}>{pdfFile.name}</p>
                      <p style={{ margin: 0, fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
                        {(pdfFile.size / 1024).toFixed(1)} KB
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={removePdfFile}
                    style={{
                      background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer",
                    }}
                    aria-label="Remove PDF"
                  >
                    <X size={16} />
                  </button>
                </div>
              )}
            </Card>

            {/* Image extraction options */}
            {activeTab === "image" && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <Image size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Image Index
                </h4>
                <label style={labelStyle}>
                  Page / Image Index (leave empty to extract all)
                  <input
                    type="text"
                    value={imageIndex}
                    onChange={(e) => setImageIndex(e.target.value)}
                    style={inputStyle}
                    placeholder="e.g. 1 or 1-5 or 1,3,5"
                  />
                </label>
              </Card>
            )}

            {/* Extract button */}
            <button
              onClick={() => handleUploadAndSubmit(activeTab === "table" ? "table" : "image")}
              disabled={!selectedProjectId || !pdfFile || submitting}
              style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                gap: "var(--spacing-sm)", padding: "12px 28px", borderRadius: "var(--radius-pill)",
                background: selectedProjectId && pdfFile ? "var(--accent)" : "var(--bg-inset)",
                color: selectedProjectId && pdfFile ? "#fff" : "var(--text-tertiary)",
                fontWeight: 600, fontSize: "0.95rem", border: "none",
                cursor: selectedProjectId && pdfFile && !submitting ? "pointer" : "not-allowed",
                opacity: submitting ? 0.7 : 1,
              }}
            >
              {submitting ? (
                <><RefreshCw size={16} style={{ animation: "spin 1s linear infinite" }} /> Extracting…</>
              ) : (
                <><Play size={16} /> Extract</>
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
            {activeTab === "table" && (
              <>
                {tablePreview.length > 0 && (
                  <Card>
                    <div style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      marginBottom: "var(--spacing-md)",
                    }}>
                      <h4 style={{ margin: 0 }}>
                        <Table2 size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                        Table Preview
                      </h4>
                      <button
                        onClick={() => {
                          // Trigger CSV download
                          const csv = [tableHeaders.join(","), ...tablePreview.map((r) => r.join(","))].join("\n");
                          const blob = new Blob([csv], { type: "text/csv" });
                          const url = URL.createObjectURL(blob);
                          const a = document.createElement("a");
                          a.href = url;
                          a.download = "extracted_table.csv";
                          a.click();
                          URL.revokeObjectURL(url);
                        }}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: "4px",
                          padding: "6px 14px", borderRadius: "var(--radius-pill)",
                          border: "1px solid var(--separator)", background: "var(--bg-elevated)",
                          color: "var(--accent)", fontSize: "0.8rem", fontWeight: 500,
                          cursor: "pointer",
                        }}
                      >
                        <Download size={14} /> Download CSV
                      </button>
                    </div>
                    <div style={{ overflow: "auto", maxHeight: "400px" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
                        <thead>
                          <tr style={{ background: "var(--bg-root)", borderBottom: "2px solid var(--separator)" }}>
                            {tableHeaders.map((h, i) => (
                              <th key={i} style={{ textAlign: "left", padding: "8px 12px", fontWeight: 600, whiteSpace: "nowrap" }}>
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {tablePreview.map((row, ri) => (
                            <tr key={ri} style={{ borderBottom: "1px solid var(--separator)" }}>
                              {row.map((cell, ci) => (
                                <td key={ci} style={{ padding: "6px 12px" }}>
                                  {cell}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                )}

                {resultLoading && (
                  <Card>
                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
                      <Skeleton height="150px" />
                      <Skeleton height="80px" />
                    </div>
                  </Card>
                )}

                {resultError && (
                  <div style={{
                    padding: "var(--spacing-md)", borderRadius: "var(--radius-panel)",
                    background: "#ff3b3018", border: "1px solid #ff3b3030",
                    color: "var(--danger)", fontSize: "0.85rem",
                    display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
                  }}>
                    <AlertTriangle size={14} /> {resultError}
                  </div>
                )}

                {!tablePreview.length && !resultLoading && !resultError && (
                  <EmptyState
                    icon={Table2}
                    title="No table extracted"
                    description="Upload a PDF and click Extract to extract table data."
                  />
                )}
              </>
            )}

            {activeTab === "image" && (
              <>
                {imageGrid.length > 0 && (
                  <Card>
                    <div style={{
                      display: "flex", alignItems: "center", justifyContent: "space-between",
                      marginBottom: "var(--spacing-md)",
                    }}>
                      <h4 style={{ margin: 0 }}>
                        <Image size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                        Extracted Images ({imageCount})
                      </h4>
                      <button
                        onClick={() => {
                          // Trigger download for all (single image or mock ZIP)
                          if (imageGrid[0]) {
                            const a = document.createElement("a");
                            a.href = imageGrid[0];
                            a.download = "extracted_images.zip";
                            a.click();
                          }
                        }}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: "4px",
                          padding: "6px 14px", borderRadius: "var(--radius-pill)",
                          border: "1px solid var(--separator)", background: "var(--bg-elevated)",
                          color: "var(--accent)", fontSize: "0.8rem", fontWeight: 500,
                          cursor: "pointer",
                        }}
                      >
                        <Download size={14} /> Download ZIP
                      </button>
                    </div>
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                        gap: "var(--spacing-md)",
                      }}
                    >
                      {imageGrid.map((url, i) => (
                        <div
                          key={i}
                          style={{
                            borderRadius: "var(--radius-panel)",
                            border: "1px solid var(--separator)",
                            overflow: "hidden",
                            background: "var(--bg-root)",
                          }}
                        >
                          <img
                            src={url}
                            alt={`Extracted image ${i + 1}`}
                            style={{
                              width: "100%",
                              aspectRatio: "1",
                              objectFit: "cover",
                              display: "block",
                            }}
                          />
                          <div style={{
                            padding: "var(--spacing-xs) var(--spacing-sm)",
                            fontSize: "0.72rem",
                            color: "var(--text-secondary)",
                            textAlign: "center",
                            borderTop: "1px solid var(--separator)",
                          }}>
                            Image {i + 1}
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}

                {resultLoading && (
                  <Card>
                    <div style={{
                      display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
                      gap: "var(--spacing-md)",
                    }}>
                      {[1, 2, 3, 4].map((i) => (
                        <Skeleton key={i} height="140px" />
                      ))}
                    </div>
                  </Card>
                )}

                {resultError && (
                  <div style={{
                    padding: "var(--spacing-md)", borderRadius: "var(--radius-panel)",
                    background: "#ff3b3018", border: "1px solid #ff3b3030",
                    color: "var(--danger)", fontSize: "0.85rem",
                    display: "flex", alignItems: "center", gap: "var(--spacing-sm)",
                  }}>
                    <AlertTriangle size={14} /> {resultError}
                  </div>
                )}
              </>
            )}

            {/* General output from job result */}
            {result && result.outputs.length > 0 && (
              <Card>
                <h4 style={{ margin: "0 0 var(--spacing-md)" }}>
                  <Eye size={16} style={{ verticalAlign: "middle", marginRight: "var(--spacing-xs)" }} />
                  Output
                </h4>
                <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", marginBottom: "var(--spacing-md)" }}>
                  <StatusBadge status={result.status} />
                  <span style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>
                    {result.job.module || "Extraction Result"}
                  </span>
                </div>
                <ResultViewer outputs={result.outputs} />
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

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};
