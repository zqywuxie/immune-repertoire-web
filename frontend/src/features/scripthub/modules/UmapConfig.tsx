import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  CommonRunFields,
  Field,
  GroupFieldSelect,
  GroupValueSamplePicker,
  ModuleShell,
  RangeFields,
  Section,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type UmapInspectResponse = {
  success: boolean;
  suggested_classification_begin?: string;
  suggested_classification_over?: string;
  suggested_param_begin?: string;
  suggested_param_over?: string;
};

export function UmapConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    group_field: "",
    n_neighbors: 6,
    min_dist: 0.01,
  });
  const [inspectNote, setInspectNote] = useState("");
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (!sourceContext?.profilePath) return;
    let cancelled = false;
    inspectScriptHubModule<UmapInspectResponse>("umap", {
      profile_path: sourceContext.profilePath,
      datapoint_path: sourceContext.profilePath,
    })
      .then((data) => {
        if (cancelled) return;
        const suggested = {
          classification_begin: data.suggested_classification_begin,
          classification_over: data.suggested_classification_over,
          group_field: data.suggested_classification_begin,
          param_begin: data.suggested_param_begin,
          param_over: data.suggested_param_over,
        };
        const next = Object.fromEntries(Object.entries(suggested).filter(([, item]) => item));
        if (Object.keys(next).length && !value.param_begin && !value.param_over) {
          onChange({ ...current, ...next });
        }
        setInspectNote("UMAP inspect loaded suggested classification and parameter ranges.");
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "UMAP inspect failed");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath]);

  return (
    <ModuleShell
      title="UMAP"
      detail="Profile 参数列从检测列选择，分组统一使用 Group Field 下拉选择。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="UMAP Parameters">
        <div style={gridStyle}>
          <GroupFieldSelect
            value={stringValue(current.group_field || current.classification_begin)}
            sourceContext={sourceContext}
            onChange={(next) => {
              onChange({ ...current, group_field: next, classification_begin: next, classification_over: next });
            }}
          />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={[stringValue(current.group_field || current.classification_begin)].filter(Boolean)} />
          <RangeFields value={current} setField={setField} sourceContext={sourceContext} parameterLabels />
          <Field label="n_neighbors">
            <input type="number" min="2" value={String(current.n_neighbors ?? 6)} onChange={(event) => setField("n_neighbors", Number(event.target.value || 6))} style={inputStyle} />
          </Field>
          <Field label="min_dist">
            <input type="number" min="0" max="1" step="0.01" value={String(current.min_dist ?? 0.01)} onChange={(event) => setField("min_dist", Number(event.target.value || 0.01))} style={inputStyle} />
          </Field>
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
