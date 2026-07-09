import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  CommonRunFields,
  Field,
  ModuleShell,
  PepCacheCardSelector,
  Section,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";
import { ExpressionComparisonFields, useExpressionInspect } from "./expressionHelpers";

type UsageInspectResponse = {
  success: boolean;
  data_dir?: string;
  file_count?: number;
  files?: string[];
};

export function VolcanoConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    input_mode: sourceContext?.transcriptomePath ? "expression" : "usage",
    group_prefix: "tpm_",
    logfc_cutoff: 1,
    comparisons: [],
  });
  const [usageNote, setUsageNote] = useState("");
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);
  const { inspect, note } = useExpressionInspect({ module: "volcano", sourceContext, value: current, onChange });

  useEffect(() => {
    if (current.input_mode !== "usage" || (!sourceContext?.pepPaths?.length && !sourceContext?.projectId && !current.data_dir)) return;
    let cancelled = false;
    inspectScriptHubModule<UsageInspectResponse>("volcano", {
      input_mode: "usage",
      base_path: sourceContext?.pepPaths?.[0],
      data_dir: current.data_dir,
      project_id: sourceContext?.projectId,
    })
      .then((data) => {
        if (cancelled) return;
        if (data.data_dir && !value.data_dir) onChange({ ...current, data_dir: data.data_dir });
        setUsageNote(`Usage inspect found ${data.file_count || 0} usage files.`);
      })
      .catch((error) => {
        if (!cancelled) setUsageNote(error instanceof Error ? error.message : "Usage inspect failed");
      });
    return () => {
      cancelled = true;
    };
  }, [current.input_mode, current.data_dir, sourceContext?.pepPaths?.join("|"), sourceContext?.projectId]);

  return (
    <ModuleShell
      title="Volcano"
      detail="表达矩阵模式自动推导 comparisons；usage 模式使用缓存/目录，不展示手动 feature range。"
      sourceContext={sourceContext}
    >
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      <Section title="Input">
        <div style={gridStyle}>
          <Field label="Input Mode">
            <select value={stringValue(current.input_mode, "expression")} onChange={(event) => setField("input_mode", event.target.value)} style={inputStyle}>
              <option value="expression">expression matrix</option>
              <option value="usage">VJ usage cache</option>
            </select>
          </Field>
          {current.input_mode === "usage" && (
            <PepCacheCardSelector
              sourceContext={sourceContext}
              cacheType="volcano"
              value={stringValue(current.data_dir)}
              label="PEP VJ Usage Cache"
              onSelect={(candidate) => onChange({
                ...current,
                data_dir: candidate.path,
                source_job_id: candidate.job_id || current.source_job_id,
                pep_cache_id: candidate.asset_id || candidate.id,
              })}
            />
          )}
        </div>
      </Section>
      {current.input_mode === "expression" ? (
        <>
          {note && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{note}</div>}
          <Section title="Expression Comparison">
            <ExpressionComparisonFields value={current} onChange={onChange} suggested={inspect?.suggested_comparisons || inspect?.comparisons} />
          </Section>
        </>
      ) : usageNote ? (
        <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{usageNote}</div>
      ) : null}
    </ModuleShell>
  );
}
