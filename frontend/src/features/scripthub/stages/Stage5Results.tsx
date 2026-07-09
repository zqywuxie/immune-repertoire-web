import { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  Download,
  Eye,
  RotateCcw,
  AlertCircle,
  Info,
} from "lucide-react";
import type { JobResultsResponse } from "../../../shared/api/jobs";
import { StatusBadge } from "../../../shared/components/StatusBadge";
import { Skeleton } from "../../../shared/components/Skeleton";

interface Stage5ResultsProps {
  jobIds: string[];
  resultsByJobId: Record<string, JobResultsResponse>;
  onReset: () => void;
}

interface ExportableOutput {
  key: string;
  jobId: string;
  module: string;
  status: string;
  label: string;
  kind: string;
  url: string;
}

export function Stage5Results({ jobIds, resultsByJobId, onReset }: Stage5ResultsProps) {
  const [downloading, setDownloading] = useState(false);
  const outputItems = useMemo<ExportableOutput[]>(() => {
    return jobIds.flatMap((jobId) => {
      const result = resultsByJobId[jobId];
      if (!result) return [];
      return result.outputs.map((output, index) => ({
        key: `${jobId}:${index}:${output.url}`,
        jobId,
        module: result.job?.module || "script-hub",
        status: result.status,
        label: output.label || output.url,
        kind: output.kind || "output",
        url: output.url,
      }));
    });
  }, [jobIds, resultsByJobId]);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);

  useEffect(() => {
    setSelectedKeys((prev) => {
      const validKeys = new Set(outputItems.map((item) => item.key));
      const preserved = prev.filter((key) => validKeys.has(key));
      if (preserved.length) return preserved;
      return outputItems
        .filter((item) => item.kind.toLowerCase().includes("zip") || item.url.toLowerCase().includes(".zip"))
        .map((item) => item.key);
    });
  }, [outputItems]);

  const results = jobIds.map((jobId) => resultsByJobId[jobId]).filter(Boolean);

  if (!results.length) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
        <div>
          <h2 style={{ margin: 0 }}>Stage 5: Results</h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            Waiting for results...
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
          <Skeleton height="60px" />
          <Skeleton height="200px" />
          <Skeleton height="120px" />
        </div>
      </div>
    );
  }

  const completedCount = results.filter((result) => result.status === "completed").length;
  const failedCount = results.filter((result) => result.status === "failed" || result.status === "cancelled").length;
  const isSuccess = results.length > 0 && completedCount === results.length;
  const isFailed = failedCount > 0;

  const handleDownloadSelected = async () => {
    setDownloading(true);
    try {
      const selectedSet = new Set(selectedKeys);
      const targets = outputItems.filter((item) => selectedSet.has(item.key));
      for (const output of targets) {
        if (output.url) {
          window.open(output.url, "_blank");
        }
      }
    } finally {
      setDownloading(false);
    }
  };

  const toggleOutput = (key: string) => {
    setSelectedKeys((prev) => (
      prev.includes(key) ? prev.filter((item) => item !== key) : [...prev, key]
    ));
  };

  const viewerOutput = outputItems.find((item) => item.kind.toLowerCase().includes("html"))
    || outputItems.find((item) => item.url.toLowerCase().includes(".html"))
    || outputItems[0];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      {/* Header */}
      <div>
        <h2 style={{ margin: 0 }}>Stage 5: Results</h2>
        <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          Review analysis outputs, download files, or start a new analysis.
        </p>
      </div>

      {/* Status Alert */}
      {isSuccess ? (
        <div
          style={{
            padding: "var(--spacing-lg)",
            borderRadius: "var(--radius-card)",
            background: "rgba(52, 199, 89, 0.08)",
            border: "1px solid rgba(52, 199, 89, 0.2)",
            display: "flex",
            alignItems: "flex-start",
            gap: "var(--spacing-md)",
          }}
        >
          <CheckCircle2 size={28} style={{ color: "var(--success)", flexShrink: 0, marginTop: "2px" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: "1rem", color: "var(--success)" }}>
              Analysis Completed Successfully
            </div>
            <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginTop: "4px" }}>
              {completedCount} job{completedCount !== 1 ? "s" : ""} completed — {outputItems.length} exportable output{outputItems.length !== 1 ? "s" : ""}
            </div>
          </div>
        </div>
      ) : isFailed ? (
        <div
          style={{
            padding: "var(--spacing-lg)",
            borderRadius: "var(--radius-card)",
            background: "rgba(255, 59, 48, 0.08)",
            border: "1px solid rgba(255, 59, 48, 0.2)",
            display: "flex",
            alignItems: "flex-start",
            gap: "var(--spacing-md)",
          }}
        >
          <AlertCircle size={28} style={{ color: "var(--danger)", flexShrink: 0, marginTop: "2px" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: "1rem", color: "var(--danger)" }}>
              Analysis Failed
            </div>
            <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginTop: "4px" }}>
              {failedCount} job{failedCount !== 1 ? "s" : ""} failed or cancelled. Check the execution log for details.
            </div>
          </div>
        </div>
      ) : (
        <div
          style={{
            padding: "var(--spacing-lg)",
            borderRadius: "var(--radius-card)",
            background: "rgba(255, 149, 0, 0.08)",
            border: "1px solid rgba(255, 149, 0, 0.2)",
            display: "flex",
            alignItems: "flex-start",
            gap: "var(--spacing-md)",
          }}
        >
          <Info size={28} style={{ color: "var(--warning)", flexShrink: 0, marginTop: "2px" }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: "1rem", color: "var(--warning)" }}>
              Analysis In Progress
            </div>
            <div style={{ fontSize: "0.82rem", color: "var(--text-secondary)", marginTop: "4px" }}>
              Completed {completedCount}/{results.length} jobs.
            </div>
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--spacing-sm)",
        }}
      >
        <button
          onClick={() => {
            if (viewerOutput?.url) {
              window.open(viewerOutput.url, "_blank");
            }
          }}
          disabled={!viewerOutput}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "10px 22px",
            borderRadius: "var(--radius-control)",
            background: viewerOutput ? "var(--accent)" : "var(--bg-inset)",
            color: viewerOutput ? "#fff" : "var(--text-tertiary)",
            fontWeight: 500,
            fontSize: "0.85rem",
            border: "none",
            cursor: viewerOutput ? "pointer" : "not-allowed",
          }}
        >
          <Eye size={16} />
          Open Viewer
        </button>

        <button
          onClick={handleDownloadSelected}
          disabled={downloading || selectedKeys.length === 0}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "10px 22px",
            borderRadius: "var(--radius-control)",
            background: selectedKeys.length > 0 && !downloading ? "var(--success)" : "var(--bg-inset)",
            color: selectedKeys.length > 0 && !downloading ? "#fff" : "var(--text-tertiary)",
            fontWeight: 500,
            fontSize: "0.85rem",
            border: "none",
            cursor: selectedKeys.length > 0 && !downloading ? "pointer" : "not-allowed",
          }}
        >
          <Download size={16} />
          {downloading ? "Downloading..." : `Export Selected (${selectedKeys.length})`}
        </button>

        <button
          onClick={onReset}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "10px 22px",
            borderRadius: "var(--radius-control)",
            border: "1px solid var(--separator)",
            background: "var(--bg-elevated)",
            color: "var(--text-primary)",
            fontWeight: 500,
            fontSize: "0.85rem",
            cursor: "pointer",
          }}
        >
          <RotateCcw size={16} />
          Start New
        </button>
      </div>

      {/* Selectable exports */}
      <div
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
            gap: "var(--spacing-sm)",
            padding: "var(--spacing-md) var(--spacing-lg)",
            borderBottom: "1px solid var(--separator)",
            flexWrap: "wrap",
          }}
        >
          <div>
            <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>Export Outputs</div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
              Choose the result files to export. ZIP outputs are selected by default.
            </div>
          </div>
          <div style={{ display: "flex", gap: "var(--spacing-xs)", flexWrap: "wrap" }}>
            <button type="button" onClick={() => setSelectedKeys(outputItems.map((item) => item.key))} style={smallBtnStyle}>
              Select all
            </button>
            <button type="button" onClick={() => setSelectedKeys([])} style={smallBtnStyle}>
              Clear
            </button>
          </div>
        </div>

        {outputItems.length === 0 ? (
          <div style={{ padding: "var(--spacing-xl)", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
            No exportable outputs were reported for these jobs.
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "var(--spacing-sm)", padding: "var(--spacing-md)" }}>
            {outputItems.map((item) => {
              const checked = selectedKeys.includes(item.key);
              return (
                <label
                  key={item.key}
                  style={{
                    display: "flex",
                    alignItems: "flex-start",
                    gap: "var(--spacing-sm)",
                    padding: "var(--spacing-sm)",
                    border: checked ? "1px solid rgba(0,113,227,0.45)" : "1px solid var(--separator)",
                    borderRadius: "var(--radius-control)",
                    background: checked ? "rgba(0,113,227,0.05)" : "var(--bg-inset)",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => toggleOutput(item.key)}
                    style={{ marginTop: "3px" }}
                  />
                  <span style={{ minWidth: 0 }}>
                    <span style={{ display: "block", fontWeight: 600, fontSize: "0.82rem", color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {item.label}
                    </span>
                    <span style={{ display: "block", fontSize: "0.7rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                      {item.module} · {item.kind} · Job {item.jobId.slice(0, 8)}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        )}
      </div>

    </div>
  );
}

const smallBtnStyle: React.CSSProperties = {
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  borderRadius: "var(--radius-control)",
  padding: "6px 10px",
  fontSize: "0.75rem",
  cursor: "pointer",
};
