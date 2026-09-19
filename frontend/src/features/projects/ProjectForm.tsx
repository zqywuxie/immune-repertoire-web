import { useEffect, useState } from "react";
import { Sheet } from "../../shared/components/Sheet";
import type { ProjectCreate } from "../../shared/types/domain";

type Props = {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: ProjectCreate) => Promise<void>;
  initial?: Partial<ProjectCreate>;
  title?: string;
};

export function ProjectForm({ open, onClose, onSubmit, initial, title = "新建项目" }: Props) {
  const [name, setName] = useState(initial?.name || "");
  const [institution, setInstitution] = useState(initial?.institution || "");
  const [cooperationLevel, setCooperationLevel] = useState(initial?.cooperation_level || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [status, setStatus] = useState(initial?.status || "active");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) return;
    setName(initial?.name || ""); setInstitution(initial?.institution || "");
    setCooperationLevel(initial?.cooperation_level || ""); setDescription(initial?.description || "");
    setStatus(initial?.status || "active"); setError("");
  }, [open, initial?.name, initial?.institution, initial?.cooperation_level, initial?.description, initial?.status]);
  const handleSave = async () => {
    if (!name.trim()) {
      setError("请填写项目名称。");
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
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Sheet open={open} onClose={onClose} title={title}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
        <Field label="名称 *">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="项目名称"
            autoFocus
            style={inputStyle}
          />
        </Field>

        <Field label="所属机构">
          <input
            type="text"
            value={institution}
            onChange={(e) => setInstitution(e.target.value)}
            placeholder="例如：南华大学"
            style={inputStyle}
          />
        </Field>

        <Field label="合作类型">
          <select value={cooperationLevel} onChange={(e) => setCooperationLevel(e.target.value)} style={inputSelectStyle}>
            <option value="">未设置</option>
            <option value="internal">内部</option>
            <option value="public">公开</option>
            <option value="collaboration">合作</option>
            <option value="restricted">受限</option>
          </select>
        </Field>

        <Field label="状态">
          <select value={status} onChange={(e) => setStatus(e.target.value)} style={inputSelectStyle}>
            <option value="active">进行中</option>
            <option value="paused">已暂停</option>
            <option value="archived">已归档</option>
          </select>
        </Field>

        <Field label="说明">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="填写项目说明…"
            rows={3}
            style={{ ...inputStyle, resize: "vertical", minHeight: "60px" }}
          />
        </Field>

        {error && (
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--danger)" }}>{error}</p>
        )}

        <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end" }}>
          <button type="button" onClick={onClose} disabled={saving} style={secondaryBtnStyle}>
            取消
          </button>
          <button type="button" onClick={handleSave} disabled={saving || !name.trim()} style={primaryBtnStyle}>
            {saving ? "正在保存…" : "保存"}
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
