import type { ModuleFormProps } from "../../jobs/forms";
import {
  ChainPicker,
  CommonRunFields,
  Field,
  GroupFieldMultiSelect,
  GroupOrderEditor,
  GroupValueSamplePicker,
  ModuleShell,
  Section,
  gridStyle,
  setFieldValue,
  stringList,
  useSyncedDefaults,
  withDefaults,
  inputStyle,
} from "./shared";

const PEP_PIPELINE_STEPS = [
  { key: "1", script: "1.move_file.ipynb", label: "Prepare PEP input files", mode: "asset" },
  { key: "2", script: "2.Pep_shared.py", label: "CDR3 shared matrix and V/J/VJ usage", mode: "required" },
  { key: "3", script: "3.add_cate_shared.py", label: "Add profile categories to Pep_shared", mode: "required" },
  { key: "4", script: "4.add_cate_usage.py", label: "Add profile categories to usage outputs", mode: "required" },
  { key: "5", script: "5.Heat_map_Thread.py", label: "Differential usage heatmaps", mode: "optional" },
  { key: "6", script: "6.Pep_statistication.py", label: "CDR3 classification statistics", mode: "optional" },
  { key: "7", script: "7.CDR3_arrage_heatmap_ver1.0.py", label: "CDR3 arrangement heatmap", mode: "optional" },
  { key: "8", script: "8.plot_heatmap.py", label: "Unique CDR3 heatmap", mode: "optional" },
];
const PEP_OPTIONAL_STEP_KEYS = PEP_PIPELINE_STEPS.filter((step) => step.mode === "optional").map((step) => step.key);

export function PepAnalysisConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    selected_chains: sourceContext?.chains?.length ? sourceContext.chains : ["TRA", "TRB"],
    group_fields: [],
    min_sample_threshold: 3,
    optional_steps: ["5", "6", "7", "8"],
  });
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  return (
    <ModuleShell
      title="PEP Shared Analysis"
      detail="按 Pep_260213 的旧版配置组织：链、Profile 分组字段、样本阈值和可选 pipeline steps。"
      sourceContext={sourceContext}
    >
      <Section title="PEP Pipeline">
        <div style={gridStyle}>
          <GroupFieldMultiSelect
            label="Group Fields"
            selected={stringList(current.group_fields)}
            sourceContext={sourceContext}
            onChange={(next) => setField("group_fields", next)}
            emptyLabel="No Profile group fields detected"
            reorderable={false}
          />
          <GroupOrderEditor
            selectedFields={stringList(current.group_fields)}
            sourceContext={sourceContext}
            value={current.group_order}
            onChange={(next) => setField("group_order", next)}
          />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.group_fields)} />
          <Field label="Min Sample Threshold">
            <input type="number" min="1" value={String(current.min_sample_threshold ?? 3)} onChange={(event) => setField("min_sample_threshold", Number(event.target.value || 3))} style={inputStyle} />
          </Field>
          <ChainPicker value={current} setField={setField} sourceContext={sourceContext} />
          <PepPipelineSteps selected={stringList(current.optional_steps)} onChange={(next) => setField("optional_steps", next)} />
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}

function PepPipelineSteps({ selected, onChange }: { selected: string[]; onChange: (next: string[]) => void }) {
  const selectedOptional = selected.filter((step) => PEP_OPTIONAL_STEP_KEYS.includes(step));
  const toggleOptional = (stepKey: string) => {
    onChange(
      selectedOptional.includes(stepKey)
        ? selectedOptional.filter((item) => item !== stepKey)
        : [...selectedOptional, stepKey],
    );
  };

  return (
    <div style={{ gridColumn: "1 / -1", display: "flex", flexDirection: "column", gap: "8px" }}>
      <span style={{ fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", color: "var(--text-secondary)" }}>
        Pipeline Steps
      </span>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "8px" }}>
        {PEP_PIPELINE_STEPS.map((step) => {
          const optional = step.mode === "optional";
          const active = !optional || selectedOptional.includes(step.key);
          const modeLabel = step.mode === "asset" ? "Assets" : optional ? "Optional" : "Required";
          return (
            <button
              key={step.key}
              type="button"
              disabled={!optional}
              onClick={() => optional && toggleOptional(step.key)}
              title={optional ? "Click to enable or skip this optional script step" : "This step is always included"}
              style={{
                minHeight: "72px",
                padding: "9px 10px",
                borderRadius: "var(--radius-control)",
                border: active ? "1px solid var(--accent)" : "1px solid var(--separator)",
                background: active ? "var(--bg-inset)" : "var(--bg-elevated)",
                color: "var(--text-primary)",
                opacity: active ? 1 : 0.64,
                cursor: optional ? "pointer" : "default",
                textAlign: "left",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "8px", marginBottom: "5px" }}>
                <strong style={{ fontSize: "0.78rem" }}>Step {step.key}</strong>
                <span style={{ fontSize: "0.68rem", color: optional && !active ? "var(--text-tertiary)" : "var(--accent)", fontWeight: 700 }}>
                  {active ? modeLabel : "Skipped"}
                </span>
              </div>
              <div style={{ fontSize: "0.76rem", fontWeight: 700, overflowWrap: "anywhere" }}>{step.script}</div>
              <div style={{ marginTop: "3px", fontSize: "0.72rem", color: "var(--text-secondary)" }}>{step.label}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
