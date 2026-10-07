import { useEffect, useRef, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  CommonRunFields, Field, GroupFieldSelect, GroupOrderEditor, GroupValueSamplePicker,
  ModuleShell, PepCacheCardSelector, Section, gridStyle, inputStyle, setFieldValue,
  stringValue, useSyncedDefaults, withDefaults,
} from "./shared";

type MaitInspectResponse = {
  success: boolean;
  resolved_tra_path?: string;
  sample_columns?: string[];
  sample_count?: number;
};

export function MaitNktConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspectNote, setInspectNote] = useState("");
  const current = withDefaults(value, {
    output_name: "", tra_source: "pep_analysis", group_field: "", batch_field: "",
  });
  const latest = useRef({ current, onChange });
  latest.current = { current, onChange };
  const setField = (key: string, next: unknown) => {
    if (key === "batch_field") onChange({ ...current, batch_field: next, selected_samples_by_group: undefined,
      group_sample_identity: next ? "batch_sample" : "sample", mait_nkt_inspect_ok: false });
    else if (key === "group_field") onChange({ ...current, group_field: next,
      selected_group_values: undefined, selected_samples_by_group: undefined, mait_nkt_inspect_ok: false });
    else if (key === "selected_samples_by_group") onChange({ ...current, selected_samples_by_group: next,
      group_sample_identity: current.batch_field ? "batch_sample" : "sample" });
    else setFieldValue(current, onChange, key, next);
  };
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    setInspectNote("");
    if (current.tra_source === "upload" && !current.tra_path) return;
    if (current.tra_source === "pep_analysis" && !current.tra_path && !current.source_job_id && !current.upstream_artifact_id) {
      setInspectNote("请选择克隆共享结果；没有可用结果时，先完成受体 α 链的克隆共享分析。");
      return;
    }
    let cancelled = false;
    const state = latest.current;
    state.onChange({ ...state.current, mait_nkt_inspect_ok: false });
    setInspectNote("正在检查受体 α 链数据、样本编号与分组…");
    inspectScriptHubModule<MaitInspectResponse>("mait-nkt", {
      profile_path: sourceContext?.profilePath, project_id: sourceContext?.projectId,
      asset_set: sourceContext?.assetSetId, upstream_artifact_id: current.upstream_artifact_id,
      tra_source: current.tra_source, tra_path: current.upstream_artifact_id ? undefined : current.tra_path,
      source_job_id: current.source_job_id, group_field: current.group_field,
      batch_field: current.batch_field,
    }).then((data) => {
      if (cancelled) return;
      const state = latest.current;
      state.onChange({ ...state.current, mait_nkt_inspect_ok: true, resolved_tra_path: data.resolved_tra_path });
      setInspectNote(`已匹配 ${data.sample_count ?? data.sample_columns?.length ?? 0} 个受体 α 链样本；下方选择决定本次实际纳入范围。`);
    }).catch((error) => {
      if (cancelled) return;
      const state = latest.current;
      state.onChange({ ...state.current, mait_nkt_inspect_ok: false });
      setInspectNote(error instanceof Error ? error.message : "受体 α 链输入检查失败");
    });
    return () => { cancelled = true; };
  }, [sourceContext?.profilePath, sourceContext?.projectId, sourceContext?.assetSetId,
    current.upstream_artifact_id, current.tra_source, current.tra_path, current.source_job_id,
    current.group_field, current.batch_field]);

  return (
    <ModuleShell title="MAIT / NKT" detail="复用受体 α 链的克隆共享结果，按样本分组比对参考序列并计算比例。" sourceContext={sourceContext}>
      <Section title="受体 α 链数据来源">
        <div style={gridStyle}>
          <Field label="受体 α 链数据来源">
            <select aria-label="受体 α 链数据来源" value={stringValue(current.tra_source, "pep_analysis")}
              onChange={(event) => onChange({ ...current, tra_source: event.target.value,
                tra_path: undefined, source_job_id: undefined, upstream_artifact_id: undefined,
                pep_cache_id: undefined, resolved_tra_path: undefined, mait_nkt_inspect_ok: false })} style={inputStyle}>
              <option value="pep_analysis">克隆共享结果</option>
              <option value="upload">已有受体 α 链表（高级）</option>
            </select>
          </Field>
          {current.tra_source === "upload" ? (
            <Field label="受体 α 链数据路径">
              <input value={stringValue(current.tra_path)} onChange={(event) => setField("tra_path", event.target.value || undefined)} placeholder="填写已有受体 α 链表的路径" style={inputStyle} />
            </Field>
          ) : (
            <PepCacheCardSelector sourceContext={sourceContext} cacheType="mait-nkt"
              value={stringValue(current.upstream_artifact_id || current.tra_path)} label="受体 α 链前置结果"
              emptyText="当前数据集没有可用的受体 α 链结果，请先完成克隆共享分析。"
              onSelect={(candidate) => onChange({ ...current, tra_source: "pep_analysis", tra_path: candidate.path,
                source_job_id: candidate.job_id, pep_cache_id: candidate.asset_id || candidate.id,
                upstream_artifact_id: candidate.artifact_id, resolved_tra_path: undefined, mait_nkt_inspect_ok: false,
                group_field: current.group_field || candidate.group_field || (candidate.group_fields?.length === 1 ? candidate.group_fields[0] : ""),
              })} />
          )}
        </div>
      </Section>
      <Section title="分组与样本范围">
        <div style={gridStyle}>
          <GroupFieldSelect label="分组字段（可选）" value={stringValue(current.group_field)} sourceContext={sourceContext}
            optional emptyLabel="不分组（全部样本）" onChange={(next) => setField("group_field", next || undefined)} />
          <GroupFieldSelect label="批次字段（可选）" value={stringValue(current.batch_field)} sourceContext={sourceContext}
            optional emptyLabel="未选择批次字段" onChange={(next) => setField("batch_field", next || undefined)} />
          {current.group_field ? <>
            <GroupOrderEditor selectedFields={[stringValue(current.group_field)]} sourceContext={sourceContext}
              value={current.group_order} onChange={(next) => setField("group_order", next)} />
            <GroupValueSamplePicker value={current} setField={setField} sourceContext={sourceContext}
              fields={[stringValue(current.group_field)]} batchField={stringValue(current.batch_field) || undefined} />
          </> : null}
        </div>
        <p style={{ fontSize: "0.82rem", lineHeight: 1.7, color: "var(--text-secondary)" }}>
          跨批次同名样本需选择与前置分析一致的批次字段。比例按各样本的受体 α 链计数计算；分组检验沿用 p 值 0.05 的判定。
        </p>
      </Section>
      {inspectNote && <div role="status" style={{ fontSize: "0.82rem", lineHeight: 1.7, color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} showPvalue={false} />
    </ModuleShell>
  );
}
