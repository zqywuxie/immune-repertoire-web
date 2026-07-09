import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  CommonRunFields,
  GroupFieldMultiSelect,
  GroupOrderEditor,
  GroupValueSamplePicker,
  GroupSpecSelect,
  ModuleShell,
  RangeFields,
  Section,
  gridStyle,
  setFieldValue,
  stringList,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type ProfileInspectResponse = {
  success: boolean;
  suggested_grouping_begin?: string;
  suggested_grouping_over?: string;
  suggested_param_begin?: string;
  suggested_param_over?: string;
};

export function ProfileConfig({ sourceContext, groupSpecs, loadingSpecs, value, onChange }: ModuleFormProps) {
  const current = withDefaults(value, {
    output_name: "",
    pvalue_threshold: 0.05,
    grouptype_fields: [],
  });
  const [inspectNote, setInspectNote] = useState("");
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (!sourceContext?.profilePath) return;
    let cancelled = false;
    inspectScriptHubModule<ProfileInspectResponse>("profile", {
      profile_path: sourceContext.profilePath,
      datapoint_path: sourceContext.profilePath,
      base_path: sourceContext.pepPaths?.[0],
    })
      .then((data) => {
        if (cancelled) return;
        const suggested = {
          param_begin: data.suggested_param_begin,
          param_over: data.suggested_param_over,
        };
        const next = Object.fromEntries(Object.entries(suggested).filter(([, item]) => item));
        if (Object.keys(next).length && !value.param_begin && !value.param_over) {
          onChange({ ...current, ...next });
        }
        setInspectNote("Profile inspect loaded suggested parameter ranges.");
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "Profile inspect failed");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath]);

  return (
    <ModuleShell
      title="Profile / Boxplot"
      detail="参考老版 Profile 配置；分组统一通过 Group Type Fields 添加，并可为每个字段自定义组别顺序。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="Profile Columns">
        <div style={gridStyle}>
          <GroupFieldMultiSelect
            label="Group Type Fields"
            selected={stringList(current.grouptype_fields)}
            sourceContext={sourceContext}
            onChange={(next) => setField("grouptype_fields", next)}
            emptyLabel="No Profile group fields detected"
          />
          <GroupOrderEditor
            selectedFields={stringList(current.grouptype_fields)}
            sourceContext={sourceContext}
            value={current.group_order}
            onChange={(next) => setField("group_order", next)}
          />
          <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext} fields={stringList(current.grouptype_fields)} />
          <RangeFields value={current} setField={setField} sourceContext={sourceContext} parameterLabels />
          <GroupSpecSelect value={current} setField={setField} groupSpecs={groupSpecs} loadingSpecs={loadingSpecs} />
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
