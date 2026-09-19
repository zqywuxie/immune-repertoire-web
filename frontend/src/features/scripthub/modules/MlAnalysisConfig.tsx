import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ColumnMultiPicker,
  ColumnSelect,
  CommonRunFields,
  Field,
  GroupFieldSelect,
  GroupValueSamplePicker,
  ModuleShell,
  PepCacheCardSelector,
  RangeFields,
  Section,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type MlInspectResponse = {
  success: boolean;
  sample_col?: string;
  label_col?: string;
  filter_candidates?: string[];
  profile_feature_candidates?: string[];
  usage_feature_candidates?: Array<{ column?: string; name?: string } | string>;
  suggested_param_begin?: string;
  suggested_param_over?: string;
  usage_path?: string;
};

export function MlAnalysisConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspect, setInspect] = useState<MlInspectResponse | null>(null);
  const [inspectNote, setInspectNote] = useState("");
  const current = withDefaults(value, {
    output_name: "",
    mode: "profile",
    sample_col: sourceContext?.profileFields?.find((field) => field.toLowerCase() === "sample") || "Sample",
    custom_threshold: 0.003,
    cv_splits: 3,
    roc_cv_splits: 7,
    feature_cols: [],
    usage_feature_cols: [],
  });
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (!sourceContext?.profilePath) return;
    let cancelled = false;
    inspectScriptHubModule<MlInspectResponse>("ml-analysis", {
      project_id: sourceContext.projectId,
      profile_path: sourceContext.profilePath,
      datapoint_path: sourceContext.profilePath,
      mode: current.mode,
      usage_path: current.upstream_artifact_id ? undefined : current.usage_path,
      label_col: current.label_col,
      sample_col: current.sample_col,
      filter_col: current.filter_col,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const defaults: Record<string, unknown> = {};
        if (!value.sample_col && data.sample_col) defaults.sample_col = data.sample_col;
        if (!value.label_col && data.label_col) defaults.label_col = data.label_col;
        if (!value.param_begin && data.suggested_param_begin) defaults.param_begin = data.suggested_param_begin;
        if (!value.param_over && data.suggested_param_over) defaults.param_over = data.suggested_param_over;
        if (!value.usage_path && data.usage_path) defaults.usage_path = data.usage_path;
        if (Object.keys(defaults).length) onChange({ ...current, ...defaults });
        setInspectNote("已读取标签列、样本列及候选特征。");
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "机器学习输入检查失败");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath, sourceContext?.projectId, sourceContext?.assetSetId, current.upstream_artifact_id, current.mode, current.upstream_artifact_id, sourceContext?.assetSetId, current.usage_path, current.label_col, current.sample_col, current.filter_col]);

  const usageFeatureColumns = (inspect?.usage_feature_candidates || []).map((item) => (
    typeof item === "string" ? item : String(item.column || item.name || "")
  )).filter(Boolean);

  return (
    <ModuleShell
      title="机器学习"
      detail="选择数据模式，再配置样本指标、基因使用特征或联合特征。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="数据模式">
        <div style={gridStyle}>
          <Field label="数据模式">
            <select
              value={stringValue(current.mode, "profile")}
              onChange={(event) => setField("mode", event.target.value)}
              style={inputStyle}
            >
              <option value="profile">样本指标表</option>
              <option value="vj">VJ</option>
              <option value="profile_vj">样本指标与 V/J 特征</option>
            </select>
          </Field>
          <Field label="样本指标表来源">
            <input value={sourceContext?.profilePath ? "Selected project Profile" : "未选择样本指标表"} readOnly style={{ ...inputStyle, color: "var(--text-secondary)" }} />
          </Field>
        </div>
      </Section>
      <Section title="数据来源">
        <div style={gridStyle}>
          {stringValue(current.mode, "profile") === "profile" ? (
            <div style={{ gridColumn: "1 / -1", color: "var(--text-secondary)", fontSize: "0.78rem" }}>
              正在使用已选样本指标表。
            </div>
          ) : (
            <PepCacheCardSelector
              sourceContext={sourceContext}
              cacheType="ml-vj"
              value={stringValue(current.upstream_artifact_id || current.usage_path)}
              label="V/J 基因使用分析结果"
              emptyText="未找到 V/J 使用缓存，请先运行并生成相应克隆分析结果。"
              onSelect={(candidate) => onChange({ ...current, usage_path: candidate.path, upstream_artifact_id: candidate.artifact_id, source_job_id: candidate.job_id })}
            />
          )}
        </div>
      </Section>
      <Section title="标签与样本">
        <div style={gridStyle}>
          <GroupFieldSelect label="标签列" value={stringValue(current.label_col)} sourceContext={sourceContext} onChange={(next) => setField("label_col", next)} />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.label_col)].filter(Boolean)} />
          <ColumnSelect label="样本列" value={stringValue(current.sample_col, "Sample")} options={sourceContext?.profileFields || []} onChange={(next) => setField("sample_col", next || "Sample")} emptyLabel="未识别到样本指标表的列" />
          <GroupFieldSelect label="筛选列" value={stringValue(current.filter_col)} sourceContext={sourceContext} onChange={(next) => setField("filter_col", next || undefined)} emptyLabel="未识别到可用的指标表筛选项" optional />
        </div>
      </Section>
      <Section title="特征范围">
        <div style={gridStyle}>
          {current.mode === "profile" || current.mode === "profile_vj" ? (
            <>
              <RangeFields value={current} setField={setField} sourceContext={sourceContext} />
            </>
          ) : null}
          {current.mode === "vj" ? (
            <>
              <ColumnMultiPicker label="基因使用特征" selected={Array.isArray(current.usage_feature_cols) ? current.usage_feature_cols.map(String) : []} options={usageFeatureColumns} onChange={(next) => setField("usage_feature_cols", next)} emptyLabel="未识别到基因使用候选特征" />
            </>
          ) : null}
          {current.mode === "profile_vj" ? (
            <ColumnMultiPicker label="可选 V/J 特征" selected={Array.isArray(current.usage_feature_cols) ? current.usage_feature_cols.map(String) : []} options={usageFeatureColumns} onChange={(next) => setField("usage_feature_cols", next)} emptyLabel="未识别到基因使用候选特征" />
          ) : null}
        </div>
      </Section>
      <Section title="模型参数">
        <div style={gridStyle}>
          <Field label="自定义阈值">
            <input type="number" min="0" step="0.001" value={String(current.custom_threshold ?? 0.003)} onChange={(event) => setField("custom_threshold", Number(event.target.value || 0.003))} style={inputStyle} />
          </Field>
          <Field label="交叉验证折数">
            <input type="number" min="2" value={String(current.cv_splits ?? 3)} onChange={(event) => setField("cv_splits", Number(event.target.value || 3))} style={inputStyle} />
          </Field>
          <Field label="分类评估交叉验证折数">
            <input type="number" min="2" value={String(current.roc_cv_splits ?? 7)} onChange={(event) => setField("roc_cv_splits", Number(event.target.value || 7))} style={inputStyle} />
          </Field>
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
