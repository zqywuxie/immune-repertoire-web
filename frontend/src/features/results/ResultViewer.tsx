import { useState, useEffect } from "react";
import type { JobOutput } from "../../shared/types/domain";

export type ResultOutput = JobOutput & {
  module?: string | null;
  category?: string | null;
  download_url?: string | null;
  asset_id?: string | null;
};

type Props = {
  outputs: ResultOutput[];
  className?: string;
};

/** Map an output kind to a human-readable label. */
export function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    html: "Interactive Report",
    png: "Image",
    image: "Image",
    csv: "CSV Data",
    zip: "Archive",
    ppt: "PowerPoint",
    pptx: "PowerPoint",
    pdf: "PDF",
    json: "JSON",
    data: "Download",
  };
  return map[kind] ?? kind.toUpperCase();
}

/** Icon glyph per kind (used as a data attribute for CSS styling). */
export function kindIcon(kind: string): string {
  const map: Record<string, string> = {
    html: "🌐",
    png: "🖼️",
    image: "🖼️",
    csv: "📊",
    zip: "📦",
    ppt: "📽️",
    pptx: "📽️",
    pdf: "📄",
    json: "📋",
    data: "📁",
  };
  return map[kind] ?? "📁";
}

export function ResultViewer({ outputs, className }: Props) {
  if (!outputs?.length) {
    return (
      <div className={className} style={{ color: "var(--text-tertiary)", padding: "var(--spacing-md)" }}>
        No outputs available.
      </div>
    );
  }

  return (
    <div className={className} style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
      {outputs.map((o, i) => (
        <OutputCard key={`${o.kind}-${i}`} output={o} />
      ))}
    </div>
  );
}

export function OutputCard({ output }: { output: ResultOutput }) {
  const { kind, url, label } = output;
  const openUrl = output.download_url || url;

  return (
    <div
      style={{
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--spacing-sm)",
          padding: "var(--spacing-md) var(--spacing-lg)",
          borderBottom: "1px solid var(--separator)",
          background: "var(--bg-root)",
        }}
      >
        <span style={{ fontSize: "1.1rem" }}>{kindIcon(kind)}</span>
        <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>{label || kindLabel(kind)}</span>
        <span
          style={{
            fontSize: "0.7rem",
            fontWeight: 500,
            textTransform: "uppercase",
            color: "var(--text-tertiary)",
            background: "var(--bg-elevated)",
            padding: "2px 8px",
            borderRadius: "var(--radius-pill)",
          }}
        >
          {kind}
        </span>
        {openUrl && (
          <a
            href={openUrl}
            target="_blank"
            rel="noreferrer"
            style={{
              marginLeft: "auto",
              fontSize: "0.78rem",
              color: "var(--accent)",
              textDecoration: "none",
            }}
          >
            Open in new tab ↗
          </a>
        )}
      </div>

      {/* Content area */}
      <div style={{ padding: "var(--spacing-md)" }}>
        <ViewArea kind={kind} url={url} downloadUrl={output.download_url || undefined} />
      </div>
    </div>
  );
}

function ViewArea({ kind, url, downloadUrl }: { kind: string; url: string; downloadUrl?: string }) {
  if (!url) {
    return <EmptyState message="No URL available for this output." />;
  }

  switch (kind) {
    case "html":
      return <HtmlViewer url={url} />;
    case "png":
    case "image":
      return <ImageViewer url={url} />;
    case "pdf":
      return <PdfViewer url={url} />;
    case "csv":
      return <CsvViewer url={downloadUrl || url} />;
    case "zip":
      return <ZipViewer url={downloadUrl || url} />;
    case "ppt":
    case "pptx":
      return <PptViewer url={downloadUrl || url} />;
    case "json":
      return <JsonViewer url={url} />;
    default:
      return <DownloadViewer url={downloadUrl || url} kind={kind} />;
  }
}

// ── Sub-viewers ───────────────────────────────────────────────────────

