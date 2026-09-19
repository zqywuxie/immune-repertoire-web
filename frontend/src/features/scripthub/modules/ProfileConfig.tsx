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
      project_id: sourceContext.projectId,
      asset_set: sourceContext.assetSetId,
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
        setInspectNote("已读取指标范围，请确认分组列和要比较的指标。");
      })
      .catch((error) => {
        if (!cancelled) setInspectNote(error instanceof Error ? error.message : "读取 Profile 失败");
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath]);

  return (
    <ModuleShell
      title="指标分组箱线图"
      detail="选择分组列与指标范围，按样本比较组间分布，并输出箱线图和统计表。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="分组与分析指标">
        <div style={gridStyle}>
          <GroupFieldMultiSelect
            label="分组列（必选）"
            selected={stringList(current.grouptype_fields)}
            sourceContext={sourceContext}
            onChange={(next) => setField("grouptype_fields", next)}
            emptyLabel="未检测到分组列，请返回检查 样本指标表"
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
