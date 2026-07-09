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
      <FormField label="Group Spec">
        <select
          value={(value.group_spec_id as string) || ""}
          onChange={(e) => setField("group_spec_id", e.target.value)}
          disabled={loadingSpecs}
          style={inputSelectStyle}
        >
          <option value="">— None (all samples) —</option>
          {groupSpecs.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        {loadingSpecs && (
          <small style={{ color: "var(--text-tertiary)", fontSize: "0.72rem" }}>
            Loading group specs…
          </small>
        )}
      </FormField>

      {/* Optional: metric selector for boxplot-style modules */}
      <FormField label="Metric (optional)">
        <select
          value={(value.metric as string) || ""}
          onChange={(e) => setField("metric", e.target.value || undefined)}
          style={inputSelectStyle}
        >
          <option value="">— Auto —</option>
          <option value="diversity">Diversity</option>
          <option value="clonality">Clonality</option>
          <option value="richness">Richness</option>
          <option value="evenness">Evenness</option>
        </select>
      </FormField>

      {/* Template ID for ppt.render-slides */}
      <FormField label="Template ID (optional)">
        <input
          type="text"
          value={(value.template_id as string) || ""}
          onChange={(e) => setField("template_id", e.target.value || undefined)}
          placeholder="e.g. default_template"
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
