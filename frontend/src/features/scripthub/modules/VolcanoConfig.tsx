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

export function VolcanoConfig({ sourceContext, value, onChange, fixedParameters }: ModuleFormProps) {
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
      data_dir: current.upstream_artifact_id ? undefined : current.data_dir,
      project_id: sourceContext?.projectId,
      asset_set: sourceContext?.assetSetId,
      upstream_artifact_id: current.upstream_artifact_id,
    })
      .then((data) => {
        if (cancelled) return;
        if (data.data_dir && !value.data_dir) onChange({ ...current, data_dir: data.data_dir });
        setUsageNote(`基因使用数据检查找到 ${data.file_count || 0} 个基因使用文件。`);
      })
      .catch((error) => {
        if (!cancelled) setUsageNote(error instanceof Error ? error.message : "基因使用数据检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [current.input_mode, current.data_dir, sourceContext?.pepPaths?.join("|"), sourceContext?.projectId]);

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
              })}
            />
          )}
        </div>
      </Section>
      {current.input_mode === "expression" ? (
        <>
          {note && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{note}</div>}
          <Section title="表达差异比较">
            <ExpressionComparisonFields value={current} onChange={onChange} suggested={inspect?.suggested_comparisons || inspect?.comparisons} />
          </Section>
        </>
      ) : usageNote ? (
        <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{usageNote}</div>
      ) : null}
    </ModuleShell>
  );
}
