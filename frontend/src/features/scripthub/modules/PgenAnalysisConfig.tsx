import { useEffect, useState } from "react";
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
  sonnia?: { available?: boolean; message?: string };
};

export function PgenAnalysisConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspect, setInspect] = useState<PgenInspectResponse | null>(null);
  const [inspectNote, setInspectNote] = useState("");
  const current = withDefaults(value, {
    output_name: "",
    species: "human",
    sample_col: sourceContext?.profileFields?.find((field) => field.toLowerCase() === "sample") || "sample",
    distribution_category_col: "",
    selected_chains: sourceContext?.chains?.filter((chain) => !["TRD", "TRG"].includes(chain)) || ["TRA", "TRB"],
  });
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (!sourceContext?.pepPaths?.length || !sourceContext.profilePath) return;
    let cancelled = false;
    inspectScriptHubModule<PgenInspectResponse>("pgen-analysis", {
      pep_paths: sourceContext.pepPaths,
      base_path: sourceContext.pepPaths[0],
      profile_path: sourceContext.profilePath,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const defaults: Record<string, unknown> = {};
        if (!value.selected_chains && data.runnable_chains?.length) defaults.selected_chains = data.runnable_chains;
        if (!value.sample_col && data.sample_column_candidates?.[0]) defaults.sample_col = data.sample_column_candidates[0];
        if (!value.distribution_category_col && data.distribution_category_candidates?.[0]) {
          defaults.distribution_category_col = data.distribution_category_candidates[0];
        }
        if (Object.keys(defaults).length) onChange({ ...current, ...defaults });
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
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.distribution_category_col)].filter(Boolean)} />
          <ColumnSelect label="样本列" value={stringValue(current.sample_col, "sample")} options={inspect?.sample_column_candidates || sourceContext?.profileFields || []} onChange={(next) => setField("sample_col", next || "sample")} emptyLabel="未识别到样本指标表的列" />
          <ChainPicker value={current} setField={setField} sourceContext={{ ...(sourceContext || { sampleNames: [], chains: [], profileFields: [], groupFields: [], pepColumns: [] }), chains: inspect?.runnable_chains || sourceContext?.chains || [] }} disabled={["TRD", "TRG"]} />
          <Field label="物种">
            <select value={stringValue(current.species, "human")} onChange={(event) => setField("species", event.target.value)} style={inputStyle}>
              <option value="human">人</option>
              <option value="mouse">小鼠</option>
            </select>
          </Field>
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
