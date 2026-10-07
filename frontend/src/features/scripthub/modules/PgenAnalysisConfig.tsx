import { useEffect, useRef, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ChainPicker,
  ColumnSelect,
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

type PgenInspectResponse = {
  success: boolean;
  runnable_chains?: string[];
  sample_column_candidates?: string[];
  distribution_category_candidates?: string[];
  sample_conflicts?: Array<{ sample: string; chain: string }>;
  sonnia?: { available?: boolean; message?: string };
};

export function PgenAnalysisConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspect, setInspect] = useState<PgenInspectResponse | null>(null);
  const [inspectNote, setInspectNote] = useState("");
  const current = withDefaults(value, {
    output_name: "",
    species: "human",
    sample_col: sourceContext?.profileFields?.find((field) => field.toLowerCase() === "sample") || "sample",
    batch_field: "",
    distribution_category_col: "",
    selected_chains: sourceContext?.chains?.filter((chain) => !["TRD", "TRG"].includes(chain)) || ["TRA", "TRB"],
  });
  const latest = useRef({ value, current, onChange });
  latest.current = { value, current, onChange };
  const setField = (key: string, next: unknown) => {
    if (key === "batch_field" || key === "sample_col") {
      onChange({ ...current, [key]: next, selected_samples_by_group: undefined,
        group_sample_identity: (key === "batch_field" ? next : current.batch_field) ? "batch_sample" : "sample" });
    } else if (key === "selected_samples_by_group") {
      onChange({ ...current, selected_samples_by_group: next,
        group_sample_identity: current.batch_field ? "batch_sample" : "sample" });
    } else setFieldValue(current, onChange, key, next);
  };
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    setInspect(null);
    if (!sourceContext?.pepPaths?.length || !sourceContext.profilePath) { setInspectNote(""); return; }
    let cancelled = false;
    setInspectNote("正在检查生成概率输入…");
    inspectScriptHubModule<PgenInspectResponse>("pgen-analysis", {
      pep_paths: sourceContext.pepPaths,
      base_path: sourceContext.pepPaths[0],
      profile_path: sourceContext.profilePath,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const { value: latestValue, current: latestCurrent, onChange: latestOnChange } = latest.current;
        const defaults: Record<string, unknown> = {};
        if (!latestValue.selected_chains && data.runnable_chains?.length) defaults.selected_chains = data.runnable_chains;
        if (!latestValue.sample_col && data.sample_column_candidates?.[0]) defaults.sample_col = data.sample_column_candidates[0];
        if (!latestValue.distribution_category_col && data.distribution_category_candidates?.[0]) {
          defaults.distribution_category_col = data.distribution_category_candidates[0];
        }
        if (Object.keys(defaults).length) latestOnChange({ ...latestCurrent, ...defaults });
        setInspectNote(data.sonnia?.message || "已读取可分析的链类型和样本指标候选列。");
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "生成概率输入检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.pepPaths?.join("|"), sourceContext?.profilePath]);

  return (
    <ModuleShell
      title="生成概率分析"
      detail="配置生成概率分析参数，并从样本指标表中选择样本列和分类列。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="生成概率参数">
        <div style={gridStyle}>
          <GroupFieldSelect label="分布分类列" value={stringValue(current.distribution_category_col)} sourceContext={sourceContext} onChange={(next) => setField("distribution_category_col", next || undefined)} />
          <ColumnSelect label="样本列" value={stringValue(current.sample_col, "sample")} options={inspect?.sample_column_candidates || sourceContext?.profileFields || []} onChange={(next) => setField("sample_col", next || "sample")} emptyLabel="未识别到样本指标表的列" />
          <GroupFieldSelect
            label="批次字段（可选）"
            value={stringValue(current.batch_field)}
            sourceContext={sourceContext}
            optional
            emptyLabel="未选择批次字段"
            onChange={(next) => setField("batch_field", next || undefined)}
          />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.distribution_category_col)].filter(Boolean)} batchField={stringValue(current.batch_field) || undefined} sampleColumn={stringValue(current.sample_col, "sample")} />
          <ChainPicker value={current} setField={setField} sourceContext={{ ...(sourceContext || { sampleNames: [], chains: [], profileFields: [], groupFields: [], pepColumns: [] }), chains: inspect?.runnable_chains || sourceContext?.chains || [] }} disabled={["TRD", "TRG"]} />
          <Field label="物种">
            <select value={stringValue(current.species, "human")} onChange={(event) => setField("species", event.target.value)} style={inputStyle}>
              <option value="human">人</option>
              <option value="mouse">小鼠</option>
            </select>
          </Field>
        </div>
        <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: "var(--bg-inset)", color: "var(--text-secondary)", fontSize: "0.82rem", lineHeight: 1.7 }}>
          <div>分析会读取当前选择的全部 PEP 文件。若不同批次有同名样本，请选择批次字段，且 PEP 文件的批次目录名需与该字段值一致。可分别选择同名样本的不同批次；更换样本列或批次字段后请重新确认各组样本。</div>
          {inspect?.sample_conflicts?.length ? <div>已发现 {inspect.sample_conflicts.length} 组同名样本与链型；提交前请确认批次字段及目录结构。</div> : null}
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
