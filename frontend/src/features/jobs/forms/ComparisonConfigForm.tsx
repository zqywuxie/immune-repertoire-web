type Props = {
  projectId: string;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

export function ComparisonConfigForm({ projectId, value, onChange }: Props) {
  const setField = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  const config = (value.comparison_config as Record<string, unknown>) || {};

  const updateConfig = (k: string, v: unknown) => {
    setField("comparison_config", { ...config, [k]: v });
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-md)" }}>
      <FormField label="Group A Name">
        <input
          type="text"
          value={(config.group_a_name as string) || ""}
          onChange={(e) => updateConfig("group_a_name", e.target.value)}
          placeholder="e.g. Healthy"
          style={inputStyle}
        />
      </FormField>

      <FormField label="Group B Name">
        <input
          type="text"
          value={(config.group_b_name as string) || ""}
          onChange={(e) => updateConfig("group_b_name", e.target.value)}
          placeholder="e.g. Disease"
          style={inputStyle}
        />
      </FormField>

      <FormField label="Comparison Method">
        <select
          value={(config.method as string) || "wilcoxon"}
          onChange={(e) => updateConfig("method", e.target.value)}
          style={inputSelectStyle}
        >
          <option value="wilcoxon">Wilcoxon Rank-Sum</option>
          <option value="ttest">T-Test</option>
          <option value="mannwhitney">Mann-Whitney U</option>
          <option value="edgeR">edgeR</option>
          <option value="deseq2">DESeq2</option>
        </select>
      </FormField>

      <FormField label="Heatmap IDs (comma-separated)">
        <input
          type="text"
          value={(config.heatmap_ids as string[])?.join(", ") || ""}
          onChange={(e) =>
            updateConfig(
              "heatmap_ids",
              e.target.value
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean)
            )
          }
          placeholder="heatmap-id-1, heatmap-id-2"
          style={inputStyle}
        />
      </FormField>

      <FormField label="Output Title (optional)">
        <input
          type="text"
          value={(config.title as string) || ""}
          onChange={(e) => updateConfig("title", e.target.value)}
          placeholder="Comparison Report Title"
          style={inputStyle}
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

const inputStyle: React.CSSProperties = {
  minHeight: "38px",
  padding: "7px 10px",
  borderRadius: "var(--radius-control)",
  border: "1px solid var(--separator)",
  background: "var(--bg-elevated)",
  color: "var(--text-primary)",
  fontSize: "0.85rem",
};

const inputSelectStyle: React.CSSProperties = { ...inputStyle };
