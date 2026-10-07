import { useEffect, useRef } from "react";
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
import { ExpressionComparisonFields, ExpressionSampleSelection, useExpressionInspect } from "./expressionHelpers";

export function GoKeggConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    input_mode: "expression",
    pvalue_threshold: 0.05,
    group_prefix: "tpm_",
    logfc_cutoff: 1,
    enrich_pvalue_cutoff: 0.05,
    p_adjust_method: "BH",
    show_category: 10,
    simplify_go: false,
    do_gsea: true,
  });
  const latest = useRef({ current, onChange });
  latest.current = { current, onChange };
  const sourceKey = `${sourceContext?.projectId || ""}:${sourceContext?.assetSetId || ""}:${sourceContext?.transcriptomePath || ""}`;
  const priorSource = useRef(sourceKey);
  useEffect(() => {
    if (priorSource.current === sourceKey) return;
    priorSource.current = sourceKey;
    const { current: active, onChange: update } = latest.current;
    update({ ...active, upstream_artifact_id: undefined, comparisons: undefined, selected_expression_groups: undefined, selected_expression_samples: undefined });
  }, [sourceKey]);
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
        <Field label="输入方式"><select aria-label="输入方式" style={inputStyle} value={reuse ? "deg" : "expression"} onChange={event => onChange({...current, input_mode:event.target.value, upstream_artifact_id:undefined, comparisons:undefined, selected_expression_groups:undefined, selected_expression_samples:undefined})}>
          <option value="expression">从表达矩阵计算差异后富集</option>
          <option value="deg">复用已完成的差异表达结果</option>
        </select></Field>
        {reuse && <DifferentialSourceSelector sourceContext={sourceContext} value={stringValue(current.upstream_artifact_id)} onSelect={id => setField("upstream_artifact_id", id || undefined)} />}
      </Section>
      {reuse ? <Field label="输出名称"><input style={inputStyle} value={stringValue(current.output_name)} onChange={event => setField("output_name", event.target.value)} placeholder="默认使用任务名称" /></Field> : <>
        <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
        {note && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{note}</div>}
        <ExpressionSampleSelection groups={inspect?.samples_by_value} value={current} onChange={onChange} />
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
            <select value={stringValue(current.p_adjust_method, "BH")} onChange={(event) => setField("p_adjust_method", event.target.value)} style={inputStyle}>
              <option value="none">无</option>
              <option value="BH">BH（控制假发现率）</option>
              <option value="BY">BY（控制假发现率）</option>
              <option value="holm">Holm（逐步校正）</option>
              <option value="bonferroni">Bonferroni（控制家族错误率）</option>
            </select>
          </Field>
          <Field label="展示条目数">
            <input type="number" min="1" value={String(current.show_category ?? 10)} onChange={(event) => setField("show_category", Number(event.target.value || 10))} style={inputStyle} />
          </Field>
          <SwitchField label="合并冗余 GO 条目（仅影响图表）" checked={Boolean(current.simplify_go)} onChange={(checked) => setField("simplify_go", checked)} />
          <SwitchField label="运行基因集富集分析" checked={Boolean(current.do_gsea)} onChange={(checked) => setField("do_gsea", checked)} />
        </div>
        <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
          默认按上调、下调和合并差异基因分别进行 ORA；GO 使用 BP（生物过程）本体，采用当前选择的校正方法。结果表保留完整条目，阈值仅用于图表筛选。
        </div>
      </Section>
    </ModuleShell>
  );
}
