import { useEffect, useState } from "react";
import { apiClient } from "../../shared/api/client";
import { listProjectAssets } from "../../shared/api/projects";

type Asset = {id: string; asset_type: string; original_name?: string; metadata?: Record<string, unknown>; metadata_json?: Record<string, unknown>};
type Schema = {columns: string[]; sheets: string[]; selected_sheet: string | null; preview_rows: string[][]; input_preparation?: {identifier_column?: string}};
export function InputMappingPanel({projectId, assetSet, onSaved}: {projectId: string; assetSet: string; onSaved: () => Promise<void> | void}) {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [assetId, setAssetId] = useState("");
  const [schema, setSchema] = useState<Schema | null>(null);
  const [sheet, setSheet] = useState<string | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    async function load() {
      const all: Asset[] = [];
      let page = 1;
      while (true) {
        const result = await listProjectAssets(projectId, {page, pageSize: 100});
        all.push(...result.assets as unknown as Asset[]);
        if (!result.pagination || page >= result.pagination.total_pages) break;
        page += 1;
      }
      if (active) setAssets(all.filter(asset => {
        const meta = asset.metadata_json || asset.metadata || {};
        const dataset = String(meta.asset_set || meta.dataset || meta.data_set || meta.group_label || meta.group || "Set1");
        return (!assetSet || dataset === assetSet) && ["profile", "datapoint", "transcriptome", "expression", "deconvolution", "cibersort"].includes(asset.asset_type);
      }));
    }
    load().catch(reason => {if (active) setError(reason instanceof Error ? reason.message : "文件列表读取失败");});
    return () => {active = false;};
  }, [projectId, assetSet]);
  async function inspect(id: string, selectedSheet?: string) {
    setBusy(true); setSchema(null); setError(""); setMessage(""); setIdentifier("");
    try {
      const result = await apiClient.post<Schema>(`/api/projects/${projectId}/assets/${id}/input-schema`, selectedSheet === undefined ? {} : {sheet_name: selectedSheet});
      setSchema(result); setSheet(result.selected_sheet);
      if (result.input_preparation?.identifier_column && result.columns.includes(result.input_preparation.identifier_column)) setIdentifier(result.input_preparation.identifier_column);
    } catch (reason) {setError(reason instanceof Error ? reason.message : "工作表读取失败");}
    finally {setBusy(false);}
  }
  async function save() {
    setBusy(true); setError(""); setMessage("");
    try {
      await apiClient.post(`/api/projects/${projectId}/assets/${assetId}/prepare-input`, {identifier_column: identifier, ...(sheet === null ? {} : {sheet_name: sheet})});
      setSchema(previous => previous ? {...previous, input_preparation: {identifier_column: identifier}} : previous);
      setMessage("映射已保存，正在重新检查数据集…");
      await onSaved();
      setMessage("映射已保存并重新检查。请重新确认分析分组、样本和指标。");
    } catch (reason) {setError(reason instanceof Error ? reason.message : "映射保存失败");}
    finally {setBusy(false);}
  }
  async function reset() {
    setBusy(true); setError(""); setMessage("");
    try {
      await apiClient.delete(`/api/projects/${projectId}/assets/${assetId}/prepare-input`);
      setSchema(previous => previous ? {...previous, input_preparation: undefined} : previous);
      setMessage("已恢复使用原始文件，正在重新检查…");
      await onSaved();
      setMessage("已恢复使用原始文件，请重新确认分析配置。历史整理文件仍保留。");
    } catch (reason) {setError(reason instanceof Error ? reason.message : "恢复原始输入失败");}
    finally {setBusy(false);}
  }
  return <details style={{padding: 16, border: "1px solid var(--separator)", borderRadius: 8}}>
    <summary>工作表与编号列设置</summary>
    <p>选择实际数据所在的工作表，以及样本编号列或基因编号列。保存后生成整理后的分析输入，原文件保留。</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <label className="field-label">原始数据文件<select className="input" value={assetId} disabled={busy} onChange={event => {setAssetId(event.target.value); if(event.target.value) void inspect(event.target.value); else setSchema(null);}}>
      <option value="">请选择文件</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.original_name || "未命名文件"}</option>)}
    </select></label>
    {schema && <div style={{display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 12, marginTop: 12}}>
      {!!schema.sheets.length && <label className="field-label">数据工作表<select className="input" value={sheet || ""} disabled={busy} onChange={event => void inspect(assetId, event.target.value)}>{schema.sheets.map(name => <option key={name}>{name}</option>)}</select></label>}
      <label className="field-label">样本编号列或基因编号列<select className="input" value={identifier} disabled={busy} onChange={event => setIdentifier(event.target.value)}><option value="">请选择编号列</option>{schema.columns.map((name, index) => <option key={index} value={name}>{name || "空列名"}</option>)}</select></label>
      <div style={{overflowX: "auto", maxWidth: "100%"}}><table><caption>原始数据预览（前五行）</caption><thead><tr>{schema.columns.map((column,index) => <th key={index}>{column}</th>)}</tr></thead><tbody>{schema.preview_rows.map((row,index) => <tr key={index}>{row.map((cell,column) => <td key={column}>{cell}</td>)}</tr>)}</tbody></table></div>
      {schema.input_preparation && <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void reset()}>恢复使用原始文件</button>}
      <button type="button" className="btn btn-primary" disabled={busy || !identifier} onClick={() => void save()}>保存映射并重新检查</button>
    </div>}
    {busy && <p role="status">正在处理数据…</p>}
  </details>;
}
