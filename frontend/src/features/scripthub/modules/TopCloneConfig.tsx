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
      title="TopClone"
      detail="旧版 trace/per-sample 模式配置；分组字段来自 Profile 检测列。"
      sourceContext={sourceContext}
    >
      <Section title="Clone Ranking">
        <div style={gridStyle}>
          <GroupFieldSelect value={stringValue(current.group_field)} sourceContext={sourceContext} onChange={(next) => setField("group_field", next || undefined)} />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.group_field)].filter(Boolean)} />
          <Field label="Group Order">
            <input value={stringValue(current.group_order)} onChange={(event) => setField("group_order", event.target.value || undefined)} placeholder="optional comma order" style={inputStyle} />
          </Field>
          <Field label="Mode">
            <select value={stringValue(current.mode, "trace")} onChange={(event) => setField("mode", event.target.value)} style={inputStyle}>
              <option value="trace">trace</option>
              <option value="per_sample">per_sample</option>
            </select>
          </Field>
          <Field label="Top N">
            <input type="number" min="1" value={String(current.top_n ?? 10)} onChange={(event) => setField("top_n", Number(event.target.value || 10))} style={inputStyle} />
          </Field>
          <ChainPicker value={current} setField={setField} sourceContext={sourceContext} />
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
