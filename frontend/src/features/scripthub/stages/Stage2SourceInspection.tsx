import { useState } from "react";
import type { CSSProperties } from "react";
import {
  RefreshCw,
  AlertCircle,
  Table2,
} from "lucide-react";
import { Card } from "../../../shared/components/Card";

export interface TablePreview {
  path?: string;
  columns: string[];
  rows: Array<Record<string, unknown> | unknown[]>;
  totalRows: number;
}

export interface InspectionResult {
  samples: number;
  sampleNames: string[];
  chains: number;
  chainLabels: string[];
  pepFiles: number;
  profileLoaded: boolean;
  transcriptomeLoaded: boolean;
  warnings: string[];
  profileFields: string[];
  groupFields: string[];
  pepColumns: string[];
  profilePreview?: TablePreview;
  pepPreview?: TablePreview;
}

interface Stage2SourceInspectionProps {
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
  inspection: InspectionResult | null;
  inspectionError?: string | null;
  onInspect: () => Promise<void> | void;
}

export function Stage2SourceInspection({
  pepPaths,
  profilePath,
  transcriptomePath,
  inspection,
  inspectionError,
  onInspect,
}: Stage2SourceInspectionProps) {
  const [inspecting, setInspecting] = useState(false);

  const handleInspect = async () => {
    setInspecting(true);
    try {
      await onInspect();
    } finally {
      setInspecting(false);
    }
  };

  const hasData = pepPaths.length > 0 || !!profilePath || !!transcriptomePath;

  if (!hasData) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
        <div>
          <h2 style={{ margin: 0 }}>Stage 2: Source Inspection</h2>
          <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
            Review and validate selected data sources.
          </p>
        </div>
        <div
          style={{
            padding: "var(--spacing-3xl)",
            textAlign: "center",
            background: "var(--bg-elevated)",
            borderRadius: "var(--radius-card)",
            border: "1px solid var(--separator)",
          }}
        >
          <AlertCircle size={40} style={{ color: "var(--text-tertiary)", marginBottom: "var(--spacing-md)" }} />
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", margin: 0 }}>
            No data sources selected. Go back to Data Intake and select files first.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xl)" }}>
      {/* Header */}
      <div>
        <h2 style={{ margin: 0 }}>Stage 2: Source Inspection</h2>
        <p style={{ margin: "4px 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          Review and validate selected data sources before configuring analysis.
        </p>
      </div>

      {/* Error banner */}
      {inspectionError && (
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
          {inspectionError}
        </div>
      )}

      {inspection && !inspection.profileLoaded && profilePath && (
        <div
          style={{
            padding: "var(--spacing-md) var(--spacing-lg)",
            borderRadius: "var(--radius-control)",
            background: "var(--warning)",
            color: "#fff",
            fontSize: "0.85rem",
            display: "flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
          }}
        >
          <AlertCircle size={16} />
          Profile file could not be loaded. Please check the file path and try again.
        </div>
      )}

      {inspection && inspection.warnings.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-xs)" }}>
          {inspection.warnings.map((warning, idx) => (
            <div
              key={`${warning}-${idx}`}
              style={{
                padding: "var(--spacing-sm) var(--spacing-md)",
                borderRadius: "var(--radius-control)",
                background: "color-mix(in srgb, var(--warning) 12%, transparent)",
                color: "var(--text-primary)",
                border: "1px solid color-mix(in srgb, var(--warning) 30%, transparent)",
                fontSize: "0.8rem",
                display: "flex",
                alignItems: "center",
                gap: "var(--spacing-sm)",
              }}
            >
              <AlertCircle size={15} style={{ color: "var(--warning)", flexShrink: 0 }} />
              {warning}
            </div>
          ))}
        </div>
      )}

      {inspection ? (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))",
            gap: "var(--spacing-lg)",
          }}
        >
          <PreviewTableCard
            title="Profile head5"
            path={inspection.profilePreview?.path || profilePath || "No profile selected"}
            preview={inspection.profilePreview}
            accent="var(--success)"
            empty="Profile file selected, but no preview rows could be read."
          />

          <PreviewTableCard
            title="PEP head5"
            path={inspection.pepPreview?.path || (pepPaths.length ? pepPaths[0] : "No PEP path selected")}
            preview={inspection.pepPreview}
            accent="var(--accent)"
            empty="PEP file selected, but no preview rows could be read."
          />
        </div>
      ) : (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-md)" }}>
            <Table2 size={20} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>Data format not inspected yet</div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                Run inspection to show the detected Profile and PEP data formats.
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Inspect Button */}
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          paddingTop: "var(--spacing-md)",
          borderTop: "1px solid var(--separator)",
        }}
      >
        <button
          onClick={handleInspect}
          disabled={inspecting}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--spacing-sm)",
            padding: "12px 32px",
            borderRadius: "var(--radius-control)",
            background: "var(--accent)",
            color: "#fff",
            fontWeight: 600,
            fontSize: "0.95rem",
            border: "none",
            cursor: inspecting ? "wait" : "pointer",
            opacity: inspecting ? 0.7 : 1,
          }}
        >
          <RefreshCw size={16} style={inspecting ? { animation: "spin 1s linear infinite" } : undefined} />
          {inspecting ? "Inspecting..." : inspection ? "Re-Inspect Sources" : "Inspect Sources"}
        </button>
      </div>
    </div>
  );
}

