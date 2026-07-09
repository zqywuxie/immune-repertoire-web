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
  const { inspect, note } = useExpressionInspect({ module: "go-kegg-enrichment", sourceContext, value: current, onChange });

  return (
    <ModuleShell
      title="GO / KEGG Enrichment"
      detail="表达矩阵分组和 comparisons 由后端 inspect 推导，富集参数保持旧版脚本配置。"
      sourceContext={sourceContext}
    >
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      {note && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{note}</div>}
      <Section title="Expression Comparison">
        <ExpressionComparisonFields value={current} onChange={onChange} suggested={inspect?.suggested_comparisons || inspect?.comparisons} />
      </Section>
      <Section title="Enrichment">
        <div style={gridStyle}>
          <Field label="Enrichment P Value">
            <input type="number" min="0" max="1" step="0.001" value={String(current.enrich_pvalue_cutoff ?? 0.05)} onChange={(event) => setField("enrich_pvalue_cutoff", Number(event.target.value || 0.05))} style={inputStyle} />
          </Field>
          <Field label="P Adjust Method">
            <select value={stringValue(current.p_adjust_method, "none")} onChange={(event) => setField("p_adjust_method", event.target.value)} style={inputStyle}>
              <option value="none">none</option>
              <option value="BH">BH</option>
              <option value="BY">BY</option>
              <option value="holm">holm</option>
              <option value="bonferroni">bonferroni</option>
            </select>
          </Field>
          <Field label="Show Category">
            <input type="number" min="1" value={String(current.show_category ?? 20)} onChange={(event) => setField("show_category", Number(event.target.value || 20))} style={inputStyle} />
          </Field>
          <SwitchField label="Simplify GO" checked={Boolean(current.simplify_go)} onChange={(checked) => setField("simplify_go", checked)} />
          <SwitchField label="Run GSEA" checked={Boolean(current.do_gsea)} onChange={(checked) => setField("do_gsea", checked)} />
        </div>
      </Section>
    </ModuleShell>
  );
}
