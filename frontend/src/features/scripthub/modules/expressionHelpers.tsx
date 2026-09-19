import { useEffect, useState } from "react";
import type { ScriptHubSourceContext } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ChipPicker,
  Field,
  gridStyle,
  inputStyle,
  listInput,
  setFieldValue,
  splitList,
  stringList,
  stringValue,
} from "./shared";

type ExpressionInspectResponse = {
  success: boolean;
  suggested_comparisons?: unknown[];
  comparisons?: unknown[];
  groups?: string[];
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
  const groupPrefix = stringValue(value.group_prefix, "tpm_");

  useEffect(() => {
    if (!enabled || !sourceContext?.transcriptomePath) { setInspect(null); setNote(""); return; }
    let cancelled = false;
    inspectScriptHubModule<ExpressionInspectResponse>(module, {
      input_mode: "expression",
      expression_path: sourceContext.transcriptomePath,
      transcriptome_path: sourceContext.transcriptomePath,
      group_prefix: groupPrefix,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const suggestions = comparisonKeys(data.suggested_comparisons || data.comparisons);
        if (suggestions.length && !stringList(value.comparisons).length) {
          onChange({ ...value, comparisons: suggestions });
        }
        setNote(`表达数据检查已读取 ${(data.groups || data.group_names || []).length} 个分组，共 ${suggestions.length} 个比较组合。`);
      })
      .catch((error) => {
        if (!cancelled) setNote(error instanceof Error ? error.message : "表达数据检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [module, enabled, sourceContext?.transcriptomePath, groupPrefix]);

  return { inspect, note };
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
  const comparisons = stringList(value.comparisons);
  const suggestions = comparisonKeys(suggested);
  const setField = (key: string, next: unknown) => setFieldValue(value, onChange, key, next);
  return (
    <div style={gridStyle}>
      <Field label="分组前缀">
        <input value={stringValue(value.group_prefix, "tpm_")} onChange={(event) => setField("group_prefix", event.target.value || "tpm_")} style={inputStyle} />
      </Field>
      {suggestions.length ? (
        <ChipPicker
          label="比较组合"
          selected={comparisons}
          options={suggestions.map((item) => ({ key: item, label: item }))}
          onToggle={(next) => setField("comparisons", next)}
        />
      ) : (
        <Field label="比较组合">
          <input value={listInput(value.comparisons)} onChange={(event) => setField("comparisons", splitList(event.target.value))} placeholder="A_vs_B, C_vs_D" style={inputStyle} />
        </Field>
      )}
      <Field label="对数倍数变化阈值">
        <input type="number" min="0" step="0.1" value={String(value.logfc_cutoff ?? 1)} onChange={(event) => setField("logfc_cutoff", Number(event.target.value || 1))} style={inputStyle} />
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
