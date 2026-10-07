import { useEffect, useRef, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  ColumnMultiPicker,
  ColumnSelect,
  CommonRunFields,
  Field,
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
  usage_feature_candidates?: Array<{ value?: string; label?: string; column?: string; name?: string } | string>;
  suggested_param_begin?: string;
  suggested_param_over?: string;
  usage_path?: string;
};

const modelOptions = [
  ["logistic_l1", "逻辑回归（L1）"],
  ["random_forest", "随机森林"],
  ["extra_trees", "极端随机树"],
  ["logistic_l2", "逻辑回归（L2）"],
  ["gaussian_nb", "高斯朴素贝叶斯"],
  ["knn", "K 近邻"],
  ["rbf_svm", "径向基 SVM"],
  ["linear_svm", "线性 SVM"],
  ["gradient_boosting", "梯度提升树"],
  ["xgboost", "XGBoost"],
] as const;

export function MlAnalysisConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspect, setInspect] = useState<MlInspectResponse | null>(null);
  const [inspectNote, setInspectNote] = useState("");
  const [inspectLoading, setInspectLoading] = useState(false);
  const [inspectFailed, setInspectFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const current = withDefaults(value, {
    output_name: "",
    mode: "profile",
    model_keys: ["random_forest"],
    sample_col: sourceContext?.profileFields?.find((field) => field.toLowerCase() === "sample") || "Sample",
      custom_threshold: 0.003,
      cv_splits: 3,
      use_stability_selection: true,
      stability_threshold: 0.6,
      stability_splits: 5,
      stability_min_features: 5,
      group_col: "",
      batch_field: "",
    feature_cols: [],
    usage_feature_cols: [],
  });
  const latest = useRef({ current, onChange });
  latest.current = { current, onChange };
  const setField = (key: string, next: unknown) => {
    const { current: active, onChange: update } = latest.current;
    const publish = (nextValue: Record<string, unknown>) => { latest.current = { current: nextValue, onChange: update }; update(nextValue); };
    if (key === "batch_field" || key === "sample_col" || key === "label_col") {
      publish({ ...active, [key]: next, ml_inspect_ok: false, selected_samples_by_group: undefined,
        ...(key === "label_col" ? { selected_group_values: undefined } : {}),
        group_sample_identity: (key === "batch_field" ? next : active.batch_field) ? "batch_sample" : "sample" });
    } else if (key === "selected_samples_by_group") {
      publish({ ...active, selected_samples_by_group: next,
        group_sample_identity: active.batch_field ? "batch_sample" : "sample" });
    } else if (["group_col", "filter_col", "filter_value"].includes(key)) {
      publish({ ...active, [key]: next, ml_inspect_ok: false });
    } else publish({ ...active, [key]: next });
  };
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    setInspect(null);
    setInspectLoading(false);
    setInspectFailed(false);
    const { current: active, onChange: update } = latest.current;
    if (active.ml_inspect_ok !== false) update({ ...active, ml_inspect_ok: false });
    if (!sourceContext?.profilePath) { setInspectNote("请选择样本指标表以检查标签和特征。"); return; }
    setInspectLoading(true);
    setInspectNote("正在读取标签、样本身份与候选特征…");
    let cancelled = false;
    inspectScriptHubModule<MlInspectResponse>("ml-analysis", {
      project_id: sourceContext.projectId,
      asset_set: sourceContext.assetSetId,
      upstream_artifact_id: current.upstream_artifact_id,
      profile_path: sourceContext.profilePath,
      datapoint_path: sourceContext.profilePath,
      mode: current.mode,
      usage_path: current.upstream_artifact_id ? undefined : current.usage_path,
      label_col: current.label_col,
      sample_col: current.sample_col,
      filter_col: current.filter_col,
      filter_value: current.filter_value,
      group_col: current.group_col,
      batch_field: current.batch_field,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const { current: active, onChange: update } = latest.current;
        const defaults: Record<string, unknown> = { ml_inspect_ok: true };
        if (!active.sample_col && data.sample_col) defaults.sample_col = data.sample_col;
        if (!active.label_col && data.label_col) defaults.label_col = data.label_col;
        if (active.mode !== "vj" && !active.param_begin && data.suggested_param_begin) defaults.param_begin = data.suggested_param_begin;
        if (active.mode !== "vj" && !active.param_over && data.suggested_param_over) defaults.param_over = data.suggested_param_over;
        if (!active.usage_path && data.usage_path) defaults.usage_path = data.usage_path;
        if (Object.keys(defaults).length) update({ ...active, ...defaults });
        setInspectNote("已读取标签列、样本列及候选特征。");
      })
      .catch((error) => {
        if (!cancelled) {
          setInspectFailed(true);
          setInspectNote(error instanceof TypeError ? "网络连接中断，请重新检查。"
            : error instanceof Error ? error.message : "机器学习输入检查失败，请重新检查。");
        }
      })
      .finally(() => { if (!cancelled) setInspectLoading(false); });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath, sourceContext?.projectId, sourceContext?.assetSetId,
    current.upstream_artifact_id, current.mode, current.upstream_artifact_id ? undefined : current.usage_path, current.label_col,
    current.sample_col, current.filter_col, current.filter_value, current.group_col, current.batch_field, revision]);

  const usageFeatureColumns = (inspect?.usage_feature_candidates || []).map((item) => (
    typeof item === "string" ? item : String(item.value || item.column || item.name || "")
  )).filter(Boolean);
  const selectedModels = Array.isArray(current.model_keys)
    ? current.model_keys.map(String)
    : ["random_forest"];

  return (
    <ModuleShell
      title="机器学习"
      detail="选择数据模式，再配置样本指标、基因使用特征或联合特征。"
      sourceContext={sourceContext}
    >
      <div aria-busy={inspectLoading} style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
        {inspectNote && <p role={inspectFailed ? "alert" : "status"} style={{ flex: "1 1 220px", margin: 0,
          fontSize: "0.8rem", color: inspectFailed ? "var(--danger)" : "var(--text-secondary)" }}>{inspectNote}</p>}
        <button type="button" className="btn btn-secondary" disabled={inspectLoading || !sourceContext?.profilePath}
          onClick={() => setRevision(value => value + 1)}>重新检查输入</button>
      </div>
      <Section title="数据模式">
        <div style={gridStyle}>
          <Field label="数据模式">
            <select
              value={stringValue(current.mode, "profile")}
              onChange={(event) => onChange({ ...current, mode: event.target.value, ml_inspect_ok: false,
                param_begin: undefined, param_over: undefined, usage_feature_cols: [],
                ...(event.target.value === "profile" ? { upstream_artifact_id: undefined, source_job_id: undefined, usage_path: undefined } : {}) })}
              style={inputStyle}
            >
              <option value="profile">样本指标表</option>
              <option value="vj">V/J 基因使用特征</option>
              <option value="profile_vj">样本指标与 V/J 特征</option>
            </select>
          </Field>
          <Field label="样本指标表来源">
            <input value={sourceContext?.profilePath ? "已选项目的样本指标表" : "未选择样本指标表"} readOnly style={{ ...inputStyle, color: "var(--text-secondary)" }} />
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
              onSelect={(candidate) => onChange({ ...current, usage_path: candidate.path, upstream_artifact_id: candidate.artifact_id,
                source_job_id: candidate.job_id, ...(candidate.artifact_id !== current.upstream_artifact_id
                  ? { ml_inspect_ok: false, usage_feature_cols: [] } : {}) })}
            />
          )}
        </div>
      </Section>
      <Section title="标签与样本">
        <div style={gridStyle}>
          <ColumnSelect label="标签列" emptyLabel="未识别到分类标签列" value={stringValue(current.label_col)} options={sourceContext?.profileFields || []} onChange={(next) => setField("label_col", next)} />
          <ColumnSelect label="受试者分组列（可选）" emptyLabel="未识别到受试者分组列" value={stringValue(current.group_col)} options={sourceContext?.profileFields || []} onChange={(next) => setField("group_col", next || "")} optional />
          <ColumnSelect label="批次字段（可选）" value={stringValue(current.batch_field)} options={sourceContext?.profileFields || []}
            onChange={(next) => setField("batch_field", next || "")} optional emptyLabel="未识别到样本指标表的列" />
          <div style={{ gridColumn: "1 / -1", color: "var(--text-secondary)", fontSize: "0.78rem", lineHeight: 1.6 }}>
            批次用于区分同名样本；受试者分组用于交叉验证，保证同一受试者不同时进入训练与验证。两种字段不会自动互相替代。
          </div>
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext}
            fields={[stringValue(current.label_col)].filter(Boolean)} batchField={stringValue(current.batch_field)} sampleColumn={stringValue(current.sample_col)} />
          <ColumnSelect label="样本列" value={stringValue(current.sample_col, "Sample")} options={sourceContext?.profileFields || []} onChange={(next) => setField("sample_col", next || "Sample")} emptyLabel="未识别到样本指标表的列" />
          <ColumnSelect label="筛选列" value={stringValue(current.filter_col)} options={sourceContext?.profileFields || []} onChange={(next) => setField("filter_col", next || undefined)} emptyLabel="未识别到可用的指标表筛选项" optional />
          {Boolean(current.filter_col) && <Field label="筛选值">
            <input value={stringValue(current.filter_value)} onChange={(event) => setField("filter_value", event.target.value)} style={inputStyle} placeholder="填写要保留的值；留空不筛选" />
          </Field>}
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
          <Field label="参与比较的模型">
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))", gap: 8 }}>
              {modelOptions.map(([key, label]) => (
                <label key={key} style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 36, color: "var(--text-primary)" }}>
                  <input
                    type="checkbox"
                    checked={selectedModels.includes(key)}
                    onChange={(event) => {
                      const next = event.target.checked
                        ? [...selectedModels, key]
                        : selectedModels.filter((selected) => selected !== key);
                      if (next.length) setField("model_keys", next);
                    }}
                  />
                  {label}
                </label>
              ))}
            </div>
            <div style={{ marginTop: 6, color: "var(--text-secondary)", fontSize: "0.78rem" }}>
              每个模型独立调参并进行嵌套交叉验证；模型越多，运行时间越长。
            </div>
          </Field>
          <Field label="特征重要性阈值">
            <input type="number" min="0" step="0.001" value={String(current.custom_threshold ?? 0.003)} onChange={(event) => setField("custom_threshold", Number(event.target.value || 0.003))} style={inputStyle} />
          </Field>
          <Field label="交叉验证折数">
            <input type="number" min="2" value={String(current.cv_splits ?? 3)} onChange={(event) => setField("cv_splits", Number(event.target.value || 3))} style={inputStyle} />
          </Field>
          <Field label="稳定特征筛选">
            <label style={{ display: "flex", alignItems: "center", gap: 8, minHeight: 36, color: "var(--text-primary)" }}>
              <input
                type="checkbox"
                checked={Boolean(current.use_stability_selection ?? true)}
                onChange={(event) => setField("use_stability_selection", event.target.checked)}
              />
              按交叉验证折中的入选频率确定最终模型特征
            </label>
            <div style={{ color: "var(--text-secondary)", fontSize: "0.78rem" }}>
              仅影响最终模型特征；交叉验证评估仍在各训练折内完成筛选，避免使用验证样本信息。
            </div>
          </Field>
          {Boolean(current.use_stability_selection ?? true) ? (
            <>
              <Field label="最低入选频率">
                <input type="number" min="0.01" max="1" step="0.05" value={String(current.stability_threshold ?? 0.6)} onChange={(event) => setField("stability_threshold", Number(event.target.value || 0.6))} style={inputStyle} />
              </Field>
              <Field label="稳定性筛选折数">
                <input type="number" min="2" value={String(current.stability_splits ?? 5)} onChange={(event) => setField("stability_splits", Number(event.target.value || 5))} style={inputStyle} />
              </Field>
              <Field label="每类数据最少保留特征数">
                <input type="number" min="1" value={String(current.stability_min_features ?? 5)} onChange={(event) => setField("stability_min_features", Number(event.target.value || 5))} style={inputStyle} />
              </Field>
            </>
          ) : null}
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} showPvalue={false} />
    </ModuleShell>
  );
}
