import { useEffect, useRef, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  CommonRunFields,
  ColumnSelect,
  Field,
  GroupFieldSelect,
  GroupOrderEditor,
  GroupValueSamplePicker,
  ModuleShell,
  PepCacheCardSelector,
  RangeFields,
  Section,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringList,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type UmapInspectResponse = {
  success: boolean;
  suggested_sample_column?: string;
  suggested_group_column?: string;
  batch_column_candidates?: string[];
  suggested_classification_begin?: string;
  suggested_classification_over?: string;
  suggested_param_begin?: string;
  suggested_param_over?: string;
  vj_usage_path?: string;
  vj_usage_available?: boolean;
  vj_upstream_artifact_id?: string;
};

const CONFIG_OPTIONS = [
  { key: "profile", label: "样本指标表", needsVj: false },
  { key: "vj", label: "V/J 使用结果", needsVj: true },
  { key: "vj+profile", label: "指标表 + V/J 使用结果", needsVj: true },
];

export function UmapConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    analysis_mode: "unified",
    configurations: ["profile"],
    comparison_cohort: "auto",
    pvalue_threshold: 0.05,
    raw_p_threshold: 0.05,
    group_field: "",
    sample_column: "sample",
    batch_field: "",
    n_neighbors: 6,
    min_dist: 0.01,
    n_epochs: 50,
    permanova_permutations: 999,
    random_state: 42,
    permanova_random_state: 42,
  });
  const [inspectNote, setInspectNote] = useState("");
  const [vjAvailable, setVjAvailable] = useState(false);
  const configs = stringList(current.configurations);
  const groupField = stringValue(current.group_field || current.classification_begin);
  const usesProfile = configs.some((config) => config === "profile" || config === "vj+profile");
  const latest = useRef({ current, onChange });
  latest.current = { current, onChange };
  const setField = (key: string, next: unknown) => {
    if (key === "batch_field" || key === "sample_column") onChange({ ...current, [key]: next,
      selected_samples_by_group: undefined, group_sample_identity: (key === "batch_field" ? next : current.batch_field) ? "batch_sample" : "sample" });
    else if (key === "selected_samples_by_group") onChange({ ...current, selected_samples_by_group: next,
      group_sample_identity: current.batch_field ? "batch_sample" : "sample" });
    else setFieldValue(current, onChange, key, next);
  };
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    setVjAvailable(false);
    if (!sourceContext?.profilePath) { setInspectNote(""); return; }
    setInspectNote("正在核对样本指标与前置 V/J 特征…");
    let cancelled = false;
    inspectScriptHubModule<UmapInspectResponse>("umap", {
      project_id: sourceContext.projectId,
      asset_set: sourceContext.assetSetId,
      profile_path: sourceContext.profilePath,
      datapoint_path: sourceContext.profilePath,
      ...(current.upstream_artifact_id ? { analysis_mode: "unified", configurations: ["vj"], upstream_artifact_id: current.upstream_artifact_id,
        group_field: groupField } : { vj_usage_path: current.vj_usage_path }),
    })
      .then((data) => {
        if (cancelled) return;
        setVjAvailable(Boolean(data.vj_usage_available));
        const { current: active, onChange: update } = latest.current;
        const next: Record<string, unknown> = {
          analysis_mode: "unified",
          sample_column: active.sample_column && active.sample_column !== "sample"
            ? active.sample_column
            : data.suggested_sample_column || active.sample_column || "sample",
          group_field: active.group_field || data.suggested_group_column || data.suggested_classification_begin || "",
          classification_begin: active.group_field || data.suggested_group_column || data.suggested_classification_begin || "",
          classification_over: active.group_field || data.suggested_group_column || data.suggested_classification_over || "",
          param_begin: active.param_begin || data.suggested_param_begin || "",
          param_over: active.param_over || data.suggested_param_over || "",
          vj_usage_path: data.vj_usage_path || "",
        };
        const updates = Object.fromEntries(Object.entries(next).filter(([key, item]) =>
          item && (!active[key] || (key === "sample_column" && active[key] === "sample")),
        ));
        if (data.vj_upstream_artifact_id && !active.upstream_artifact_id) updates.upstream_artifact_id = data.vj_upstream_artifact_id;
        if (Object.keys(updates).length) update({ ...active, ...updates });
        setInspectNote(data.vj_usage_available
          ? `已检查样本编号、分组及 V/J 使用结果；请选择投影组合和比较范围。${data.batch_column_candidates?.length ? "如存在跨批次同名样本，请选择批次字段。" : ""}`
          : `已检查样本指标表。当前没有可用的 V/J 使用结果，仍可运行样本指标表投影。${data.batch_column_candidates?.length ? "如存在跨批次同名样本，请选择批次字段。" : ""}`
        );
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "输入检查失败，请重新选择样本指标表。");
      });
    return () => { cancelled = true; };
  }, [sourceContext?.profilePath, sourceContext?.projectId, sourceContext?.assetSetId, current.upstream_artifact_id]);

  const toggleConfig = (key: string, checked: boolean) => {
    const next = new Set(configs);
    if (checked) next.add(key);
    else next.delete(key);
    if (!next.size) next.add("profile");
    onChange({ ...current, analysis_mode: "unified", configurations: CONFIG_OPTIONS.map((option) => option.key).filter((item) => next.has(item)) });
  };

  return (
    <ModuleShell
      title="统一多模态 UMAP"
      detail="选择样本指标表和 V/J 使用结果的组合；系统按组间差异筛选特征，输出 UMAP 投影与 PERMANOVA 统计。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div role="status" style={{ fontSize: "0.82rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}

      <Section title="数据与比较范围">
        <div style={gridStyle}>
          <GroupFieldSelect
            label="分组字段"
            value={groupField}
            sourceContext={sourceContext}
            onChange={(next) => onChange({ ...current, group_field: next, classification_begin: next, classification_over: next, selected_group_values: undefined, selected_samples_by_group: undefined })}
            emptyLabel="未检测到分组字段，请检查样本指标表"
          />
          <GroupOrderEditor
            selectedFields={groupField ? [groupField] : []}
            sourceContext={sourceContext}
            value={current.group_order}
            onChange={(next) => setField("group_order", next)}
          />
          <ColumnSelect label="样本编号字段" value={stringValue(current.sample_column)} options={sourceContext?.profileFields || []}
            onChange={(next) => setField("sample_column", next)} emptyLabel="未识别到样本编号字段" />
          <ColumnSelect
            label="批次字段（可选）"
            value={stringValue(current.batch_field)}
            onChange={(next) => setField("batch_field", next || "")}
            options={(sourceContext?.profileFields || []).filter((column) => column !== stringValue(current.sample_column) && column !== groupField)}
            emptyLabel="未识别到其他字段"
            optional
          />
          <GroupValueSamplePicker
            value={{ ...current, grouptype_fields: groupField ? [groupField] : [] }}
            setField={setField}
            sourceContext={sourceContext}
            fields={groupField ? [groupField] : []}
            batchField={stringValue(current.batch_field)} sampleColumn={stringValue(current.sample_column)}
          />
        </div>
        <div style={{ display: "grid", gap: 10, marginTop: 16 }}>
          <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>投影数据组合</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
            {CONFIG_OPTIONS.map((option) => {
              const disabled = option.needsVj && !vjAvailable;
              return (
                <label key={option.key} style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "9px 12px", border: "1px solid var(--border-default)", borderRadius: 9, opacity: disabled ? 0.55 : 1, cursor: disabled ? "not-allowed" : "pointer" }}>
                  <input type="checkbox" checked={configs.includes(option.key)} disabled={disabled} onChange={(event) => toggleConfig(option.key, event.target.checked)} />
                  <span>{option.label}</span>
                </label>
              );
            })}
          </div>
        </div>
      </Section>

      {configs.some(config => config.split("+").includes("vj")) && <Section title="V/J 特征来源">
        <PepCacheCardSelector sourceContext={sourceContext} cacheType="umapin"
          value={stringValue(current.upstream_artifact_id || current.vj_usage_path)} label="V/J 特征汇总结果"
          onSelect={candidate => onChange({ ...current, upstream_artifact_id: candidate.artifact_id,
            source_job_id: candidate.job_id, vj_usage_path: candidate.path })} />
      </Section>}

      {usesProfile && (
        <Section title="样本指标特征范围">
          <RangeFields value={current} setField={setField} sourceContext={sourceContext} parameterLabels />
        </Section>
      )}

      <Section title="投影与统计参数">
        <div style={gridStyle}>
          <Field label="原始 p 值筛选阈值">
            <input type="number" min="0.000001" max="1" step="0.01" value={String(current.raw_p_threshold ?? current.pvalue_threshold ?? 0.05)} onChange={(event) => setField("raw_p_threshold", Number(event.target.value || 0.05))} style={inputStyle} />
          </Field>
          <Field label="比较样本范围">
            <select className="input" value={stringValue(current.comparison_cohort || "auto")} onChange={(event) => setField("comparison_cohort", event.target.value)} style={inputStyle}>
              <option value="auto">单数据源分别使用；组合数据使用共同样本</option>
              <option value="per_config">各配置使用各自可匹配样本</option>
              <option value="shared">联合投影只使用各输入共有样本</option>
            </select>
          </Field>
          <Field label="邻居数量">
            <input type="number" min="2" value={String(current.n_neighbors ?? 6)} onChange={(event) => setField("n_neighbors", Number(event.target.value || 6))} style={inputStyle} />
          </Field>
          <Field label="最小距离">
            <input type="number" min="0" max="1" step="0.01" value={String(current.min_dist ?? 0.01)} onChange={(event) => setField("min_dist", Number(event.target.value || 0.01))} style={inputStyle} />
          </Field>
          <Field label="训练轮数">
            <input type="number" min="1" value={String(current.n_epochs ?? 50)} onChange={(event) => setField("n_epochs", Number(event.target.value || 50))} style={inputStyle} />
          </Field>
          <Field label="PERMANOVA 置换次数">
            <input type="number" min="1" value={String(current.permanova_permutations ?? 999)} onChange={(event) => setField("permanova_permutations", Number(event.target.value || 999))} style={inputStyle} />
          </Field>
        </div>
        <p style={{ margin: "12px 0 0", color: "var(--text-tertiary)", fontSize: "0.78rem" }}>
          组合投影默认仅使用各输入共有的样本；单数据源投影保留该数据源可匹配的样本。置换检验在标准化后的筛选特征空间计算。
        </p>
        {Boolean(current.batch_field) && <p style={{ margin: "8px 0 0", color: "var(--text-tertiary)", fontSize: "0.78rem" }}>
          样本按“批次 + 编号”分别识别，可只纳入某个批次的同名样本；所选 V/J 结果须包含对应身份。
        </p>}
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} showPvalue={false} />
    </ModuleShell>
  );
}
