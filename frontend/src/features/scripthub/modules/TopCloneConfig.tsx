import type { ModuleFormProps } from "../../jobs/forms";
import {
  ChainPicker,
  CommonRunFields,
  Field,
  GroupFieldSelect,
  GroupValueSamplePicker,
  ModuleShell,
  Section,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

export function TopCloneConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    mode: "trace",
    top_n: 10,
    selected_chains: sourceContext?.chains?.length ? sourceContext.chains : ["TRA", "TRB"],
  });
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  return (
    <ModuleShell
      title="优势克隆"
      detail="选择克隆跟踪或逐样本分析模式，并配置样本分组。"
      sourceContext={sourceContext}
    >
      <Section title="克隆排序">
        <div style={gridStyle}>
          <GroupFieldSelect value={stringValue(current.group_field)} sourceContext={sourceContext} onChange={(next) => setField("group_field", next || undefined)} />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.group_field)].filter(Boolean)} />
          <Field label="分组顺序">
            <input value={stringValue(current.group_order)} onChange={(event) => setField("group_order", event.target.value || undefined)} placeholder="可选，按顺序填写并用逗号分隔" style={inputStyle} />
          </Field>
          <Field label="分析模式">
            <select value={stringValue(current.mode, "trace")} onChange={(event) => setField("mode", event.target.value)} style={inputStyle}>
              <option value="trace">跟踪记录</option>
              <option value="per_sample">逐样本</option>
            </select>
          </Field>
          <Field label="排名前几位">
            <input type="number" min="1" value={String(current.top_n ?? 10)} onChange={(event) => setField("top_n", Number(event.target.value || 10))} style={inputStyle} />
          </Field>
          <ChainPicker value={current} setField={setField} sourceContext={sourceContext} />
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
