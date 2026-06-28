import { useState } from "react";
import { Upload } from "lucide-react";
import { uploadProjectAssets } from "../../shared/api/projects";

const UPLOAD_ASSET_TYPES = [
  "profile",
  "pep",
  "transcriptome",
  "sample_summary",
  "group_spec",
  "ppt_template",
  "pdf_source",
  "raw_archive",
];

type Props = {
  projectId: string;
  onSuccess: () => void;
};

export function AssetUpload({ projectId, onSuccess }: Props) {
  const [assetType, setAssetType] = useState("profile");
  const [files, setFiles] = useState<File[]>([]);
  const [replaceExisting, setReplaceExisting] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [message, setMessage] = useState("");

  const handleUpload = async () => {
    if (files.length === 0) return;
    setState("loading");
    setMessage("");
    try {
      const result = await uploadProjectAssets(projectId, {
        assetType,
        files,
        replaceExisting,
      });
      setState("idle");
      setMessage(
        `${result.assets.length} asset${result.assets.length !== 1 ? "s" : ""} uploaded.`
      );
      setFiles([]);
      onSuccess();
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Upload failed");
    }
  };

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "flex-end",
        gap: "var(--spacing-md)",
        padding: "var(--spacing-lg)",
        background: "var(--bg-elevated)",
        borderRadius: "var(--radius-panel)",
        border: "1px solid var(--separator)",
      }}
    >
      <Field label="Asset type">
        <select
          value={assetType}
          onChange={(e) => setAssetType(e.target.value)}
          disabled={state === "loading"}
          style={inputStyle}
        >
          {UPLOAD_ASSET_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </Field>

      <Field label="Files">
        <input
          type="file"
          multiple
          disabled={state === "loading"}
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
          style={inputStyle}
        />
      </Field>

      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--spacing-sm)",
          fontSize: "0.8rem",
          cursor: "pointer",
          paddingBottom: "2px",
        }}
      >
        <input
          type="checkbox"
          checked={replaceExisting}
          onChange={(e) => setReplaceExisting(e.target.checked)}
        />
        Replace existing
      </label>

      <button
        disabled={files.length === 0 || state === "loading"}
        onClick={handleUpload}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "var(--spacing-sm)",
          padding: "10px 18px",
          borderRadius: "var(--radius-control)",
          background: "var(--accent)",
          color: "#ffffff",
          fontWeight: 500,
          opacity: files.length === 0 ? 0.5 : 1,
          cursor: files.length === 0 ? "default" : "pointer",
        }}
      >
        <Upload size={16} />
        {state === "loading" ? "Uploading…" : `Upload ${files.length || ""}`}
      </button>

      {message && (
        <p
          style={{
            width: "100%",
            margin: 0,
            fontSize: "0.85rem",
            color: state === "error" ? "var(--danger)" : "var(--success)",
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
        color: "var(--text-secondary)",
        textTransform: "uppercase",
      }}
    >
      {label}
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
};
