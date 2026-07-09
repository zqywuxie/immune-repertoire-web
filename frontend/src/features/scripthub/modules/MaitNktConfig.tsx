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
      setInspectNote("Select a PEP TRA cache before inspecting MAIT/NKT.");
      return;
    }
    let cancelled = false;
    inspectScriptHubModule<MaitInspectResponse>("mait-nkt", {
      profile_path: sourceContext?.profilePath,
      project_id: sourceContext?.projectId,
      tra_source: current.tra_source,
      tra_path: current.tra_path,
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
        setInspectNote(`MAIT/NKT inspect loaded ${data.sample_count || data.sample_columns?.length || 0} TRA sample columns.`);
      })
      .catch((error) => {
        if (!cancelled) {
          setInspect(null);
          onChange({ ...current, mait_nkt_inspect_ok: false });
          setInspectNote(error instanceof Error ? error.message : "MAIT/NKT inspect failed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [sourceContext?.profilePath, sourceContext?.projectId, current.tra_source, current.tra_path, current.source_job_id]);

  return (
    <ModuleShell
      title="MAIT / NKT"
      detail="MAIT/NKT 只需要选择 TRA Source；可来自上传 TRA CSV 或包含 TRA 的 PEP cache。"
      sourceContext={sourceContext}
    >
      {inspectNote && <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)" }}>{inspectNote}</div>}
      <Section title="TRA Source">
        <div style={gridStyle}>
          <Field label="TRA Source">
            <select
              value={stringValue(current.tra_source, "upload")}
              onChange={(event) => onChange({ ...current, tra_source: event.target.value, tra_path: undefined, source_job_id: undefined, mait_nkt_inspect_ok: undefined })}
              style={inputStyle}
            >
              <option value="upload">uploaded TRA CSV</option>
              <option value="pep_analysis">PEP shared result</option>
            </select>
          </Field>
          {current.tra_source === "upload" ? (
            <Field label="TRA Path">
              <input value={stringValue(current.tra_path)} onChange={(event) => setField("tra_path", event.target.value || undefined)} placeholder="required for upload source" style={inputStyle} />
            </Field>
          ) : (
            <PepCacheCardSelector
              sourceContext={sourceContext}
              cacheType="mait-nkt"
              value={stringValue(current.tra_path)}
              label="PEP TRA Cache"
              emptyText="No PEP cache with TRA data found. Run PEP Analysis with TRA chain or provide a TRA CSV path."
              onSelect={(candidate) => onChange({
                ...current,
                tra_source: "pep_analysis",
                tra_path: candidate.path,
                source_job_id: candidate.job_id || current.source_job_id,
                pep_cache_id: candidate.asset_id || candidate.id,
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
