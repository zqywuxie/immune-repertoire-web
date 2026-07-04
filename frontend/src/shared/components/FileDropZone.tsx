import { useCallback, type DragEvent, type ChangeEvent } from "react";
import { Upload, X, File as FileIcon } from "lucide-react";

interface FileEntry {
  name: string;
  size: number;
  file: File;
}

type Props = {
  files: FileEntry[];
  onFilesAdded: (files: FileList | File[]) => void;
  onRemoveFile: (name: string) => void;
  accept?: string;
  multiple?: boolean;
  disabled?: boolean;
  label?: string;
};

export function FileDropZone({
  files,
  onFilesAdded,
  onRemoveFile,
  accept,
  multiple = false,
  disabled,
  label = "Drag & drop files here, or click to browse",
}: Props) {
  const handleDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (!disabled && e.dataTransfer.files.length > 0) {
        onFilesAdded(multiple ? e.dataTransfer.files : [e.dataTransfer.files[0]]);
      }
    },
    [disabled, multiple, onFilesAdded],
  );

  const handleInput = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        onFilesAdded(multiple ? e.target.files : [e.target.files[0]]);
        e.target.value = "";
      }
    },
    [multiple, onFilesAdded],
  );

  const inputId = `fd-${Math.random().toString(36).slice(2, 8)}`;

  return (
    <div>
      <div
        onDrop={handleDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => !disabled && document.getElementById(inputId)?.click()}
        style={{
          border: "2px dashed var(--separator)",
          borderRadius: "var(--radius-panel)",
          padding: "var(--spacing-2xl)",
          textAlign: "center",
          background: "var(--bg-root)",
          cursor: disabled ? "not-allowed" : "pointer",
          transition: "border-color var(--duration-fast), background var(--duration-fast)",
          opacity: disabled ? 0.5 : 1,
        }}
        onDragEnter={(e) => {
          (e.target as HTMLDivElement).style.borderColor = "var(--accent)";
          (e.target as HTMLDivElement).style.background = "rgba(0,113,227,0.04)";
        }}
        onDragLeave={(e) => {
          (e.target as HTMLDivElement).style.borderColor = "var(--separator)";
          (e.target as HTMLDivElement).style.background = "var(--bg-root)";
        }}
      >
        <Upload size={28} style={{ color: "var(--text-tertiary)", marginBottom: "var(--spacing-sm)" }} />
        <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.875rem", fontFamily: "var(--font-family)" }}>
          {label}
        </p>
        {accept && (
          <p style={{ margin: "4px 0 0", color: "var(--text-tertiary)", fontSize: "0.75rem" }}>
            Accepted: {accept}
          </p>
        )}
        <input id={inputId} type="file" multiple={multiple} accept={accept} onChange={handleInput} style={{ display: "none" }} />
      </div>

      {files.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "6px", marginTop: "var(--spacing-md)" }}>
          {files.map((f) => (
            <div
              key={f.name}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "8px 12px",
                background: "var(--bg-root)",
                borderRadius: "var(--radius-control)",
                fontSize: "0.84rem",
                fontFamily: "var(--font-family)",
              }}
            >
              <span style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)", minWidth: 0 }}>
                <FileIcon size={14} style={{ color: "var(--text-tertiary)", flexShrink: 0 }} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                <span style={{ color: "var(--text-tertiary)", fontSize: "0.75rem", flexShrink: 0 }}>
                  {f.size < 1024 ? `${f.size} B` : f.size < 1024 * 1024 ? `${(f.size / 1024).toFixed(1)} KB` : `${(f.size / (1024 * 1024)).toFixed(1)} MB`}
                </span>
              </span>
              {!disabled && (
                <button
                  onClick={(e) => { e.stopPropagation(); onRemoveFile(f.name); }}
                  style={{ background: "none", border: "none", color: "var(--text-tertiary)", cursor: "pointer", padding: "2px", flexShrink: 0 }}
                  aria-label={`Remove ${f.name}`}
                >
                  <X size={14} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
