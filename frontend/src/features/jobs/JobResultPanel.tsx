import { useEffect, useMemo, useState } from "react";
import { Download, ExternalLink } from "lucide-react";
import type { JobResultsResponse } from "../../shared/api/jobs";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { kindLabel, type ResultOutput } from "../results";

type Props = {
  result: JobResultsResponse | null;
  loading: boolean;
  embedded?: boolean;
};

type DisplayOutput = ResultOutput & {
  key: string;
  module: string;
  category: string;
  download_url?: string | null;
};

export function JobResultPanel({ result, loading, embedded = false }: Props) {
  const outputs = useMemo(() => normalizeOutputs(result), [result]);
  const viewableOutputs = useMemo(() => outputs.filter((item) => !isArchive(item)), [outputs]);
  const archiveOutputs = useMemo(() => outputs.filter(isArchive), [outputs]);
  const moduleOptions = useMemo(() => unique(viewableOutputs.map((item) => item.module)), [viewableOutputs]);
  const [selectedModule, setSelectedModule] = useState("");
  const [selectedOutputKey, setSelectedOutputKey] = useState("");

  const moduleOutputs = useMemo(
    () => viewableOutputs.filter((item) => item.module === selectedModule),
    [selectedModule, viewableOutputs],
  );
  const selectedOutput = moduleOutputs.find((item) => item.key === selectedOutputKey) || moduleOutputs[0] || null;
  const moduleArchives = archiveOutputs.filter((item) => !selectedModule || item.module === selectedModule);

  useEffect(() => {
    if (!moduleOptions.length) {
      setSelectedModule("");
      return;
    }
    setSelectedModule((current) => (current && moduleOptions.includes(current) ? current : moduleOptions[0]));
  }, [moduleOptions]);

  useEffect(() => {
    if (!moduleOutputs.length) {
      setSelectedOutputKey("");
      return;
    }
    setSelectedOutputKey((current) =>
      current && moduleOutputs.some((item) => item.key === current) ? current : moduleOutputs[0].key,
    );
  }, [moduleOutputs]);

  if (loading) {
    return <PanelShell embedded={embedded}><EmptyState message="Loading job results..." /></PanelShell>;
  }

  if (!result) {
    return embedded
      ? <PanelShell embedded={embedded}><EmptyState message="No results available yet." /></PanelShell>
      : null;
  }

  return (
    <PanelShell embedded={embedded}>
      {!embedded && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "var(--spacing-md)",
          }}
        >
          <h4 style={{ margin: 0 }}>{result.job.module || "Job Result"}</h4>
          <StatusBadge status={result.status} />
        </div>
      )}

      {viewableOutputs.length > 0 ? (
        <div style={{ display: "grid", gap: "var(--spacing-md)" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "var(--spacing-sm)",
              alignItems: "end",
            }}
          >
            <SelectField
              label="Module"
              value={selectedModule}
              onChange={setSelectedModule}
              options={moduleOptions.map((value) => ({ value, label: value }))}
            />
            <SelectField
              label="Result"
              value={selectedOutput?.key || ""}
              onChange={setSelectedOutputKey}
              options={moduleOutputs.map((item) => ({
                value: item.key,
                label: `${item.category} · ${item.label || kindLabel(item.kind)}`,
              }))}
            />
          </div>

          {selectedOutput && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "var(--spacing-md)",
                padding: "var(--spacing-md)",
                borderRadius: "var(--radius-control)",
                background: "var(--bg-root)",
                border: "1px solid var(--separator)",
                flexWrap: "wrap",
              }}
            >
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: "0.88rem" }}>
                  {selectedOutput.label || kindLabel(selectedOutput.kind)}
                </div>
                <div style={{ color: "var(--text-secondary)", fontSize: "0.76rem", marginTop: "3px" }}>
                  {selectedOutput.category} · {kindLabel(selectedOutput.kind)}
                </div>
              </div>
              <a
                href={selectedOutput.download_url || selectedOutput.url}
                target="_blank"
                rel="noreferrer"
                style={downloadButtonStyle}
              >
                <ExternalLink size={15} />
                {selectedOutput.kind === "html" ? "Open Viewer" : "Open Output"}
              </a>
            </div>
          )}
        </div>
      ) : (
        <EmptyState message="No previewable results available." />
      )}

      {moduleArchives.length > 0 && (
        <div style={{ display: "grid", gap: "var(--spacing-sm)" }}>
          <div style={sectionLabelStyle}>ZIP Downloads</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {moduleArchives.map((item) => (
              <a
                key={item.key}
                href={item.download_url || item.url}
                download
                target="_blank"
                rel="noreferrer"
                style={downloadButtonStyle}
                title={item.label || item.module}
              >
                <Download size={15} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {item.module}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}

      {result.assets.length > 0 && (
        <div style={{ display: "grid", gap: "var(--spacing-sm)" }}>
          <div style={sectionLabelStyle}>Registered Assets</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--spacing-sm)" }}>
            {result.assets.map((asset) => (
              <a
                key={asset.id}
                href={asset.download_url || asset.preview_url || "#"}
                target="_blank"
                rel="noreferrer"
                style={assetLinkStyle}
                title={asset.original_name}
              >
                <ExternalLink size={14} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {asset.original_name}
                </span>
              </a>
            ))}
          </div>
        </div>
      )}
    </PanelShell>
  );
}

function PanelShell({ children, embedded }: { children: React.ReactNode; embedded?: boolean }) {
  if (embedded) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
        {children}
      </div>
    );
  }

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        padding: "var(--spacing-xl)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-lg)",
      }}
    >
      {children}
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <label style={{ display: "grid", gap: "6px", minWidth: 0 }}>
      <span style={sectionLabelStyle}>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        style={{
          width: "100%",
          minHeight: "38px",
          border: "1px solid var(--separator)",
          borderRadius: "var(--radius-control)",
          background: "var(--bg-root)",
          color: "var(--text-primary)",
          padding: "0 10px",
          fontSize: "0.86rem",
        }}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div
      style={{
        background: "var(--bg-root)",
        border: "1px solid var(--separator)",
        borderRadius: "var(--radius-control)",
        padding: "var(--spacing-xl)",
        textAlign: "center",
        color: "var(--text-tertiary)",
      }}
    >
      {message}
    </div>
  );
}

