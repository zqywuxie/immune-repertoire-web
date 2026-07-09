import { useState } from "react";
import { Sheet } from "../../shared/components/Sheet";
import type { ProjectCreate } from "../../shared/types/domain";

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: ProjectCreate) => Promise<void>;
  initial?: Partial<ProjectCreate>;
  title?: string;
};

export function ProjectForm({ open, onClose, onSubmit, initial, title = "New Project" }: Props) {
  const [name, setName] = useState(initial?.name || "");
  const [institution, setInstitution] = useState(initial?.institution || "");
  const [cooperationLevel, setCooperationLevel] = useState(initial?.cooperation_level || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [status, setStatus] = useState(initial?.status || "active");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSave = async () => {
    if (!name.trim()) {
      setError("Project name is required.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await onSubmit({
        name: name.trim(),
        institution: institution.trim() || undefined,
        cooperation_level: cooperationLevel.trim() || undefined,
        description: description.trim() || undefined,
        status,
      } as ProjectCreate);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
        <Field label="Name *">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Project name"
            autoFocus
            style={inputStyle}
          />
        </Field>

        <Field label="Institution">
          <input
            type="text"
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            placeholder="e.g. Tsinghua University"
            style={inputStyle}
          />
        </Field>

        <Field label="Cooperation Level">
          <select value={cooperationLevel} onChange={(e) => setCooperationLevel(e.target.value)} style={inputSelectStyle}>
            <option value="">— None —</option>
            <option value="internal">Internal</option>
            <option value="public">Public</option>
            <option value="collaboration">Collaboration</option>
            <option value="restricted">Restricted</option>
          </select>
        </Field>

        <Field label="Status">
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={inputSelectStyle}>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="archived">Archived</option>
          </select>
        </Field>

        <Field label="Description">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Project description…"
            rows={3}
            style={{ ...inputStyle, resize: "vertical", minHeight: "60px" }}
          />
        </Field>

        {error && (
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--danger)" }}>{error}</p>
        )}

        <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end" }}>
          <button type="button" onClick={onClose} disabled={saving} style={secondaryBtnStyle}>
            Cancel
          </button>
          <button type="button" onClick={handleSave} disabled={saving || !name.trim()} style={primaryBtnStyle}>
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </Sheet>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: "flex", flexDirection: "column", gap: "4px", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: "var(--text-secondary)" }}>
      {label}
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  minHeight: "38px", padding: "7px 10px", borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)", background: "var(--bg-elevated)",
  color: "var(--text-primary)", fontSize: "0.85rem",
};
const inputSelectStyle: React.CSSProperties = { ...inputStyle };

const primaryBtnStyle: React.CSSProperties = {
  padding: "8px 20px", borderRadius: "var(--radius-control)", background: "var(--accent)",
  color: "#fff", fontWeight: 500, border: "none", cursor: "pointer",
  opacity: undefined as unknown as number | undefined,
};
const secondaryBtnStyle: React.CSSProperties = {
  ...primaryBtnStyle, background: "var(--bg-elevated)", color: "var(--text-primary)",
  border: "1px solid var(--separator)",
};
