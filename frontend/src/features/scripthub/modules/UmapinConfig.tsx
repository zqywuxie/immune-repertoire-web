import { useEffect, useRef, useState } from "react";
import { UmapinSampleSelection } from "./UmapinSampleSelection";
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
  sample_column?: string;
  sample_count?: number;
  feature_columns?: string[];
  pvalue_columns?: string[];
  samples_by_value?: Record<string, string[]>;
  suggested_param_begin?: string;
  suggested_param_over?: string;
};

export function UmapinConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspect, setInspect] = useState<UmapinInspectResponse | null>(null);
  const [inspectNote, setInspectNote] = useState("");
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectFailed, setInspectFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const current = withDefaults(value, {
    output_name: "",
    category_col: "Category",
    n_neighbors: 6,
    min_dist: 0.01,
    do_fdr: false,
    sample_column: "",
    n_epochs: 100,
  });
  const columns = inspect?.columns || [];
  const latest = useRef({ current, onChange });
  latest.current = { current, onChange };
  const setField = (key: string, next: unknown) => {
    if (key === "category_col" || key === "sample_column") onChange({ ...current, [key]: next,
      umapin_inspect_ok: false, selected_categories: undefined, selected_samples: undefined });
    else setFieldValue(current, onChange, key, next);
  };
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    setInspect(null);
    setInspectNote("请选择前置结果以检查特征与样本。");
    setInspectLoading(false);
    setInspectFailed(false);
    const {current: active, onChange: update} = latest.current;
    if (active.umapin_inspect_ok !== false) update({...active, umapin_inspect_ok: false});
    if (sourceContext?.projectId && sourceContext?.assetSetId && !current.upstream_artifact_id && !current.data_path) return;
    if (!sourceContext?.pepPaths?.length && !sourceContext?.projectId && !current.data_path) return;
    setInspectNote("正在检查特征列与实际投影样本…");
    setInspectLoading(true);
    let cancelled = false;
    inspectScriptHubModule<UmapinInspectResponse>("umapin", {
      data_path: current.upstream_artifact_id ? undefined : current.data_path,
      base_path: sourceContext?.pepPaths?.[0],
      project_id: sourceContext?.projectId,
      asset_set: sourceContext?.assetSetId,
      upstream_artifact_id: current.upstream_artifact_id,
      category_col: current.category_col, sample_column: current.sample_column,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const { current: active, onChange: update } = latest.current;
        const defaults: Record<string, unknown> = {umapin_inspect_ok: true};
        if (!active.data_path && data.data_path) defaults.data_path = data.data_path;
        if ((!active.category_col || active.category_col === "Category") && data.category_col && active.category_col !== data.category_col) defaults.category_col = data.category_col;
        if (!active.sample_column && data.sample_column) defaults.sample_column = data.sample_column;
        if (data.samples_by_value && !Array.isArray(active.selected_samples)) defaults.selected_samples = Object.values(data.samples_by_value).flat();
        if (!active.param_begin && data.suggested_param_begin) defaults.param_begin = data.suggested_param_begin;
        if (!active.param_over && data.suggested_param_over) defaults.param_over = data.suggested_param_over;
        if (Object.keys(defaults).length) update({ ...active, ...defaults });
        setInspectNote(`已读取 ${data.sample_count ?? 0} 个样本、${data.feature_columns?.length ?? 0} 个数值特征，请选择投影范围。`);
      })
      .catch((error) => {
        if (!cancelled) {
          setInspectFailed(true);
          setInspectNote(error instanceof TypeError ? "网络连接中断，请重新检查。"
            : error instanceof Error ? error.message : "特征降维输入检查失败，请重新检查。");
        }
      })
      .finally(() => {
        if (!cancelled) setInspectLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.pepPaths?.join("|"), sourceContext?.projectId, sourceContext?.assetSetId, current.upstream_artifact_id, current.upstream_artifact_id ? undefined : current.data_path, current.category_col, current.sample_column, revision]);

  return (
    <ModuleShell
      title="特征降维"
      detail="选择基因使用汇总表，并配置分类列、指标范围及降维参数。"
      sourceContext={sourceContext}
    >
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} showPvalue={false} />
      <div aria-busy={inspectLoading} style={{display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12}}>
        {inspectNote && <p role={inspectFailed ? "alert" : "status"} style={{flex: "1 1 220px", margin: 0,
          fontSize: "0.8rem", color: inspectFailed ? "var(--danger)" : "var(--text-secondary)"}}>{inspectNote}</p>}
        <button type="button" className="btn btn-secondary"
          disabled={inspectLoading || (!current.upstream_artifact_id && !current.data_path && !sourceContext?.pepPaths?.length)}
          onClick={() => setRevision(value => value + 1)}>重新检查输入</button>
      </div>
      <Section title="基因使用数据表">
        <div style={gridStyle}>
          <PepCacheCardSelector
            sourceContext={sourceContext}
            cacheType="umapin"
            value={stringValue(current.upstream_artifact_id || current.data_path)}
            label="克隆特征分析结果"
            onSelect={(candidate) => {
              const changed = candidate.artifact_id !== current.upstream_artifact_id;
              onChange({ ...current, data_path: candidate.path, source_job_id: candidate.job_id,
                upstream_artifact_id: candidate.artifact_id,
                ...(changed ? { umapin_inspect_ok: false, category_col: "Category", sample_column: "", param_begin: undefined, param_over: undefined,
                  selected_categories: undefined, selected_samples: undefined, do_fdr: false } : {}) });
            }}
          />
          <ColumnSelect label="样本编号列" value={stringValue(current.sample_column)} options={columns} onChange={next => setField("sample_column", next)} emptyLabel="未识别到样本编号列" />
          <ColumnSelect label="分类列" value={stringValue(current.category_col, "Category")} options={columns} onChange={(next) => setField("category_col", next || "Category")} emptyLabel="未识别到基因使用数据列" />
          <ColumnSelect label="指标起始列" value={stringValue(current.param_begin)} options={inspect?.feature_columns || []} onChange={(next) => setField("param_begin", next)} emptyLabel="未识别到基因使用数据列" />
          <ColumnSelect label="指标结束列" value={stringValue(current.param_over)} options={inspect?.feature_columns || []} onChange={(next) => setField("param_over", next)} emptyLabel="未识别到基因使用数据列" />
          <Field label="邻居数量">
            <input type="number" min="2" value={String(current.n_neighbors ?? 6)} onChange={(event) => setField("n_neighbors", Number(event.target.value || 6))} style={inputStyle} />
          </Field>
          <Field label="最小距离">
            <input type="number" min="0" max="1" step="0.01" value={String(current.min_dist ?? 0.01)} onChange={(event) => setField("min_dist", Number(event.target.value || 0.01))} style={inputStyle} />
          </Field>
          <Field label="训练轮数"><input type="number" min="1" value={String(current.n_epochs)} onChange={event => setField("n_epochs", Number(event.target.value))} style={inputStyle} /></Field>
          {!!inspect?.pvalue_columns?.length && <SwitchField label="假发现率校正" checked={Boolean(current.do_fdr)} onChange={(checked) => setField("do_fdr", checked)} />}
          {!!inspect?.pvalue_columns?.length && <p style={{ gridColumn: "1 / -1", fontSize: "0.8rem", color: "var(--text-secondary)", margin: 0 }}>对识别到的前 3 个 p 值列分别执行 0.05 BH 校正，结果另表下载。</p>}
        </div>
      </Section>
      {inspect?.samples_by_value && <UmapinSampleSelection groups={inspect.samples_by_value} value={current} onChange={onChange} />}
    </ModuleShell>
  );
}
