import type { GroupSpec } from "../../../shared/api/groupSpecs";

type Props = {
  projectId: string;
  groupSpecs: GroupSpec[];
  loadingSpecs: boolean;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

export function SimpleForm({
  projectId,
  groupSpecs,
  loadingSpecs,
  value,
  onChange,
}: Props) {
  const setField = (k: string, v: unknown) => onChange({ ...value, [k]: v });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
      <FormField label="分组方案">
        <select
          value={(value.group_spec_id as string) || ""}
          onChange={(e) => setField("group_spec_id", e.target.value)}
          disabled={loadingSpecs}
          style={inputSelectStyle}
        >
          <option value="">不设置（全部样本）</option>
          {groupSpecs.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        {loadingSpecs && (
          <small style={{ color: "var(--text-tertiary)", fontSize: "0.72rem" }}>
            正在读取分组方案…
          </small>
        )}
      </FormField>

      {/* Optional: metric selector for boxplot-style modules */}
      <FormField label="指标（可选）">
        <select
          value={(value.metric as string) || ""}
          onChange={(e) => setField("metric", e.target.value || undefined)}
          style={inputSelectStyle}
        >
          <option value="">自动</option>
          <option value="diversity">多样性</option>
          <option value="clonality">克隆性</option>
          <option value="richness">丰富度</option>
          <option value="evenness">均匀度</option>
        </select>
      </FormField>

      {/* Template ID for ppt.render-slides */}
      <FormField label="模板编号（可选）">
        <input
          type="text"
          value={(value.template_id as string) || ""}
          onChange={(e) => setField("template_id", e.target.value || undefined)}
          placeholder="例如：默认模板"
          style={inputTextStyle}
        />
      </FormField>
    </div>
  );
}

function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
        textTransform: "uppercase",
        color: "var(--text-secondary)",
      }}
    >
      {label}
      {children}
    </label>
  );
}

const inputSelectStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};

const inputTextStyle: React.CSSProperties = {
  ...inputSelectStyle,
};
