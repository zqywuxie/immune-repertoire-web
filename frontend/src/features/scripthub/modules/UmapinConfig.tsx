import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ColumnSelect,
  CommonRunFields,
  Field,
  ModuleShell,
  PepCacheCardSelector,
  Section,
  SwitchField,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type UmapinInspectResponse = {
  success: boolean;
  data_path?: string;
  columns?: string[];
  category_col?: string;
  suggested_param_begin?: string;
  suggested_param_over?: string;
};

export function UmapinConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspect, setInspect] = useState<UmapinInspectResponse | null>(null);
  const [inspectNote, setInspectNote] = useState("");
  const current = withDefaults(value, {
    output_name: "",
    category_col: "Category",
    n_neighbors: 6,
    min_dist: 0.01,
    do_fdr: false,
  });
  const columns = inspect?.columns || [];
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (!sourceContext?.pepPaths?.length && !sourceContext?.projectId && !current.data_path) return;
    let cancelled = false;
    inspectScriptHubModule<UmapinInspectResponse>("umapin", {
      data_path: current.upstream_artifact_id ? undefined : current.data_path,
      base_path: sourceContext?.pepPaths?.[0],
      project_id: sourceContext?.projectId,
      asset_set: sourceContext?.assetSetId,
      upstream_artifact_id: current.upstream_artifact_id,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const defaults: Record<string, unknown> = {};
        if (!value.data_path && data.data_path) defaults.data_path = data.data_path;
        if (!value.category_col && data.category_col) defaults.category_col = data.category_col;
        if (!value.param_begin && data.suggested_param_begin) defaults.param_begin = data.suggested_param_begin;
        if (!value.param_over && data.suggested_param_over) defaults.param_over = data.suggested_param_over;
        if (Object.keys(defaults).length) onChange({ ...current, ...defaults });
        setInspectNote(`特征降维检查已读取 ${data.columns?.length || 0} 列基因使用数据。`);
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "特征降维输入检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.pepPaths?.join("|"), sourceContext?.projectId, sourceContext?.assetSetId, current.upstream_artifact_id, current.data_path]);

  return (
    <ModuleShell
      title="特征降维"
      detail="选择基因使用汇总表，并配置分类列、指标范围及降维参数。"
      sourceContext={sourceContext}
    >
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="基因使用数据表">
        <div style={gridStyle}>
          <PepCacheCardSelector
            sourceContext={sourceContext}
            cacheType="umapin"
            value={stringValue(current.upstream_artifact_id || current.data_path)}
            label="克隆特征分析结果"
            onSelect={(candidate) => onChange({
              ...current,
              data_path: candidate.path,
              source_job_id: candidate.job_id || current.source_job_id,
              pep_cache_id: candidate.asset_id || candidate.id,
                upstream_artifact_id: candidate.artifact_id,
            })}
          />
          <ColumnSelect label="分类列" value={stringValue(current.category_col, "Category")} options={columns} onChange={(next) => setField("category_col", next || "Category")} emptyLabel="未识别到基因使用数据列" />
          <ColumnSelect label="指标起始列" value={stringValue(current.param_begin)} options={columns} onChange={(next) => setField("param_begin", next)} emptyLabel="未识别到基因使用数据列" />
          <ColumnSelect label="指标结束列" value={stringValue(current.param_over)} options={columns} onChange={(next) => setField("param_over", next)} emptyLabel="未识别到基因使用数据列" />
          <Field label="邻居数量">
            <input type="number" min="2" value={String(current.n_neighbors ?? 6)} onChange={(event) => setField("n_neighbors", Number(event.target.value || 6))} style={inputStyle} />
          </Field>
          <Field label="最小距离">
            <input type="number" min="0" max="1" step="0.01" value={String(current.min_dist ?? 0.01)} onChange={(event) => setField("min_dist", Number(event.target.value || 0.01))} style={inputStyle} />
          </Field>
          <SwitchField label="假发现率校正" checked={Boolean(current.do_fdr)} onChange={(checked) => setField("do_fdr", checked)} />
        </div>
      </Section>
    </ModuleShell>
  );
}
