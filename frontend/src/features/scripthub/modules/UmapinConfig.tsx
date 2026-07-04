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
      data_path: current.data_path,
      base_path: sourceContext?.pepPaths?.[0],
      project_id: sourceContext?.projectId,
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
        setInspectNote(`UMAPin inspect loaded ${data.columns?.length || 0} usage columns.`);
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "UMAPin inspect failed");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.pepPaths?.join("|"), sourceContext?.projectId, current.data_path]);

  return (
    <ModuleShell
      title="UMAPin"
      detail="基于 VJ usage 汇总表配置；category 和参数范围全部来自 usage CSV columns。"
      sourceContext={sourceContext}
    >
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="Usage Table">
        <div style={gridStyle}>
          <PepCacheCardSelector
            sourceContext={sourceContext}
            cacheType="umapin"
            value={stringValue(current.data_path)}
            label="PEP UMAPin Cache"
            onSelect={(candidate) => onChange({
              ...current,
              data_path: candidate.path,
              source_job_id: candidate.job_id || current.source_job_id,
              pep_cache_id: candidate.asset_id || candidate.id,
            })}
          />
          <ColumnSelect label="Category Column" value={stringValue(current.category_col, "Category")} options={columns} onChange={(next) => setField("category_col", next || "Category")} emptyLabel="No usage columns detected" />
          <ColumnSelect label="Parameter Begin" value={stringValue(current.param_begin)} options={columns} onChange={(next) => setField("param_begin", next)} emptyLabel="No usage columns detected" />
          <ColumnSelect label="Parameter End" value={stringValue(current.param_over)} options={columns} onChange={(next) => setField("param_over", next)} emptyLabel="No usage columns detected" />
          <Field label="n_neighbors">
            <input type="number" min="2" value={String(current.n_neighbors ?? 6)} onChange={(event) => setField("n_neighbors", Number(event.target.value || 6))} style={inputStyle} />
          </Field>
          <Field label="min_dist">
            <input type="number" min="0" max="1" step="0.01" value={String(current.min_dist ?? 0.01)} onChange={(event) => setField("min_dist", Number(event.target.value || 0.01))} style={inputStyle} />
          </Field>
          <SwitchField label="FDR Correction" checked={Boolean(current.do_fdr)} onChange={(checked) => setField("do_fdr", checked)} />
        </div>
      </Section>
    </ModuleShell>
  );
}
