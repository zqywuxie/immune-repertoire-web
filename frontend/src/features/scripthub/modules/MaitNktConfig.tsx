import { useEffect, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import {
  CommonRunFields,
  Field,
  ModuleShell,
  PepCacheCardSelector,
  Section,
  gridStyle,
  inputStyle,
  setFieldValue,
  stringValue,
  useSyncedDefaults,
  withDefaults,
} from "./shared";

type MaitInspectResponse = {
  success: boolean;
  resolved_tra_path?: string;
  sample_columns?: string[];
  sample_count?: number;
};

export function MaitNktConfig({ sourceContext, value, onChange }: ModuleFormProps) {
  const [inspect, setInspect] = useState<MaitInspectResponse | null>(null);
  const [inspectNote, setInspectNote] = useState("");
  const current = withDefaults(value, {
    output_name: "",
    tra_source: "upload",
  });
  const setField = (key: string, next: unknown) => setFieldValue(current, onChange, key, next);
  useSyncedDefaults(value, current, onChange);

  useEffect(() => {
    if (current.tra_source === "upload" && !current.tra_path) {
      setInspect(null);
      setInspectNote("");
      return;
    }
    if (current.tra_source === "pep_analysis" && !current.tra_path && !current.source_job_id) {
      setInspect(null);
      setInspectNote("检查特征前，请先选择受体 α 链缓存。");
      return;
    }
    let cancelled = false;
    inspectScriptHubModule<MaitInspectResponse>("mait-nkt", {
      profile_path: sourceContext?.profilePath,
      project_id: sourceContext?.projectId,
      asset_set: sourceContext?.assetSetId,
      upstream_artifact_id: current.upstream_artifact_id,
      tra_source: current.tra_source,
      tra_path: current.upstream_artifact_id ? undefined : current.tra_path,
      source_job_id: current.source_job_id,
    })
      .then((data) => {
        if (cancelled) return;
        setInspect(data);
        const defaults: Record<string, unknown> = {
          mait_nkt_inspect_ok: true,
          resolved_tra_path: data.resolved_tra_path,
        };
        onChange({ ...current, ...defaults });
        setInspectNote(`特征输入检查已读取 ${data.sample_count || data.sample_columns?.length || 0} 个受体 α 链样本列。`);
      })
      .catch((error) => {
        if (!cancelled) {
          setInspect(null);
          onChange({ ...current, mait_nkt_inspect_ok: false });
          setInspectNote(error instanceof Error ? error.message : "特征输入检查失败");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath, sourceContext?.projectId, sourceContext?.assetSetId, current.upstream_artifact_id, current.tra_source, current.tra_path, current.source_job_id]);

  return (
    <ModuleShell
      title="MAIT / NKT"
      detail="选择受体 α 链数据，可使用上传的数据表或已有克隆分析缓存。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="受体 α 链数据来源">
        <div style={gridStyle}>
          <Field label="受体 α 链数据来源">
            <select
              value={stringValue(current.tra_source, "upload")}
              onChange={(event) => onChange({ ...current, tra_source: event.target.value, tra_path: undefined, source_job_id: undefined, mait_nkt_inspect_ok: undefined })}
              style={inputStyle}
            >
              <option value="upload">上传的受体 α 链数据表</option>
              <option value="pep_analysis">克隆共享结果</option>
            </select>
          </Field>
          {current.tra_source === "upload" ? (
            <Field label="受体 α 链数据路径">
              <input value={stringValue(current.upstream_artifact_id || current.tra_path)} onChange={(event) => setField("tra_path", event.target.value || undefined)} placeholder="使用上传数据时必填" style={inputStyle} />
            </Field>
          ) : (
            <PepCacheCardSelector
              sourceContext={sourceContext}
              cacheType="mait-nkt"
              value={stringValue(current.upstream_artifact_id || current.tra_path)}
              label="克隆受体 α 链缓存"
              emptyText="未找到含受体 α 链数据的缓存，请先运行相应克隆分析或上传受体 α 链数据表。"
              onSelect={(candidate) => onChange({
                ...current,
                tra_source: "pep_analysis",
                tra_path: candidate.path,
                source_job_id: candidate.job_id || current.source_job_id,
                pep_cache_id: candidate.asset_id || candidate.id,
                upstream_artifact_id: candidate.artifact_id,
                mait_nkt_inspect_ok: undefined,
              })}
            />
          )}
        </div>
      </Section>
      <CommonRunFields value={current} setField={setField} sourceContext={sourceContext} />
    </ModuleShell>
  );
}
