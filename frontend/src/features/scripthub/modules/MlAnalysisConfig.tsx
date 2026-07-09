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
      usage_path: current.usage_path,
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
        setInspectNote("ML inspect loaded label/sample columns and feature candidates.");
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "ML inspect failed");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath, sourceContext?.projectId, current.usage_path, current.label_col, current.sample_col, current.filter_col]);

  const usageFeatureColumns = (inspect?.usage_feature_candidates || []).map((item) => (
    typeof item === "string" ? item : String(item.column || item.name || "")
  )).filter(Boolean);

  return (
    <ModuleShell
      title="Machine Learning"
      detail="先选择 Data Mode，再选择对应数据源；支持 Profile、VJ、Profile + VJ。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="Data Mode">
        <div style={gridStyle}>
          <Field label="Data Mode">
            <select
              value={stringValue(current.mode, "profile")}
              onChange={(event) => setField("mode", event.target.value)}
              style={inputStyle}
            >
              <option value="profile">Profile</option>
              <option value="vj">VJ</option>
              <option value="profile_vj">Profile + VJ</option>
            </select>
          </Field>
          <Field label="Profile Source">
            <input value={sourceContext?.profilePath ? "Selected project Profile" : "No Profile selected"} readOnly style={{ ...inputStyle, color: "var(--text-secondary)" }} />
          </Field>
        </div>
      </Section>
      <Section title="Data Source">
        <div style={gridStyle}>
          {stringValue(current.mode, "profile") === "profile" ? (
            <div style={{ gridColumn: "1 / -1", color: "var(--text-secondary)", fontSize: "0.78rem" }}>
              Using the selected Profile source.
            </div>
          ) : (
            <PepCacheCardSelector
              sourceContext={sourceContext}
              cacheType="ml-vj"
              value={stringValue(current.usage_path)}
              label="PEP VJ Cache"
              emptyText="No PEP cache with VJ usage found. Run PEP Analysis with VJ usage outputs first."
              onSelect={(candidate) => setField("usage_path", candidate.path)}
            />
          )}
        </div>
      </Section>
      <Section title="Label And Samples">
        <div style={gridStyle}>
          <GroupFieldSelect label="Label Column" value={stringValue(current.label_col)} sourceContext={sourceContext} onChange={(next) => setField("label_col", next)} />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.label_col)].filter(Boolean)} />
          <ColumnSelect label="Sample Column" value={stringValue(current.sample_col, "Sample")} options={sourceContext?.profileFields || []} onChange={(next) => setField("sample_col", next || "Sample")} emptyLabel="No Profile columns detected" />
          <GroupFieldSelect label="Filter Column" value={stringValue(current.filter_col)} sourceContext={sourceContext} onChange={(next) => setField("filter_col", next || undefined)} emptyLabel="No Profile filter candidates detected" optional />
        </div>
      </Section>
      <Section title="Feature Range">
        <div style={gridStyle}>
          {current.mode === "profile" || current.mode === "profile_vj" ? (
            <>
              <RangeFields value={current} setField={setField} sourceContext={sourceContext} />
            </>
          ) : null}
          {current.mode === "vj" ? (
            <>
              <ColumnMultiPicker label="Usage Features" selected={Array.isArray(current.usage_feature_cols) ? current.usage_feature_cols.map(String) : []} options={usageFeatureColumns} onChange={(next) => setField("usage_feature_cols", next)} emptyLabel="No usage feature candidates detected" />
            </>
          ) : null}
          {current.mode === "profile_vj" ? (
            <ColumnMultiPicker label="Optional VJ Features" selected={Array.isArray(current.usage_feature_cols) ? current.usage_feature_cols.map(String) : []} options={usageFeatureColumns} onChange={(next) => setField("usage_feature_cols", next)} emptyLabel="No usage feature candidates detected" />
          ) : null}
        </div>
      </Section>
      <Section title="Model Parameters">
        <div style={gridStyle}>
          <Field label="Custom Threshold">
            <input type="number" min="0" step="0.001" value={String(current.custom_threshold ?? 0.003)} onChange={(event) => setField("custom_threshold", Number(event.target.value || 0.003))} style={inputStyle} />
          </Field>
          <Field label="CV Splits">
            <input type="number" min="2" value={String(current.cv_splits ?? 3)} onChange={(event) => setField("cv_splits", Number(event.target.value || 3))} style={inputStyle} />
          </Field>
          <Field label="ROC CV Splits">
            <input type="number" min="2" value={String(current.roc_cv_splits ?? 7)} onChange={(event) => setField("roc_cv_splits", Number(event.target.value || 7))} style={inputStyle} />
          </Field>
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
