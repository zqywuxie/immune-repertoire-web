import { useEffect, useState } from "react";
import { Select } from "../../shared/components/Select";
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

  const dirty = name !== (initial?.name || "") || institution !== (initial?.institution || "") || cooperationLevel !== (initial?.cooperation_level || "") || description !== (initial?.description || "") || status !== (initial?.status || "active");
  const requestClose = () => { if (!saving && (!dirty || window.confirm("项目内容尚未保存，确定放弃修改？"))) onClose(); };
  return (
    <Sheet open={open} onClose={requestClose} title={title}>
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

        <details open={Boolean(initial)} className="project-form-details"><summary>更多项目信息（可选）</summary><div style={{display:"grid", gap:16, paddingTop:16}}>
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
          <Select ariaLabel="合作类型" value={cooperationLevel} onChange={setCooperationLevel} disabled={saving} options={[{value:"",label:"未设置"},{value:"internal",label:"内部"},{value:"public",label:"公开"},{value:"collaboration",label:"合作"},{value:"restricted",label:"受限"}]} />
        </Field>

        <Field label="状态">
          <Select ariaLabel="项目状态" value={status} onChange={setStatus} disabled={saving} options={[{value:"active",label:"进行中"},{value:"paused",label:"已暂停"},{value:"archived",label:"已归档"}]} />
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

        </div></details>
        {error && (
          <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--danger)" }}>{error}</p>
        )}

        <div style={{ display: "flex", gap: "var(--spacing-sm)", justifyContent: "flex-end" }}>
          <button type="button" onClick={requestClose} disabled={saving} style={secondaryBtnStyle}>
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
  minHeight: "44px", padding: "10px 12px", borderRadius: "var(--radius-control)",
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
