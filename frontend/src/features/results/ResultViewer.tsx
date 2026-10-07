import { ResultDocumentPreview } from "./ResultDocumentPreview";
import { ResultImageViewer } from "./ResultImageViewer";
import { TablePreview } from "./TablePreview";
import { TextResultPreview } from "./TextResultPreview";
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
    html: "交互报告",
    png: "图像",
    image: "图像",
    csv: "数据表",
    tsv: "数据表",
    xlsx: "电子表格",
    zip: "压缩包",
    ppt: "演示文稿",
    pptx: "演示文稿",
    pdf: "PDF",
    json: "JSON",
    log: "日志",
    text: "文本说明",
    txt: "文本说明",
    data: "下载",
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
        暂无输出文件。
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
  const { kind: recordedKind, url, label } = output;
  const kind = textOutputKind(recordedKind, url) || recordedKind;
  const openUrl = ["html", "pdf"].includes(kind) ? url : output.download_url || url;

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
          {kindLabel(kind)}
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
            在新标签页打开 ↗
          </a>
        )}
      </div>

      {/* Content area */}
      <div style={{ padding: "var(--spacing-md)" }}>
        <ViewArea kind={kind} url={url} downloadUrl={output.download_url || undefined} label={label || undefined} />
      </div>
    </div>
  );
}

export function ViewArea({ kind, url, downloadUrl, jobId, label }: { kind: string; url: string; downloadUrl?: string; jobId?: string; label?: string }) {
  if (!url) {
    return <EmptyState message="此输出没有可用链接。" />;
  }

  switch (textOutputKind(kind, url) || kind) {
    case "html":
      return <ResultDocumentPreview key={"html:" + url} kind="html" url={url} label={label} />;
    case "png":
    case "jpg":
    case "jpeg":
    case "svg":
    case "image":
      return <ResultImageViewer key={url} url={url} label={label} />;
    case "pdf":
      return <ResultDocumentPreview key={"pdf:" + url} kind="pdf" url={url} label={label} downloadUrl={downloadUrl} />;
    case "tsv":
    case "csv":
      return <CsvViewer jobId={jobId} kind={kind} url={downloadUrl || url} />;
    case "zip":
      return <ZipViewer url={downloadUrl || url} />;
    case "ppt":
    case "pptx":
      return <PptViewer url={downloadUrl || url} />;
    case "log":
    case "text":
      return <div><TextResultPreview key={kind + ":" + url} url={url} kind={textOutputKind(kind, url) || "text"} /><DownloadLink url={downloadUrl || url} label={textOutputKind(kind, url) === "log" ? "下载完整日志" : "下载完整文本"} /></div>;
    case "json":
      return <div><TextResultPreview key={url} url={url} /><DownloadLink url={downloadUrl || url} label="下载完整结构化数据" /></div>;
    default:
      return <DownloadViewer url={downloadUrl || url} kind={kind} />;
  }
}

// ── Sub-viewers ───────────────────────────────────────────────────────

function CsvViewer({ url, kind, jobId }: { url: string; kind: string; jobId?: string }) {
  return <div><TablePreview key={url} url={url} kind={kind} jobId={jobId} /><DownloadLink url={url} label="下载完整数据表" /></div>;
}

function ZipViewer({ url }: { url: string }) {
  return (
    <DownloadLink
      url={url}
      label="下载文件包"
      hint="包含此任务的全部输出文件。"
    />
  );
}

function PptViewer({ url }: { url: string }) {
  return (
    <DownloadLink
      url={url}
      label="下载演示文稿"
      hint="下载后可使用演示文稿软件打开。"
    />
  );
}

function DownloadViewer({ url, kind }: { url: string; kind: string }) {
  return <DownloadLink url={url} label={`下载${kindLabel(kind)}`} />;
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

/** Recognize registered log/text output, including legacy generic file kinds. */
export function textOutputKind(kind: string, url: string): "log" | "text" | null {
  const value = kind.toLowerCase();
  if (value === "log") return "log";
  if (value === "text" || value === "txt") return "text";
  if (!["data", "file", ""].includes(value)) return null;
  try {
    const pathname = decodeURIComponent(new URL(url, window.location.href).pathname).toLowerCase();
    if (pathname.endsWith(".log")) return "log";
    if (pathname.endsWith(".txt")) return "text";
  } catch { /* Unknown links retain their existing download behavior. */ }
  return null;
}
