import { useEffect, useRef, useState } from "react";
import { UmapinSampleSelection } from "./UmapinSampleSelection";
import type { ScriptHubSourceContext } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ChipPicker,
  Field,
  gridStyle,
  inputStyle,
  listInput,
  miniButtonStyle,
  setFieldValue,
  splitList,
  stringValue,
} from "./shared";

type ExpressionInspectResponse = {
  success: boolean;
  suggested_comparisons?: unknown[];
  comparisons?: unknown[];
  groups?: string[];
  sample_count?: number;
  samples_by_value?: Record<string, string[]>;
  group_names?: string[];
  columns?: string[];
  file_count?: number;
  files?: string[];
};

export function useExpressionInspect({
  module,
  enabled = true,
  sourceContext,
  value,
  onChange,
}: {
  module: "volcano" | "go-kegg-enrichment";
  enabled?: boolean;
  sourceContext?: ScriptHubSourceContext;
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const [inspect, setInspect] = useState<ExpressionInspectResponse | null>(null);
  const [note, setNote] = useState("");
  const latest = useRef({ value, onChange });
  latest.current = { value, onChange };
  const groupPrefix = stringValue(value.group_prefix, "tpm_");

  useEffect(() => {
    if (!enabled || !sourceContext?.transcriptomePath) { setInspect(null); setNote(""); return; }
    setInspect(null);
    setNote("正在检查表达数据分组…");
    let cancelled = false;
    inspectScriptHubModule<ExpressionInspectResponse>(module, {
      input_mode: "expression",
      project_id: sourceContext.projectId, asset_set: sourceContext.assetSetId,
      expression_path: sourceContext.transcriptomePath,
      transcriptome_path: sourceContext.transcriptomePath,
      group_prefix: groupPrefix,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const suggestions = comparisonKeys(data.suggested_comparisons || data.comparisons);
        const { value: active, onChange: update } = latest.current;
        const defaults: Record<string, unknown> = {};
        if (suggestions.length && active.comparisons === undefined) defaults.comparisons = suggestions;
        if (data.samples_by_value && !Array.isArray(active.selected_expression_samples)) defaults.selected_expression_samples = Object.values(data.samples_by_value).flat();
        if (Object.keys(defaults).length) update({ ...active, ...defaults });
        setNote(`表达数据检查已读取 ${(data.groups || data.group_names || []).length} 个分组，共 ${suggestions.length} 个比较组合。`);
      })
      .catch((error) => {
        if (!cancelled) setNote(error instanceof Error ? error.message : "表达数据检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [module, enabled, sourceContext?.transcriptomePath, sourceContext?.projectId, sourceContext?.assetSetId, groupPrefix]);

  return { inspect, note };
}

export function ExpressionSampleSelection({ value, onChange, groups }: {
  value: Record<string, unknown>; onChange: (next: Record<string, unknown>) => void; groups?: Record<string, string[]>;
}) {
  if (!groups) return null;
  return <UmapinSampleSelection groups={groups} title="表达样本范围" sampleLabel="表达样本"
    description="选择表达矩阵中的真实样本列。全部所选样本参与归一化，各组间比较仅由对应两组拟合；每组至少保留两个样本。"
    value={{ selected_categories: value.selected_expression_groups, selected_samples: value.selected_expression_samples }}
    onChange={next => {
      const categories = Array.isArray(next.selected_categories) ? next.selected_categories.map(String) : Object.keys(groups);
      const samples = Array.isArray(next.selected_samples) ? next.selected_samples.map(String) : Object.values(groups).flat();
      const active = new Set(categories.filter(group => (groups[group] || []).some(sample => samples.includes(sample))));
      onChange({ ...value, selected_expression_groups: next.selected_categories, selected_expression_samples: next.selected_samples,
        comparisons: value.comparisons === undefined ? undefined : comparisonKeys(value.comparisons as unknown[]).filter(key => key.split("_vs_").every(group => active.has(group))) });
    }} />;
}

export function ExpressionComparisonFields({
  value,
  onChange,
  suggested,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
  suggested?: unknown[];
}) {
  const comparisons = comparisonKeys(value.comparisons as unknown[]);
  const availableGroups = Array.isArray(value.selected_expression_groups) ? value.selected_expression_groups.map(String) : null;
  const suggestions = comparisonKeys(suggested).filter(key => !availableGroups || key.split("_vs_").every(group => availableGroups.includes(group)))
    .map(key => { const reversed = key.split("_vs_").reverse().join("_vs_"); return comparisons.includes(reversed) ? reversed : key; });
  const setField = (key: string, next: unknown) => setFieldValue(value, onChange, key, next);
  return (
    <div style={gridStyle}>
      <Field label="分组前缀">
        <input value={stringValue(value.group_prefix, "tpm_")} onChange={(event) => onChange({ ...value, group_prefix: event.target.value || "tpm_", comparisons: undefined, selected_expression_groups: undefined, selected_expression_samples: undefined })} style={inputStyle} />
      </Field>
      {suggestions.length ? (
        <div style={{ display: "grid", gap: 8 }}><ChipPicker
          label="比较组合"
          selected={comparisons}
          options={suggestions.map((item) => ({ key: item, label: item }))}
          onToggle={(next) => setField("comparisons", next)}
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {comparisons.map(key => <button key={key} type="button" style={miniButtonStyle} aria-label={`交换 ${key} 的比较方向`}
            onClick={() => setField("comparisons", comparisons.map(item => item === key ? item.split("_vs_").reverse().join("_vs_") : item))}>
            {key.replace("_vs_", " / ")} · 交换方向
          </button>)}
        </div><div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>比较顺序为前组 / 后组，正值表示前组较高。</div></div>
      ) : (
        <Field label="比较组合">
          <input value={listInput(value.comparisons)} onChange={(event) => setField("comparisons", splitList(event.target.value))} placeholder="A_vs_B, C_vs_D" style={inputStyle} />
        </Field>
      )}
      <Field label="对数倍数变化阈值">
        <input type="number" min="0" step="0.1" value={String(value.logfc_cutoff ?? 1)} onChange={(event) => setField("logfc_cutoff", Number(event.target.value))} style={inputStyle} />
      </Field>
    </div>
  );
}

function comparisonKeys(items?: unknown[]) {
  if (!Array.isArray(items)) return [];
  return items
    .map((item) => {
      if (Array.isArray(item)) return item.map((part) => String(part || "").trim()).filter(Boolean).join("_vs_");
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        const left = record.group1 || record.group_a || record.a || record.case || record.treatment || record.left;
        const right = record.group2 || record.group_b || record.b || record.control || record.right;
        if (left && right) return `${left}_vs_${right}`;
        if (record.name) return String(record.name);
      }
      return String(item || "").trim();
    })
    .filter(Boolean);
}
