import { DifferentialSourceSelector } from "./DifferentialSourceSelector";
import type { ModuleFormProps } from "../../jobs/forms";
import {
  CommonRunFields,
  Field,
  ModuleShell,
  Section,
  SwitchField,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";
import { ExpressionComparisonFields, useExpressionInspect } from "./expressionHelpers";

export function GoKeggConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    input_mode: "expression",
    pvalue_threshold: 0.05,
    group_prefix: "tpm_",
    logfc_cutoff: 1,
    comparisons: [],
    enrich_pvalue_cutoff: 0.05,
    p_adjust_method: "none",
    show_category: 20,
    simplify_go: true,
    do_gsea: true,
  });
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);
  const reuse = current.input_mode === "deg";
  const { inspect, note } = useExpressionInspect({ enabled: !reuse, module: "go-kegg-enrichment", sourceContext, value: current, onChange });

  return (
    <ModuleShell
      title="基因功能与通路富集"
      detail="选择表达矩阵或已有差异表达结果，再配置功能富集参数。"
      sourceContext={sourceContext}
    >
      <Section title="分析来源">
        <Field label="输入方式"><select aria-label="输入方式" style={inputStyle} value={reuse ? "deg" : "expression"} onChange={event => onChange({...current, input_mode:event.target.value, upstream_artifact_id:undefined})}>
          <option value="expression">从表达矩阵计算差异后富集</option>
          <option value="deg">复用已完成的差异表达结果</option>
        </select></Field>
        {reuse && <DifferentialSourceSelector sourceContext={sourceContext} value={stringValue(current.upstream_artifact_id)} onSelect={id => setField("upstream_artifact_id", id || undefined)} />}
      </Section>
      {reuse ? <Field label="输出名称"><input style={inputStyle} value={stringValue(current.output_name)} onChange={event => setField("output_name", event.target.value)} placeholder="默认使用任务名称" /></Field> : <>
        <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
        {note && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{note}</div>}
        <Section title="表达差异比较">
          <ExpressionComparisonFields value={current} onChange={onChange} suggested={inspect?.suggested_comparisons || inspect?.comparisons} />
        </Section>
      </>}
      <Section title="富集分析">
        <div style={gridStyle}>
          <Field label="富集分析 p 值阈值">
            <input type="number" min="0" max="1" step="0.001" value={String(current.enrich_pvalue_cutoff ?? 0.05)} onChange={(event) => setField("enrich_pvalue_cutoff", Number(event.target.value || 0.05))} style={inputStyle} />
          </Field>
          <Field label="多重检验校正方法">
            <select value={stringValue(current.p_adjust_method, "none")} onChange={(event) => setField("p_adjust_method", event.target.value)} style={inputStyle}>
              <option value="none">无</option>
              <option value="BH">BH</option>
              <option value="BY">BY</option>
              <option value="holm">holm</option>
              <option value="bonferroni">bonferroni</option>
            </select>
          </Field>
          <Field label="展示条目数">
            <input type="number" min="1" value={String(current.show_category ?? 20)} onChange={(event) => setField("show_category", Number(event.target.value || 20))} style={inputStyle} />
          </Field>
          <SwitchField label="合并冗余功能条目" checked={Boolean(current.simplify_go)} onChange={(checked) => setField("simplify_go", checked)} />
          <SwitchField label="运行基因集富集分析" checked={Boolean(current.do_gsea)} onChange={(checked) => setField("do_gsea", checked)} />
        </div>
      </Section>
    </ModuleShell>
  );
}