function HtmlViewer({ url }: { url: string }) {
  return (
    <iframe
      src={url}
      title="HTML report"
      style={{
        width: "100%",
        height: "500px",
        border: "1px solid var(--separator)",
        borderRadius: "var(--radius-sm)",
        background: "#fff",
      }}
      sandbox="allow-scripts allow-same-origin"
    />
  );
}

function ImageViewer({ url }: { url: string }) {
  return (
    <div style={{ textAlign: "center" }}>
      <img
        src={url}
        alt="Output image"
        style={{
          maxWidth: "100%",
          maxHeight: "600px",
          borderRadius: "var(--radius-sm)",
          border: "1px solid var(--separator)",
        }}
      />
    </div>
  );
}

function PdfViewer({ url }: { url: string }) {
  return (
    <div>
      <iframe
        src={url}
        title="PDF viewer"
        style={{
          width: "100%",
          height: "600px",
          border: "1px solid var(--separator)",
          borderRadius: "var(--radius-sm)",
        }}
      />
      <DownloadLink url={url} label="Download PDF" />
    </div>
  );
}

function CsvViewer({ url }: { url: string }) {
  return (
    <DownloadLink
      url={url}
      label="Download CSV"
      hint="CSV files can be opened in Excel, Numbers, or any text editor."
    />
  );
}

function ZipViewer({ url }: { url: string }) {
  return (
    <DownloadLink
      url={url}
      label="Download Archive"
      hint="Contains all output files for this job."
    />
  );
}

function PptViewer({ url }: { url: string }) {
  return (
    <DownloadLink
      url={url}
      label="Download PowerPoint"
      hint="Download and open in Microsoft PowerPoint or Google Slides."
    />
  );
}

function JsonViewer({ url }: { url: string }) {
  const [json, setJson] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!url) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    fetch(url, { credentials: "include" })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const text = await r.text();
        // Try to pretty-print if valid JSON
        try {
          return JSON.stringify(JSON.parse(text), null, 2);
        } catch {
          return text;
        }
      })
      .then((formatted) => {
        if (!cancelled) setJson(formatted);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || "Failed to load JSON");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [url]);

  return (
    <div>
      {loading && (
        <div style={{ padding: "var(--spacing-md)", color: "var(--text-tertiary)", fontSize: "0.85rem" }}>
          Loading…
        </div>
      )}
      {error && (
        <div style={{ padding: "var(--spacing-md)", color: "var(--danger)", fontSize: "0.85rem" }}>
          Error: {error}
        </div>
      )}
      {json && (
        <pre
          style={{
            maxHeight: "400px",
            overflow: "auto",
            background: "var(--bg-root)",
            border: "1px solid var(--separator)",
            borderRadius: "var(--radius-sm)",
            padding: "var(--spacing-md)",
            fontSize: "0.78rem",
            fontFamily: "var(--font-mono, monospace)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          <code>{json}</code>
        </pre>
      )}
      <DownloadLink url={url} label="Download JSON" />
    </div>
  );
}

function DownloadViewer({ url, kind }: { url: string; kind: string }) {
  return <DownloadLink url={url} label={`Download ${kindLabel(kind)}`} />;
}

// ── Shared helpers ────────────────────────────────────────────────────

function DownloadLink({
  url,
  label,
  hint,
}: {
  url: string;
  label: string;
  hint?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: "var(--spacing-sm)",
        padding: "var(--spacing-lg)",
      }}
    >
      <a
        href={url}
        download
        target="_blank"
        rel="noreferrer"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--spacing-xs)",
          padding: "10px 24px",
          borderRadius: "var(--radius-pill)",
          background: "var(--accent)",
          color: "#fff",
          fontWeight: 600,
          fontSize: "0.88rem",
          textDecoration: "none",
        }}
      >
        {label}
      </a>
      {hint && (
        <span style={{ fontSize: "0.75rem", color: "var(--text-tertiary)" }}>
          {hint}
        </span>
      )}
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: "var(--spacing-xl)",
        color: "var(--text-tertiary)",
      }}
    >
      {message}
    </div>
  );
}
