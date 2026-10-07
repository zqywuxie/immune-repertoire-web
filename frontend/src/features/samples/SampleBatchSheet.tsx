import { useLayoutEffect, useEffect, useMemo, useState } from "react";
import { Download, Upload, Check } from "lucide-react";
import { Sheet } from "../../shared/components/Sheet";
import { Select } from "../../shared/components/Select";
import { Pagination } from "../../shared/components/Pagination";
import { ProjectPicker } from "../projects/ProjectPicker";
import { useApi } from "../../shared/hooks/useApi";
import { listProjectDatasets } from "../../shared/api/projects";
import type { SampleRecord } from "../../shared/api/samples";
import { applySampleBatch, downloadSampleBatchTemplate, previewSampleBatchFile, previewSampleBatchRows } from "../../shared/api/sampleBatch";
import type { SampleBatchPreview, SampleBatchResultRow } from "../../shared/api/sampleBatch";
import { sampleFieldLabels } from "./sampleDisplay";
import "./SampleBatch.css";

const statusLabels = { new: "新增登记", update: "修改登记", unchanged: "无变化", unmatched: "未匹配", invalid: "需修改" };
export function SampleBatchSheet({ initialProjectId, initialAssetSet, selectedRecords, onClose, onSaved, onDraftChange }: {
  initialProjectId: string; initialAssetSet: string; selectedRecords: SampleRecord[];
  onClose: () => void; onSaved: () => void; onDraftChange: (dirty: boolean) => void;
}) {
  const selectedMode = selectedRecords.length > 0;
  const [method, setMethod] = useState<"field" | "file">(selectedMode ? "field" : "file");
  const fieldMode = selectedMode && method === "field";
  const [projectId, setProjectId] = useState(initialProjectId);
  const [assetSet, setAssetSet] = useState(initialAssetSet);
  const [file, setFile] = useState<File | null>(null);
  const [allowUnmatched, setAllowUnmatched] = useState(false);
  const [field, setField] = useState("illness");
  const [value, setValue] = useState("");
  const [clearField, setClearField] = useState(false);
  const [preview, setPreview] = useState<SampleBatchPreview | null>(null);
  const [results, setResults] = useState<Map<number, SampleBatchResultRow>>(new Map());
  const [busy, setBusy] = useState<"" | "template" | "preview" | "save">("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [page, setPage] = useState(1);
  const [discard, setDiscard] = useState(false);
  const datasets = useApi(() => listProjectDatasets(projectId), [projectId], !!projectId);
  const names = datasets.status === "ready" ? datasets.data.datasets.map(dataset => dataset.name) : [];
  const choices = [...new Set([...names, ...(assetSet ? [assetSet] : [])])];
  const dirty = !!busy || (!!preview && (!results.size || [...results.values()].some(row => row.status === "failed"))) || (!results.size && (!!file || clearField || !!value));
  useLayoutEffect(() => { onDraftChange(dirty); }, [dirty, onDraftChange]);
  useEffect(() => () => onDraftChange(false), [onDraftChange]);
  const pendingRows = useMemo(() => preview?.rows.filter(row => row.can_apply && !["saved", "unchanged"].includes(results.get(row.row)?.status || "")) || [], [preview, results]);
  const failedRows = [...results.values()].filter(row => row.status === "failed");
  const savedCount = [...results.values()].filter(row => row.status !== "failed").length;
  const shown = preview?.rows.slice((page - 1) * 50, page * 50) || [];
  const scopeReady = !!projectId && !!assetSet;
  function requestClose() { if (busy) return; if (dirty) setDiscard(true); else onClose(); }
  function editAgain() { setPreview(null); setResults(new Map()); setError(""); setNotice(""); setPage(1); }
  async function template() {
    setBusy("template"); setError(""); setNotice("");
    try {
      const blob = await downloadSampleBatchTemplate(projectId, assetSet, selectedMode ? selectedRecords.map(row => row.id) : undefined);
      const url = URL.createObjectURL(blob); const link = document.createElement("a");
      link.href = url; link.download = "样本批量登记模板.xlsx"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice("模板已准备，请按文本填写原始编号；空白默认不修改。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "模板下载失败，请重试。"); }
    finally { setBusy(""); }
  }
  async function inspect() {
    if (!scopeReady || busy || (!fieldMode && !file)) return;
    setBusy("preview"); setError(""); setNotice("");
    try {
      const response = fieldMode ? await previewSampleBatchRows(projectId, assetSet, selectedRecords.map(row => ({
        record_id: row.id, sample_id: String(row.extra_metadata.input_sample_id || row.sample_id || ""),
        fields: clearField ? {} : { [field]: value }, clear_fields: clearField ? [field] : [],
      }))) : selectedMode
        ? await previewSampleBatchFile(projectId, assetSet, file!, false, selectedRecords.map(row => row.id))
        : await previewSampleBatchFile(projectId, assetSet, file!, allowUnmatched);
      setPreview(response); setResults(new Map()); setPage(1);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "预览失败，选择和编辑内容已保留。"); }
    finally { setBusy(""); }
  }
  async function save(rows: number[]) {
    if (!preview || busy || !rows.length) return;
    setBusy("save"); setError(""); setNotice("");
    try {
      const response = await applySampleBatch(projectId, preview.preview_token, rows);
      setResults(previous => { const next = new Map(previous); response.rows.forEach(row => next.set(row.row, row)); return next; });
      if (response.rows.some(row => row.status === "saved")) onSaved();
      setNotice(response.rows.some(row => row.status === "failed") ? "已保留成功行，请查看未保存原因；可重试失败行或返回编辑后重新预览。" : "本次登记处理完成，原始输入文件保持不变。");
    } catch (reason) {
      setError(`${reason instanceof Error ? reason.message : "暂时无法确认保存结果。"} 原预览已保留，重试会核对已保存行，不会重复新增。`);
    } finally { setBusy(""); }
  }

  return <>
    <Sheet open onClose={requestClose} title={selectedMode ? `批量修改 ${selectedRecords.length} 条登记` : "批量样本登记"}>
      <div className="sample-batch-flow">
        <ol className="sample-batch-steps" aria-label="批量登记步骤">{["明确范围", "准备变更", "预览确认", "保存结果"].map((label, index) => <li key={label} className={(results.size ? 3 : preview ? 2 : scopeReady ? 1 : 0) === index ? "is-current" : ""}><span>{index + 1}</span>{label}</li>)}</ol>
        {!preview ? <>
          <div className="sample-batch-scope">
            {selectedMode ? <p>项目：{selectedRecords[0]?.project_name || "当前项目"} · 数据集：{assetSet} · 所选 {selectedRecords.length} 条</p> : <>
              <ProjectPicker label="登记项目" value={projectId} disabled={!!busy} onChange={id => { setProjectId(id); setAssetSet(""); setNotice(""); setError(""); }} />
              <label className="field-label">登记数据集<Select ariaLabel="登记数据集" value={assetSet} disabled={!!busy || !projectId} placeholder="请选择数据集" options={choices.map(name => ({ value: name, label: name }))} onChange={setAssetSet} /></label>
              {datasets.status === "error" && <p className="data-error" role="alert">数据集暂时无法读取。<button className="btn btn-secondary" onClick={datasets.refetch}>重新读取数据集</button></p>}
              {projectId && datasets.status === "ready" && !choices.length && <p className="data-muted">该项目尚未建立输入数据集，请先在项目数据中导入数据。</p>}
            </>}
          </div>
          <button className="btn btn-secondary" disabled={!scopeReady || !!busy} onClick={template}><Download size={16} />{busy === "template" ? "正在准备模板…" : selectedMode ? "下载所选登记模板" : "下载数据集登记模板"}</button>
          {selectedMode && <fieldset className="sample-batch-methods" disabled={!!busy}>
            <legend>选择修改方式</legend>
            <label className={method === "field" ? "is-selected" : ""}><input type="radio" name="sample-batch-method" value="field" checked={method === "field"} onChange={() => { setMethod("field"); setError(""); }} /><span><strong>统一修改字段</strong><small>为所选记录填写相同的新值</small></span></label>
            <label className={method === "file" ? "is-selected" : ""}><input type="radio" name="sample-batch-method" value="file" checked={method === "file"} onChange={() => { setMethod("file"); setError(""); }} /><span><strong>上传所选模板</strong><small>逐行填写不同内容，再预览确认</small></span></label>
          </fieldset>}
          {fieldMode ? <fieldset className="sample-batch-editor" disabled={!!busy}>
            <legend>对所选记录修改同一字段</legend>
            <label className="field-label">修改字段<Select value={field} ariaLabel="批量修改字段" options={Object.entries(sampleFieldLabels).map(([value, label]) => ({ value, label }))} onChange={next => { setField(next); setValue(""); setClearField(false); }} /></label>
            <label className="field-label">新值<input className="input" aria-label="批量字段新值" value={value} maxLength={field === "is_healthy" || field === "is_pe" ? 120 : 255} disabled={clearField} onChange={event => setValue(event.target.value)} placeholder="填写要保存的新值" /></label>
            {field !== "sample_name" && <label className="sample-batch-check"><input type="checkbox" checked={clearField} onChange={event => { setClearField(event.target.checked); setValue(""); }} />明确清空此字段</label>}
          </fieldset> : <>
            <label className="sample-batch-upload"><Upload size={22} /><strong>{file?.name || "选择填写后的登记表"}</strong><span>支持 Excel 或 UTF-8 CSV · 最多 5000 行、10 MB</span><span className="sample-batch-file-button" aria-hidden="true">{file ? "重新选择文件" : "选择文件"}</span><input className="sample-batch-file-input" type="file" aria-label="上传批量登记表" accept=".xlsx,.csv" disabled={!!busy} onChange={event => { setFile(event.target.files?.[0] || null); setError(""); setNotice(""); }} /></label>
            {selectedMode ? <p className="data-muted">本次仅修改所选 {selectedRecords.length} 条登记。请上传所选模板并保留登记记录标识，可删除无需修改的行。</p> : <label className="sample-batch-check"><input type="checkbox" checked={allowUnmatched} disabled={!!busy} onChange={event => setAllowUnmatched(event.target.checked)} />允许补充尚未关联输入的登记</label>}
            <p className="data-muted">未匹配补录不会加入分析样本。空白默认不修改；清空内容请填写模板中的“清空字段”。编号、记录标识和来源保持原身份。</p>
          </>}
          <div className="sample-batch-preview-actions"><button className="btn btn-primary" disabled={!scopeReady || !!busy || (fieldMode ? !clearField && !value.trim() : !file)} onClick={inspect}>{busy === "preview" ? "正在读取变更…" : "预览登记变更"}</button></div>
        </> : <>
          <div className="sample-batch-summary"><strong>{preview.project_name} · {preview.asset_set}</strong><p>共 {preview.rows.length} 条 · 新增 {preview.counts.new || 0} · 修改 {preview.counts.update || 0} · 无变化 {preview.counts.unchanged || 0} · 需核对 {(preview.counts.invalid || 0) + (preview.counts.unmatched || 0)}</p></div>
          {preview.rows.some(row => row.can_apply && !row.linked) && <p className="sample-batch-warning">含尚未关联输入的补充登记；确认保存后仍不会增加输入覆盖或分析样本。</p>}
          {!!results.size && <p className="sample-batch-result-summary" role="status">已处理 {savedCount} 条 · 保存失败 {failedRows.length} 条</p>}
          <div className="sample-batch-rows" aria-label="登记变更预览">{shown.map(row => {
            const outcome = results.get(row.row);
            return <article key={row.row} className={`sample-batch-row${outcome?.status === "failed" || !row.can_apply ? " needs-attention" : ""}`}>
              <div className="sample-batch-row-heading"><strong>第 {row.row} 条 · <code>{row.sample_id || "编号未填写"}</code></strong><span>{outcome ? outcome.status === "saved" ? "已保存" : outcome.status === "unchanged" ? "无变化" : "未保存" : statusLabels[row.status]}</span></div>
              <p className="data-muted">{outcome?.message || row.message}</p>
              {row.changes.length > 0 && <dl>{row.changes.map(change => <div key={change.field}><dt>{change.label}</dt><dd><span>{change.before || "未填写"}</span><span aria-hidden="true">→</span><strong>{change.after === null ? "明确清空" : change.after}</strong></dd></div>)}</dl>}
            </article>;
          })}</div>
          <Pagination pagination={{ page, page_size: 50, total: preview.rows.length, total_pages: Math.ceil(preview.rows.length / 50) }} onPageChange={setPage} />
          <div className="data-row-actions sample-batch-actions"><button className="btn btn-secondary" disabled={!!busy} onClick={editAgain}>返回编辑并重新预览</button>
            {pendingRows.length > 0 && <button className="btn btn-primary" disabled={!!busy} onClick={() => save(results.size ? pendingRows.map(row => row.row) : preview.rows.map(row => row.row))}><Check size={16} />{busy === "save" ? "正在核对并保存…" : error ? "核对并重试保存" : results.size ? "仅重试失败行" : `确认保存 ${pendingRows.length} 条`}</button>}
            {!pendingRows.length && results.size > 0 && <button className="btn btn-primary" onClick={requestClose}>完成并关闭</button>}
          </div>
        </>}
        {notice && <p className="data-notice" role="status">{notice}</p>}
        {error && <p className="data-error" role="alert">{error}</p>}
      </div>
    </Sheet>
    <Sheet open={discard} layer={120} onClose={() => setDiscard(false)} title="放弃未保存的批量登记">
      <p>将放弃本次未保存的选择与变更；已经保存的登记会保留。</p><div className="data-row-actions"><button className="btn btn-primary" onClick={() => setDiscard(false)}>继续编辑</button><button className="btn btn-danger" onClick={onClose}>放弃未保存内容</button></div>
    </Sheet>
  </>;
}