function PreviewTableCard({
  title,
  path,
  preview,
  accent,
  empty,
}: {
  title: string;
  path: string;
  preview?: TablePreview;
  accent: string;
  empty: string;
}) {
  const columns = preview?.columns || [];
  const rows = (preview?.rows || []).slice(0, 5);
  return (
    <Card>
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: "var(--spacing-sm)",
          marginBottom: "var(--spacing-md)",
        }}
      >
        <Table2 size={18} style={{ color: accent, flexShrink: 0, marginTop: "1px" }} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: "0.95rem" }}>{title}</div>
          <div
            style={{
              marginTop: "3px",
              fontSize: "0.75rem",
              color: "var(--text-tertiary)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              maxWidth: "100%",
            }}
            title={path}
          >
            {path}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-xs)", marginBottom: "var(--spacing-md)" }}>
        <PreviewMeta>{columns.length} columns</PreviewMeta>
        <PreviewMeta>showing {rows.length} rows</PreviewMeta>
        {typeof preview?.totalRows === "number" && <PreviewMeta>{preview.totalRows} preview rows read</PreviewMeta>}
      </div>

      {columns.length && rows.length ? (
        <div style={tableScrollerStyle}>
          <table style={tableStyle}>
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column} style={thStyle} title={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {columns.map((column, columnIndex) => (
                    <td key={`${column}-${columnIndex}`} style={tdStyle} title={cellText(row, column, columnIndex)}>
                      {cellText(row, column, columnIndex)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ ...emptyPreviewStyle, borderColor: `color-mix(in srgb, ${accent} 18%, var(--separator))` }}>
          {empty}
        </div>
      )}
    </Card>
  );
}

function PreviewMeta({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        padding: "3px 9px",
        borderRadius: "var(--radius-pill)",
        background: "var(--bg-inset)",
        color: "var(--text-secondary)",
        fontSize: "0.72rem",
        fontWeight: 600,
      }}
    >
      {children}
    </span>
  );
}

function cellText(row: Record<string, unknown> | unknown[], column: string, columnIndex: number) {
  const value = Array.isArray(row) ? row[columnIndex] : row[column];
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

const tableScrollerStyle: CSSProperties = {
  maxWidth: "100%",
  overflowX: "auto",
  border: "1px solid var(--separator)",
  borderRadius: "var(--radius-control)",
};

const tableStyle: CSSProperties = {
  width: "100%",
  minWidth: "720px",
  borderCollapse: "separate",
  borderSpacing: 0,
  fontSize: "0.76rem",
};

const thStyle: CSSProperties = {
  position: "sticky",
  top: 0,
  zIndex: 1,
  textAlign: "left",
  padding: "8px 10px",
  background: "var(--bg-inset)",
  color: "var(--text-secondary)",
  borderBottom: "1px solid var(--separator)",
  whiteSpace: "nowrap",
  maxWidth: "220px",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const tdStyle: CSSProperties = {
  padding: "7px 10px",
  borderBottom: "1px solid var(--separator)",
  color: "var(--text-primary)",
  whiteSpace: "nowrap",
  maxWidth: "260px",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const emptyPreviewStyle: CSSProperties = {
  padding: "var(--spacing-lg)",
  border: "1px dashed var(--separator)",
  borderRadius: "var(--radius-control)",
  color: "var(--text-tertiary)",
  background: "var(--bg-inset)",
  fontSize: "0.82rem",
};