function normalizeOutputs(result: JobResultsResponse | null): DisplayOutput[] {
  if (!result) return [];
  const baseModule = result.job.module || "Result";
  const rawOutputs: ResultOutput[] = [...(result.outputs || [])];

  for (const asset of result.assets || []) {
    const url = asset.preview_url || asset.download_url || "";
    if (!url) continue;
    rawOutputs.push({
      label: asset.original_name || "Asset",
      url,
      kind: kindFromAsset(asset),
      module: assetModule(asset, baseModule),
      category: "Registered Asset",
      download_url: asset.download_url || url,
      asset_id: asset.id,
    });
  }

  const seen = new Set<string>();
  const normalized: DisplayOutput[] = [];
  rawOutputs.forEach((output, index) => {
    const url = String(output.url || "").trim();
    const downloadUrl = String(output.download_url || "").trim();
    if (!url && !downloadUrl) return;
    const module = cleanText(output.module) || resultModuleFromLabel(output.label) || baseModule;
    const keySeed = `${module}:${output.kind}:${url || downloadUrl}:${output.asset_id || ""}`;
    if (seen.has(keySeed)) return;
    seen.add(keySeed);
    const kind = String(output.kind || kindFromUrl(url || downloadUrl)).toLowerCase();
    normalized.push({
      ...output,
      kind,
      url: url || downloadUrl,
      download_url: downloadUrl || (kind === "zip" ? url : undefined),
      module,
      category: cleanText(output.category) || defaultCategory(kind),
      key: `${keySeed}:${index}`,
    });
  });
  return normalized;
}

function isArchive(output: DisplayOutput) {
  return output.kind === "zip" || defaultCategory(output.kind) === "Archive";
}

function defaultCategory(kind: string) {
  if (kind === "zip") return "Archive";
  if (kind === "html") return "Viewer";
  if (kind === "png" || kind === "image") return "Plots";
  return kindLabel(kind);
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function cleanText(value: unknown) {
  return String(value || "").trim();
}

function resultModuleFromLabel(label: unknown) {
  const text = cleanText(label);
  const marker = text.match(/^(.*?)\s+(viewer|bundle|zip|archive)$/i);
  return marker?.[1]?.trim() || "";
}

function kindFromAsset(asset: { mime_type?: string | null; original_name?: string }) {
  const mime = String(asset.mime_type || "").toLowerCase();
  if (mime.includes("zip")) return "zip";
  if (mime.includes("html")) return "html";
  if (mime.includes("image") || mime.includes("png") || mime.includes("jpeg")) return "image";
  if (mime.includes("pdf")) return "pdf";
  if (mime.includes("csv") || mime.includes("excel")) return "csv";
  if (mime.includes("json")) return "json";
  return kindFromUrl(asset.original_name || "");
}

function kindFromUrl(url: string) {
  const lower = url.toLowerCase().split("?")[0];
  if (lower.endsWith(".zip")) return "zip";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "html";
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".svg")) return "image";
  if (lower.endsWith(".pdf")) return "pdf";
  if (lower.endsWith(".csv") || lower.endsWith(".tsv") || lower.endsWith(".xlsx")) return "csv";
  if (lower.endsWith(".json")) return "json";
  if (lower.endsWith(".ppt") || lower.endsWith(".pptx")) return "ppt";
  return "data";
}

function assetModule(asset: { metadata?: unknown }, fallback: string) {
  const metadata = asset.metadata && typeof asset.metadata === "object" ? asset.metadata as Record<string, unknown> : {};
  return cleanText(metadata.analysis_type) || cleanText(metadata.module) || fallback;
}

const sectionLabelStyle: React.CSSProperties = {
  fontSize: "0.76rem",
  color: "var(--text-secondary)",
  fontWeight: 700,
  textTransform: "uppercase",
};

const downloadButtonStyle: React.CSSProperties = {
  minWidth: "150px",
  maxWidth: "240px",
  minHeight: "36px",
  padding: "8px 12px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--accent)",
  background: "var(--accent)",
  color: "#fff",
  fontSize: "0.82rem",
  fontWeight: 650,
  textDecoration: "none",
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  gap: "8px",
};

const assetLinkStyle: React.CSSProperties = {
  maxWidth: "260px",
  minHeight: "34px",
  padding: "7px 12px",
  borderRadius: "var(--radius-control)",
  background: "var(--bg-root)",
  color: "var(--text-primary)",
  fontSize: "0.82rem",
  textDecoration: "none",
  border: "1px solid var(--separator)",
  display: "inline-flex",
  alignItems: "center",
  gap: "8px",
};
