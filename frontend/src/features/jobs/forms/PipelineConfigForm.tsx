type Props = {
  projectId: string;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
};

const ANALYSIS_TYPES = [
  { key: "full", label: "Full Pipeline", desc: "Complete analysis from raw data to reports" },
  { key: "quick", label: "Quick Analysis", desc: "Fast overview with key metrics" },
  { key: "custom", label: "Custom", desc: "Select specific analysis steps" },
];

const CUSTOM_STEPS = [
  "cdr3_analysis",
  "diversity",
  "clonality",
  "v_usage",
  "j_usage",
  "vj_pairing",
  "heatmap",
  "treemap",
  "chord",
  "statistical",
  "report",
];

export function PipelineConfigForm({ projectId, value, onChange }: Props) {
  const setField = (k: string, v: unknown) => onChange({ ...value, [k]: v });
  const config = (value.pipeline_config as Record<string, unknown>) || {};
  const updateConfig = (k: string, v: unknown) =>
    setField("pipeline_config", { ...config, [k]: v });

  const analysisType = (value.analysis_type as string) || "full";
  const customSteps: string[] = Array.isArray(config.steps)
    ? (config.steps as string[])
    : [];

  const toggleStep = (step: string) => {
    const next = customSteps.includes(step)
      ? customSteps.filter((s) => s !== step)
      : [...customSteps, step];
    updateConfig("steps", next);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-lg)" }}>
      {/* Analysis type radio group */}
      <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
        <legend
          style={{
            fontSize: "0.75rem",
            fontWeight: 600,
            textTransform: "uppercase",
            color: "var(--text-secondary)",
            marginBottom: "var(--spacing-sm)",
          }}
        >
          Analysis Type
        </legend>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--spacing-sm)" }}>
          {ANALYSIS_TYPES.map((at) => {
            const isSelected = analysisType === at.key;
            return (
              <label
                key={at.key}
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "var(--spacing-md)",
                  padding: "var(--spacing-sm) var(--spacing-md)",
                  borderRadius: "var(--radius-control)",
                  border: `1px solid ${isSelected ? "var(--accent)" : "var(--separator)"}`,
                  background: isSelected ? "var(--bg-root)" : "var(--bg-elevated)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="radio"
                  name="analysis_type"
                  value={at.key}
                  checked={isSelected}
                  onChange={() => setField("analysis_type", at.key)}
                  style={{ marginTop: "3px" }}
                />
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.88rem" }}>{at.label}</div>
                  <div
                    style={{
                      fontSize: "0.75rem",
                      color: "var(--text-tertiary)",
                      marginTop: "2px",
                    }}
                  >
                    {at.desc}
                  </div>
                </div>
              </label>
            );
          })}
        </div>
      </fieldset>

      {/* Custom steps (only when custom is selected) */}
      {analysisType === "custom" && (
        <fieldset style={{ border: "none", padding: 0, margin: 0 }}>
          <legend
            style={{
              fontSize: "0.75rem",
              fontWeight: 600,
              textTransform: "uppercase",
              color: "var(--text-secondary)",
              marginBottom: "var(--spacing-sm)",
            }}
          >
            Pipeline Steps {customSteps.length > 0 && `(${customSteps.length})`}
          </legend>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "var(--spacing-xs)",
            }}
          >
            {CUSTOM_STEPS.map((step) => {
              const s = customSteps.includes(step);
              return (
                <button
                  key={step}
                  type="button"
                  onClick={() => toggleStep(step)}
                  style={{
                    padding: "4px 10px",
                    borderRadius: "var(--radius-pill)",
                    border: "1px solid var(--separator)",
                    background: s ? "var(--accent)" : "var(--bg-elevated)",
                    color: s ? "#fff" : "var(--text-primary)",
                    fontSize: "0.78rem",
                    fontWeight: s ? 600 : 400,
                    cursor: "pointer",
                  }}
                >
                  {s ? "✓ " : ""}
                  {step.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                </button>
              );
            })}
          </div>
        </fieldset>
      )}

      {/* Output format */}
      <FormField label="Output Format">
        <select
          value={(config.output_format as string) || "html"}
          onChange={(e) => updateConfig("output_format", e.target.value)}
          style={inputSelectStyle}
        >
          <option value="html">HTML Report</option>
          <option value="pdf">PDF Report</option>
          <option value="zip">ZIP Archive</option>
        </select>
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
