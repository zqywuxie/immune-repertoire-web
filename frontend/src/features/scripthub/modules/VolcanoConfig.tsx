import { useEffect, useRef, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ChipPicker,
  CommonRunFields,
  Field,
  ModuleShell,
  PepCacheCardSelector,
  Section,
  gridStyle,
  inputStyle,
  miniButtonStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";
import { UmapinSampleSelection } from "./UmapinSampleSelection";
import { ExpressionComparisonFields, ExpressionSampleSelection, useExpressionInspect } from "./expressionHelpers";

type UsageInspectResponse = {
  success: boolean;
  data_dir?: string;
  file_count?: number;
  files?: string[];
  groups?: string[];
  sample_count?: number;
  samples_by_value?: Record<string, string[]>;
  group_counts?: Record<string, number>;
  suggested_comparisons?: Array<{ group1: string; group2: string }>;
};

export function VolcanoConfig({ sourceContext, value, onChange, fixedParameters }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    input_mode: sourceContext?.transcriptomePath ? "expression" : "usage",
    group_prefix: "tpm_",
    logfc_cutoff: 1,
  });
  const [usageNote, setUsageNote] = useState("");
  const [usageInspect, setUsageInspect] = useState<UsageInspectResponse | null>(null);
  const latest = useRef({ current, onChange });
  latest.current = { current, onChange };
  const sourceKey = `${sourceContext?.projectId || ""}:${sourceContext?.assetSetId || ""}:${sourceContext?.transcriptomePath || ""}`;
  const priorSource = useRef(sourceKey);
  useEffect(() => {
    if (priorSource.current === sourceKey) return;
    priorSource.current = sourceKey;
    const { current: active, onChange: update } = latest.current;
    update({ ...active, data_dir: undefined, upstream_artifact_id: undefined, source_job_id: undefined,
      pep_cache_id: undefined, usage_inspect_ok: false, comparisons: undefined, selected_samples: undefined, selected_categories: undefined, selected_expression_samples: undefined, selected_expression_groups: undefined });
  }, [sourceKey]);
  const setField = (key: string, next: unknown) => {
    if (key === "input_mode" || key === "group_prefix") onChange({ ...current, [key]: next,
      usage_inspect_ok: false, comparisons: undefined, selected_categories: undefined, selected_samples: undefined, selected_expression_samples: undefined, selected_expression_groups: undefined });
    else setFieldValue(current, onChange, key, next);
  };
  useSyncedDefaults(value, current, onChange);
  const { inspect, note } = useExpressionInspect({ module: "volcano", enabled: current.input_mode === "expression", sourceContext, value: current, onChange });

  useEffect(() => {
    setUsageInspect(null);
    setUsageNote("请选择前置结果以检查实际样本与分组。");
    if (current.input_mode !== "usage") return;
    const {current: active, onChange: update} = latest.current;
    if (active.usage_inspect_ok !== false) update({...active, usage_inspect_ok: false});
    if (sourceContext?.projectId && sourceContext?.assetSetId && !current.upstream_artifact_id && !current.data_dir) return;
    if (!sourceContext?.pepPaths?.length && !sourceContext?.projectId && !current.data_dir) return;
    setUsageNote("正在检查基因使用表与实际样本…");
    let cancelled = false;
    setUsageInspect(null);
    inspectScriptHubModule<UsageInspectResponse>("volcano", {
      input_mode: "usage",
      base_path: sourceContext?.pepPaths?.[0],
      data_dir: current.upstream_artifact_id ? undefined : current.data_dir,
      project_id: sourceContext?.projectId,
      asset_set: sourceContext?.assetSetId,
      upstream_artifact_id: current.upstream_artifact_id,
    })
      .then((data) => {
        if (cancelled) return;
        setUsageInspect(data);
        const { current: active, onChange: update } = latest.current;
        const defaults: Record<string, unknown> = {usage_inspect_ok: true};
        if (data.data_dir && !active.data_dir) defaults.data_dir = data.data_dir;
        if (active.comparisons === undefined) defaults.comparisons = (data.suggested_comparisons || []).map(pair => [pair.group1, pair.group2]);
        if (!Array.isArray(active.selected_samples) && data.samples_by_value) defaults.selected_samples = Object.values(data.samples_by_value).flat();
        if (Object.keys(defaults).length) update({ ...active, ...defaults });
        setUsageNote(`已读取 ${data.file_count || 0} 个文件、${data.sample_count || 0} 个样本、${(data.groups || []).length} 个分组。请选择样本范围与比较方向。`);
      })
      .catch((error) => {
        if (!cancelled) setUsageNote(error instanceof Error ? error.message : "基因使用数据检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [current.input_mode, current.upstream_artifact_id, current.upstream_artifact_id ? undefined : current.data_dir, sourceContext?.pepPaths?.join("|"), sourceContext?.projectId, sourceContext?.assetSetId]);

  const groups = usageInspect?.samples_by_value || {};
  const categories = Array.isArray(current.selected_categories) ? current.selected_categories.map(String) : Object.keys(groups);
  const samples = Array.isArray(current.selected_samples) ? current.selected_samples.map(String) : Object.values(groups).flat();
  const activeGroups = new Set(categories.filter(group => (groups[group] || []).some(sample => samples.includes(sample))));
  const suggested = (usageInspect?.suggested_comparisons || []).filter(pair => activeGroups.has(pair.group1) && activeGroups.has(pair.group2));
  const chosenPairs = normalizePairs(current.comparisons);
  const shownPairs = suggested.map(pair => chosenPairs.find(chosen => chosen[0] === pair.group2 && chosen[1] === pair.group1)
    || [pair.group1, pair.group2] as [string, string]);
  const setScope = (next: Record<string, unknown>) => {
    const categories = Array.isArray(next.selected_categories) ? next.selected_categories.map(String) : Object.keys(groups);
    const samples = Array.isArray(next.selected_samples) ? next.selected_samples.map(String) : Object.values(groups).flat();
    const active = new Set(categories.filter(group => (groups[group] || []).some(sample => samples.includes(sample))));
    onChange({ ...next, comparisons: normalizePairs(next.comparisons).filter(pair => active.has(pair[0]) && active.has(pair[1])) });
  };

  return (
    <ModuleShell
      title="差异分析"
      detail="使用表达矩阵配置组间比较，或选择已有的基因使用缓存进行差异分析。"
      sourceContext={sourceContext}
    >
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      <Section title="输入数据">
        <div style={gridStyle}>
          {!fixedParameters?.input_mode && <Field label="输入模式">
            <select value={stringValue(current.input_mode, "expression")} onChange={(event) => setField("input_mode", event.target.value)} style={inputStyle}>
              <option value="expression">表达矩阵</option>
              <option value="usage">V/J 基因使用缓存</option>
            </select>
          </Field>}
          {current.input_mode === "usage" && (
            <PepCacheCardSelector
              sourceContext={sourceContext}
              cacheType="volcano"
              value={stringValue(current.upstream_artifact_id || current.data_dir)}
              label="V/J 基因使用分析结果"
              onSelect={(candidate) => onChange({
                ...current,
                data_dir: candidate.path,
                source_job_id: candidate.job_id || current.source_job_id,
                pep_cache_id: candidate.asset_id || candidate.id,
                upstream_artifact_id: candidate.artifact_id,
                usage_inspect_ok: false,
                comparisons: undefined, selected_categories: undefined, selected_samples: undefined,
              })}
            />
          )}
        </div>
      </Section>
      {current.input_mode === "usage" && usageInspect?.samples_by_value && <UmapinSampleSelection groups={groups} value={current} onChange={setScope} title="差异分析样本范围" sampleLabel="分析样本" />}
      {current.input_mode === "usage" && usageInspect && (
        <Section title="使用量组间比较">
          {shownPairs.length ? (
            <>
              <ChipPicker
                label="选择比较组合"
                selected={chosenPairs.map(pairKey)}
                options={shownPairs.map(pair => ({ key: pairKey(pair), label: `${pair[0]} 与 ${pair[1]}` }))}
                onToggle={(keys) => setField("comparisons", keys.map((key) => JSON.parse(key) as [string, string]))}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                {chosenPairs.filter(pair => activeGroups.has(pair[0]) && activeGroups.has(pair[1])).map(pair => <button
                  key={pairKey(pair)} type="button" style={miniButtonStyle} aria-label={`交换 ${pair[0]} 与 ${pair[1]} 的比较方向`}
                  onClick={() => setField("comparisons", chosenPairs.map(item => pairKey(item) === pairKey(pair) ? [pair[1], pair[0]] : item))}>
                  {pair[0]} / {pair[1]} · 交换方向
                </button>)}
              </div>
              <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>
                使用双侧秩和检验；按原始 P 值判定显著性，同时提供 BH 校正值。至少一组有 3 个非零样本时才标记显著。比较顺序为前组 / 后组，正值表示前组较高。
              </div>
            </>
          ) : (
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>所选样本少于两个有效分组，无法进行组间比较。</div>
          )}
        </Section>
      )}
      {current.input_mode === "expression" ? (
        <>
          {note && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{note}</div>}
          <ExpressionSampleSelection groups={inspect?.samples_by_value} value={current} onChange={onChange} />
          <Section title="表达差异比较">
            <ExpressionComparisonFields value={current} onChange={onChange} suggested={inspect?.suggested_comparisons || inspect?.comparisons} />
            <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
              TPM 按 log2(TPM+1) 转换并进行分位数归一化，使用 limma 质量加权线性模型。结果同时提供原始 P 值与 BH-FDR；显著基因及后续 GO/GSEA 默认按 FDR 判定。火山图颜色、纵轴和阈值线沿用原始 P 值，FDR 判定请查看结果表。
            </div>
          </Section>
        </>
      ) : usageNote ? (
        <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{usageNote}</div>
      ) : null}
    </ModuleShell>
  );
}

function normalizePairs(value: unknown): Array<[string, string]> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (Array.isArray(item) && item.length >= 2) {
      const pair: [string, string] = [String(item[0] || "").trim(), String(item[1] || "").trim()];
      return pair[0] && pair[1] && pair[0] !== pair[1] ? [pair] : [];
    }
    if (item && typeof item === "object") {
      const row = item as Record<string, unknown>;
      const pair: [string, string] = [String(row.group1 || "").trim(), String(row.group2 || "").trim()];
      return pair[0] && pair[1] && pair[0] !== pair[1] ? [pair] : [];
    }
    return [];
  });
}

function pairKey(pair: [string, string]) {
  return JSON.stringify(pair);
}
