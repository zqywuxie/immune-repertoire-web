import { useEffect, useLayoutEffect, useId, useState } from "react";
import { ApiError } from "../../shared/api/client";
import { getSampleFieldOptions, type SampleRecord, type SampleUpdatePayload } from "../../shared/api/samples";
import { useApi } from "../../shared/hooks/useApi";
import { Select } from "../../shared/components/Select";
import "./SampleEdit.css";
import { Sheet } from "../../shared/components/Sheet";
import "../assets/DataManagement.css";
import { registrationSource, manuallyMaintainedFields, sampleFieldLabels } from "./sampleDisplay";
import { UnsavedChangesGuard } from "../../shared/components/UnsavedChangesGuard";

export function SampleEditSheet({
  sample,
  open,
  onClose,
  onSave,
  onDraftChange,
}: {
  sample: SampleRecord;
  open: boolean;
  onClose: () => void;
  onSave: (data: SampleUpdatePayload) => Promise<void>;
  onDraftChange?: (dirty: boolean) => void;
}) {
  const [sampleName, setSampleName] = useState(sample.sample_name);
  const [chainFlag, setChainFlag] = useState(sample.chain_flag || "");
  const [isHealthy, setIsHealthy] = useState(sample.is_healthy || "");
  const [spices, setSpices] = useState(sample.spices || "");
  const [illness, setIllness] = useState(sample.illness || "");
  const [containMethod, setContainMethod] = useState(sample.contain_method || "");
  const [isoTag, setIsoTag] = useState(sample.iso_tag || "");
  const [sequenceId, setSequenceId] = useState(sample.sequence_id || "");
  const [institution, setInstitution] = useState(sample.institution || "");
  const [isPe, setIsPe] = useState(sample.is_pe || "");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [baseline, setBaseline] = useState(sample);
  const [conflict, setConflict] = useState<{sample: SampleRecord; conflicts: Record<string, {expected: string | null; current: string | null; submitted: string | null}>} | null>(null);

  const [discardOpen, setDiscardOpen] = useState(false);
  const suggestionId = useId();
  const dataset = typeof sample.extra_metadata.asset_set === "string" ? sample.extra_metadata.asset_set : "";
  const suggestions = useApi(() => getSampleFieldOptions(sample.project_id, "", dataset),
    [sample.project_id, dataset], open && !!sample.project_id && !!dataset);
  const candidates = suggestions.status === "ready" ? suggestions.data.fields || {} : {};
  const maintained = manuallyMaintainedFields(sample.extra_metadata);
  function textField(label: string, field: string, value: string, setValue: (value: string) => void, placeholder?: string) {
    const options = candidates[field]?.length ? [...new Set([...candidates[field], ...(value ? [value] : [])])] : [];
    const listId = `${suggestionId}-${field}`;
    return <label className="sample-edit-field"><span>{label}</span>
      <input className="input" value={value} onChange={event => setValue(event.target.value)} disabled={saving}
        placeholder={placeholder} list={options.length ? listId : undefined}/>
      {options.length > 0 && <datalist id={listId}>{options.map(option => <option key={option} value={option}/>)}</datalist>}
    </label>;
  }
  function choiceField(label: string, value: string, setValue: (value: string) => void, options: {value:string;label:string}[]) {
    const choices = [{value:"",label:"未设置"}, ...options];
    if (value && !choices.some(option => option.value === value)) choices.push({value,label:`${value}（原有值）`});
    return <div className="sample-edit-field"><span>{label}</span>
      <Select ariaLabel={label} value={value} options={choices} onChange={setValue} disabled={saving}/>
    </div>;
  }
  const current: SampleUpdatePayload = {
    sample_name: sampleName.trim(), chain_flag: chainFlag, is_healthy: isHealthy,
    spices, illness, contain_method: containMethod, iso_tag: isoTag,
    sequence_id: sequenceId, institution, is_pe: isPe,
  };
  const changes: SampleUpdatePayload = {};
  for (const key of Object.keys(current) as (keyof SampleUpdatePayload)[]) {
    if (current[key] !== (baseline[key as keyof SampleRecord] ?? "")) Object.assign(changes, { [key]: current[key] });
  }
  const dirty = open && Object.keys(changes).length > 0;
  useLayoutEffect(() => { onDraftChange?.(dirty || (open && saving)); }, [dirty, open, saving, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  function requestClose() {
    if (saving) return;
    if (dirty) setDiscardOpen(true); else onClose();
  }

  function reviewLatest() {
    if (!conflict) return;
    const edited = new Set(Object.keys(changes));
    const setters: Record<string, (value: string) => void> = {
      sample_name: setSampleName, chain_flag: setChainFlag, is_healthy: setIsHealthy,
      spices: setSpices, illness: setIllness, contain_method: setContainMethod,
      iso_tag: setIsoTag, sequence_id: setSequenceId, institution: setInstitution, is_pe: setIsPe,
    };
    for (const [field, setter] of Object.entries(setters)) {
      // Keep this draft's edits, while adopting concurrent edits to other fields.
      if (!edited.has(field)) setter(String(conflict.sample[field as keyof SampleRecord] ?? ""));
    }
    setBaseline(conflict.sample);
    setConflict(null);
    setSaveError("");
  }

  const handleSave = async () => {
    if (conflict) return;
    setSaving(true);
    setSaveError("");
    try {
      if (Object.keys(changes).length) await onSave({...changes, expected_values: Object.fromEntries(
        Object.keys(changes).map(field => {const value = baseline[field as keyof SampleRecord]; return [field, value == null ? null : String(value)];}))});
      onClose();
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "保存失败");
      if (err instanceof ApiError && err.status === 409) {
        const response = err.payload as {error_code?: string; details?: {sample: SampleRecord; conflicts: Record<string, {expected: string | null; current: string | null; submitted: string | null}>}};
        if (response?.error_code === "SAMPLE_RECORD_CHANGED" && response.details?.sample && response.details.conflicts) setConflict(response.details);
      }
    } finally {
      setSaving(false);
    }
  };

  return <>
    {!onDraftChange && <UnsavedChangesGuard when={dirty || (open && saving)} />}
    <Sheet open={open} onClose={requestClose} title="补充样本信息" panelClassName="sample-edit-panel">
      <form className="sample-edit-form" onSubmit={event => {event.preventDefault(); if (!saving && sampleName.trim()) void handleSave();}}>
        <div className="sample-edit-content">
          <div className="sample-edit-identity" aria-label="当前样本身份">
            <div><span>样本编号</span><strong>{sample.sample_id || "—"}</strong></div>
            <div><span>项目</span><strong>{sample.project_name || "—"}</strong></div>
            <div><span>数据集</span><strong>{dataset || "未标记来源"}</strong></div>
          </div>
          {conflict && <section className="sample-edit-conflict" aria-label="核对登记变化">
            <strong>这些字段在编辑期间发生了变化</strong>
            <dl>{Object.entries(conflict.conflicts).map(([field, values]) => <div key={field}>
              <dt>{sampleFieldLabels[field] || field}</dt>
              <dd>打开时：{values.expected || "未设置"}</dd><dd>最新值：{values.current || "未设置"}</dd>
              <dd>本次修改：{String(current[field as keyof SampleUpdatePayload] ?? "未设置")}</dd>
            </div>)}</dl>
            <p>原始输入文件不受影响。核对后可保留本次修改，其他字段会采用最新值。</p>
            <button type="button" className="btn btn-secondary" onClick={reviewLatest}>保留修改，更新对照</button>
          </section>}
          <p className="sample-edit-caption">登记信息独立保存，不会修改原始输入文件。</p>
          <section className="sample-edit-section" aria-label="样本基本信息">
            <h4>基本信息</h4><div className="sample-edit-grid">
              {textField("样本名称", "sample_name", sampleName, setSampleName)}
              {textField("序列编号", "sequence_id", sequenceId, setSequenceId)}
              {textField("物种", "spices", spices, setSpices, "选择已有值或输入，例如：人、小鼠")}
              {textField("疾病", "illness", illness, setIllness, "选择已有值或输入疾病名称")}
              {choiceField("健康状态", isHealthy, setIsHealthy, [{value:"yes",label:"健康"},{value:"no",label:"非健康"}])}
              {textField("所属机构", "institution", institution, setInstitution, "选择已有机构或输入新值")}
            </div>
          </section>
          <section className="sample-edit-section" aria-label="测序与登记信息">
            <h4>测序与登记</h4><div className="sample-edit-grid">
              {choiceField("链标记", chainFlag, setChainFlag, ["TRA","TRB","TRG","TRD","IGH","IGK","IGL"].map(value => ({value,label:value})))}
              {choiceField("双端测序", isPe, setIsPe, [{value:"yes",label:"是"},{value:"no",label:"否"}])}
              {textField("纳入方法", "contain_method", containMethod, setContainMethod, "选择已有方法或输入新值")}
              {textField("同型标签", "iso_tag", isoTag, setIsoTag)}
            </div>
          </section>
          {dataset && <div className="sample-edit-suggestions">
            {suggestions.status === "error" ? <p role="status">已有值建议暂时无法读取，仍可直接填写。<button type="button" className="btn btn-secondary" onClick={suggestions.refetch}>重新读取建议</button></p>
              : <p>{suggestions.status === "loading" || suggestions.status === "idle" ? "正在读取当前数据集的已有值建议…" : "已有值建议来自当前项目与数据集，也可直接填写新值。"}</p>}
          </div>}
          <details className="sample-edit-provenance" open={maintained.length > 0}>
            <summary>登记来源与人工维护</summary>
            <p>登记来源：{registrationSource(sample.extra_metadata)}</p>
            {maintained.length > 0 && <><strong>人工维护字段</strong><p>{maintained.map(field => sampleFieldLabels[field] || "其他补充字段").join("、")}</p>
              <p className="data-muted">这些字段在来源表更新后仍保留；本次保存只更新实际修改的字段。</p></>}
          </details>
        </div>
        <div className="sample-edit-footer">
          {saveError && <p className="data-error" role="alert">{saveError}</p>}

          <div><span>{dirty ? `已修改 ${Object.keys(changes).length} 个字段` : "修改后仅保存变更字段"}</span>
            <div className="data-row-actions"><button type="button" className="btn btn-secondary" onClick={requestClose} disabled={saving}>取消</button>
              <button type="submit" className="btn btn-primary" disabled={saving || !!conflict || !sampleName.trim()}>{saving ? "正在保存…" : "保存"}</button></div>
          </div>
        </div>
      </form>
    </Sheet>
    <Sheet open={discardOpen} layer={200} onClose={() => setDiscardOpen(false)} title="放弃未保存的样本信息">
      <p>样本信息尚未保存。关闭将放弃这些修改。</p><div className="data-row-actions">
        <button className="btn btn-primary" onClick={() => setDiscardOpen(false)}>继续编辑</button>
        <button className="btn btn-danger" onClick={() => {setDiscardOpen(false);onClose();}}>放弃修改并关闭</button>
      </div>
    </Sheet>
  </>;
}
