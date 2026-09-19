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
  { key: "1", script: "1.move_file.ipynb", label: "准备克隆序列输入文件", mode: "asset" },
  { key: "2", script: "2.Pep_shared.py", label: "CDR3 共享矩阵与 V/J 基因使用", mode: "required" },
  { key: "3", script: "3.add_cate_shared.py", label: "向克隆共享结果添加样本分类", mode: "required" },
  { key: "4", script: "4.add_cate_usage.py", label: "向基因使用结果添加样本分类", mode: "required" },
  { key: "5", script: "5.Heat_map_Thread.py", label: "基因使用差异热力图", mode: "optional" },
  { key: "6", script: "6.Pep_statistication.py", label: "CDR3 分类统计", mode: "optional" },
  { key: "7", script: "7.CDR3_arrage_heatmap_ver1.0.py", label: "CDR3 排列热力图", mode: "optional" },
  { key: "8", script: "8.plot_heatmap.py", label: "唯一 CDR3 热力图", mode: "optional" },
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
      title="克隆共享分析"
      detail="选择链类型、样本分组、样本数阈值及需要运行的分析步骤。"
      sourceContext={sourceContext}
    >
      <Section title="克隆分析流程">
        <div style={gridStyle}>
          <GroupFieldMultiSelect
            label="分组列"
            selected={stringList(current.group_fields)}
            sourceContext={sourceContext}
            onChange={(next) => setField("group_fields", next)}
            emptyLabel="未识别到样本指标表的分组列"
            reorderable={false}
          />
          <GroupOrderEditor
            selectedFields={stringList(current.group_fields)}
            sourceContext={sourceContext}
            value={current.group_order}
            onChange={(next) => setField("group_order", next)}
          />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.group_fields)} />
          <Field label="最少样本数">
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
        流程步骤
      </span>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "8px" }}>
        {PEP_PIPELINE_STEPS.map((step) => {
          const optional = step.mode === "optional";
          const active = !optional || selectedOptional.includes(step.key);
          const modeLabel = step.mode === "asset" ? "文件" : optional ? "Optional" : "Required";
          return (
            <button
              key={step.key}
              type="button"
              disabled={!optional}
              onClick={() => optional && toggleOptional(step.key)}
              title={optional ? "点击启用或跳过此可选步骤" : "始终运行此步骤"}
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
                <strong style={{ fontSize: "0.78rem" }}>步骤 {step.key}</strong>
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
