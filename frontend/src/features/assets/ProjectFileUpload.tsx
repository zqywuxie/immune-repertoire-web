import { useState } from "react";
import { FileUp, Upload, X } from "lucide-react";
import { uploadProjectAssets } from "../../shared/api/projects";
import { FileDropZone } from "../../shared/components/FileDropZone";

type Props = {
  projectId: string;
  onSuccess: () => void;
};

type FileEntry = {
  name: string;
  size: number;
  file: File;
};

export function ProjectFileUpload({ projectId, onSuccess }: Props) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleUpload = async () => {
    if (!files.length || state === "loading") return;
    setState("loading");
    setMessage("");
    try {
      const result = await uploadProjectAssets(projectId, {
        assetType: "project_file",
        files: files.map((item) => item.file),
        replaceExisting: false,
      });
      setFiles([]);
      setState("idle");
      setMessage(`${result.assets.length} project file(s) uploaded.`);
      onSuccess();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Project file upload failed.");
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-xl)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-card)",
        border: "1px solid var(--separator)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--spacing-md)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--spacing-sm)" }}>
          <FileUp size={18} style={{ color: "var(--accent)" }} />
          <div>
            <h4 style={{ margin: 0, fontSize: "0.95rem" }}>Project Files</h4>
            <p style={{ margin: "2px 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
              Upload project-related files that should not be used as analysis inputs.
            </p>
          </div>
        </div>
        {files.length > 0 && (
          <button
            type="button"
            onClick={() => setFiles([])}
            disabled={state === "loading"}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "4px",
              border: "1px solid var(--separator)",
              borderRadius: "var(--radius-control)",
              background: "var(--bg-root)",
              color: "var(--text-secondary)",
              padding: "6px 10px",
              fontSize: "0.78rem",
              cursor: state === "loading" ? "not-allowed" : "pointer",
            }}
          >
            <X size={14} />
            Clear
          </button>
        )}
      </div>

      <FileDropZone
        files={files}
        onFilesAdded={(incoming) => {
          const nextFiles = Array.from(incoming as FileList | File[]).map((file) => ({
            name: file.name,
            size: file.size,
            file,
          }));
          setFiles((prev) => {
            const byName = new Map(prev.map((item) => [item.name, item]));
            for (const item of nextFiles) byName.set(item.name, item);
            return [...byName.values()];
          });
        }}
        onRemoveFile={(name) => setFiles((prev) => prev.filter((item) => item.name !== name))}
        multiple
        disabled={state === "loading"}
        label="Drop project documents, notes, tables, or attachments here"
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--spacing-md)" }}>
        <span style={{ color: "var(--text-tertiary)", fontSize: "0.78rem" }}>
          These files are stored with the project and excluded from analysis data sets.
        </span>
        <button
          type="button"
          onClick={handleUpload}
          disabled={!files.length || state === "loading"}
          className="btn btn-primary"
          style={{ padding: "10px 18px", whiteSpace: "nowrap" }}
        >
          <Upload size={15} />
          {state === "loading" ? "Uploading..." : `Upload ${files.length || ""}`}
        </button>
      </div>

      {message && (
        <div
          style={{
            padding: "var(--spacing-sm) var(--spacing-md)",
            borderRadius: "var(--radius-control)",
            background: state === "error" ? "rgba(255,59,48,0.08)" : "rgba(52,199,89,0.08)",
            border: `1px solid ${state === "error" ? "var(--danger)" : "var(--success)"}`,
            color: state === "error" ? "var(--danger)" : "var(--success)",
            fontSize: "0.82rem",
          }}
        >
          {message}
        </div>
      )}
    </div>
  );
}
