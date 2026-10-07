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
    batch_field: "",
    mode: "trace",
    top_n: 10,
    selected_chains: sourceContext?.chains?.length ? sourceContext.chains : ["TRA", "TRB"],
  });
  const setField = (key: string, next: unknown) => {
    if (current.analysis_type === "igh_subclass_topclone") { setFieldValue(current, onChange, key, next); return; }
    if (key === "batch_field") {
      onChange({ ...current, batch_field: next, selected_samples_by_group: undefined,
        group_sample_identity: next ? "batch_sample" : "sample" });
    } else if (key === "selected_samples_by_group") {
      onChange({ ...current, selected_samples_by_group: next,
        group_sample_identity: current.batch_field ? "batch_sample" : "sample" });
    } else setFieldValue(current, onChange, key, next);
  };
  useSyncedDefaults(value, current, onChange);

  if (current.analysis_type === "igh_subclass_topclone") {
    return (
      <ModuleShell
        title="IGH 免疫球蛋白亚类优势克隆"
        detail="在每个免疫球蛋白亚类内部汇总克隆 copy 数，计算前 10、20、50、100 位克隆占该亚类总 copy 的比例，再进行分组比较。"
        sourceContext={sourceContext}
      >
        <Section title="样本分组">
          <div style={gridStyle}>
            <GroupFieldSelect value={stringValue(current.group_field)} sourceContext={sourceContext} onChange={(next) => setField("group_field", next || undefined)} />
            <GroupFieldSelect
              label="批次字段（可选）"
              value={stringValue(current.batch_field)}
              sourceContext={sourceContext}
              optional
              emptyLabel="未选择批次字段"
              onChange={(next) => setField("batch_field", next || undefined)}
            />
            <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.group_field)].filter(Boolean)} />
            <Field label="分组顺序">
              <input value={stringValue(current.group_order)} onChange={(event) => setField("group_order", event.target.value || undefined)} placeholder="可选，如 健康对照,患者" style={inputStyle} />
            </Field>
          </div>
          <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: "var(--bg-inset)", color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.7 }}>
            <div>存在跨批次同名样本时，请选择批次字段；PEP 文件需位于与批次字段值同名的批次目录中。</div>
            <div>比较所有已选择分组之间的差异；每个亚类 × Top-N 组合分别进行双侧 Mann–Whitney 检验，并在每组比较内统一进行 BH 校正。</div>
            <div>请确保所选 PEP 数据包含 IGH 文件，且文件样本编号能与样本指标表对应。缺少或重复的样本编号会在任务检查时指出。</div>
          </div>
        </Section>
        <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      </ModuleShell>
    );
  }

  return (
    <ModuleShell
      title="优势克隆"
      detail="选择克隆跟踪或逐样本分析模式，并配置样本分组。"
      sourceContext={sourceContext}
    >
      <Section title="克隆排序">
        <div style={gridStyle}>
          <GroupFieldSelect value={stringValue(current.group_field)} sourceContext={sourceContext} onChange={(next) => setField("group_field", next || undefined)} />
          {current.mode === "trace" && <Field label="分组顺序">
            <input value={stringValue(current.group_order)} onChange={(event) => setField("group_order", event.target.value || undefined)} placeholder="可选，按顺序填写并用逗号分隔" style={inputStyle} />
          </Field>}
          <Field label="分析模式">
            <select aria-label="分析模式" value={stringValue(current.mode, "trace")} onChange={(event) => setField("mode", event.target.value)} style={inputStyle}>
              <option value="trace">跟踪记录</option>
              <option value="per_sample">逐样本</option>
            </select>
          </Field>
          <GroupFieldSelect
              label="批次字段（可选）"
              value={stringValue(current.batch_field)}
              sourceContext={sourceContext}
              optional
              emptyLabel="未选择批次字段"
              onChange={(next) => setField("batch_field", next || undefined)}
            />
          <GroupValueSamplePicker batchField={stringValue(current.batch_field)} value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.group_field)].filter(Boolean)} />
          {current.mode === "per_sample" && <Field label="排名前几位">
            <input type="number" min="1" value={String(current.top_n ?? 10)} onChange={(event) => setField("top_n", Number(event.target.value || 10))} style={inputStyle} />
          </Field>}
          <ChainPicker value={current} setField={setField} sourceContext={sourceContext} />
        </div>
      </Section>
      {current.mode === "trace" && (
        <div style={{ padding: 12, borderRadius: 8, background: "var(--bg-inset)", color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.7 }}>
          跟踪模式固定计算前 10、20、50、100 位克隆比例。仅纳入已选择的分组和样本。
          当不同批次存在同名样本时，请选择批次字段；PEP 文件所在批次目录名需与该列取值一致。平台会按“批次 + 样本编号 + 链型”匹配。
        </div>
      )}
      <CommonRunFields showPvalue={current.mode === "trace"} value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
