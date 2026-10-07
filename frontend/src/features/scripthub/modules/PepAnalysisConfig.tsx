import { useRef } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import {
  ChainPicker,
  CommonRunFields,
  Field,
  GroupFieldSelect,
  GroupFieldMultiSelect,
  GroupOrderEditor,
  GroupValueSamplePicker,
  ModuleShell,
  Section,
  gridStyle,
  setFieldValue,
  stringList,
  stringValue,
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
  { key: "9", script: "12.clone_tracking.py", label: "\u8de8\u7ec4\u5171\u4eab CDR3 \u514b\u9686\u8ffd\u8e2a(\u81ea\u52a8\u5305\u542b\u7b2c 6 \u6b65)", mode: "optional" },
  { key: "10", script: "9.plot_CDR3_category_heatmap.py", label: "\u6309 CDR3 \u5206\u7c7b\u7ed8\u5236\u70ed\u56fe\uff08\u7ba1\u7ebf\u811a\u672c 9\uff09", mode: "optional" },
  { key: "11", script: "10.Alignment_shared.py", label: "\u6309\u5171\u4eab\u7c7b\u522b\u6bd4\u5bf9 VDJdb\u3001McPAS-TCR \u4e0e IEDB\uff08\u81ea\u52a8\u5305\u542b\u7b2c 6 \u6b65\uff09", mode: "optional" },
  { key: "12", script: "8.VJ_statistication.py", label: "\u539f\u7ba1\u7ebf\u7b2c 8 \u6b65\uff1aV/J \u4f7f\u7528\u5dee\u5f02\u6c47\u603b\uff08\u81ea\u52a8\u914d\u5bf9\u4e0a\u6e38\u5206\u7ec4\uff09", mode: "optional" },
];
const PEP_OPTIONAL_STEP_KEYS = PEP_PIPELINE_STEPS.filter((step) => step.mode === "optional").map((step) => step.key);

export function PepAnalysisConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    selected_chains: sourceContext?.chains?.length ? sourceContext.chains : ["TRA", "TRB"],
    group_fields: [],
    batch_field: "",
    min_sample_threshold: 3,
    optional_steps: ["5", "6", "7", "8"],
  });
  const latest = useRef({ current, onChange });
  latest.current = { current, onChange };
  const setField = (key: string, next: unknown) => {
    const { current: active, onChange: update } = latest.current;
    const publish = (nextValue: Record<string, unknown>) => { latest.current = { current: nextValue, onChange: update }; update(nextValue); };
    if (key === "batch_field") {
      publish({ ...active, batch_field: next, selected_samples_by_group: undefined,
        group_sample_identity: next ? "batch_sample" : "sample" });
    } else if (key === "selected_samples_by_group") {
      publish({ ...active, selected_samples_by_group: next,
        group_sample_identity: active.batch_field ? "batch_sample" : "sample" });
    } else publish({ ...active, [key]: next });
  };
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
          <GroupFieldSelect
            label="批次字段（可选）"
            value={stringValue(current.batch_field)}
            sourceContext={sourceContext}
            optional
            emptyLabel="未选择批次字段"
            onChange={(next) => setField("batch_field", next || undefined)}
          />
          <GroupOrderEditor
            selectedFields={stringList(current.group_fields)}
            sourceContext={sourceContext}
            value={current.group_order}
            onChange={(next) => setField("group_order", next)}
          />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.group_fields)} batchField={stringValue(current.batch_field) || undefined} />
          <Field label="最少样本数">
            <input type="number" min="1" value={String(current.min_sample_threshold ?? 3)} onChange={(event) => setField("min_sample_threshold", Number(event.target.value || 3))} style={inputStyle} />
          </Field>
          <ChainPicker value={current} setField={setField} sourceContext={sourceContext} />
          <PepPipelineSteps selected={stringList(current.optional_steps)} onChange={(next) => setField("optional_steps", next)} />
        </div>
        <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: "var(--bg-inset)", color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.7 }}>
          分析会读取当前选择的 PEP 文件，并按所选分组和样本筛选。若跨批次存在同名样本，请选择批次字段；PEP 文件所在批次目录名需与指标表中的批次值一致，平台会按“批次 + 样本编号 + 链型”匹配。样本选项显示批次与编号，更换批次字段后请重新确认各组样本。
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
          const modeLabel = step.mode === "asset" ? "\u8f93\u5165\u6587\u4ef6" : optional ? "\u53ef\u9009" : "\u5fc5\u9009";
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
                  {active ? modeLabel : "\u5df2\u8df3\u8fc7"}
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
