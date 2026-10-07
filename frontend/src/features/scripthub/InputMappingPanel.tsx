import { useEffect, useMemo, useState } from "react";
import { apiClient } from "../../shared/api/client";
import type { ProjectAsset } from "../../shared/types/domain";
import { listProjectAssets } from "../../shared/api/projects";
import { parseSampleIdMappings, SampleIdMappingEditor, type SampleIdMapping } from "./SampleIdMappingEditor";

type Asset = {id: string; asset_type: string; original_name?: string; metadata?: Record<string, unknown>; metadata_json?: Record<string, unknown>};
type MatrixOrientation = "genes_are_rows" | "samples_are_rows";
type Schema = {columns: string[]; sheets: string[]; selected_sheet: string | null; preview_rows: string[][]; requires_sheet_selection?: boolean; input_preparation?: {identifier_column?: string; orientation?: MatrixOrientation; sample_mappings?: SampleIdMapping[]; batch_field?: string}};
const canonicalKind = (kind: string) => ({datapoint:"profile", expression:"transcriptome", cibersort:"deconvolution"} as Record<string,string>)[kind] || kind;
export function InputMappingPanel({projectId, assetSet, inputTypes, selectedAssets, onSaved}: {projectId: string; assetSet: string; inputTypes?: string[]; selectedAssets?: ProjectAsset[]; onSaved: () => Promise<void> | void}) {
  const inputScopeKey = JSON.stringify(inputTypes ?? null);
  const [expanded, setExpanded] = useState(false);
  // Only identity changes reset an edited mapping; refreshed validation metadata does not.
  const selectedAssetsKey = selectedAssets === undefined ? null : JSON.stringify(selectedAssets.filter(asset => {
    const meta = asset.metadata || {};
    const dataset = String(meta.asset_set || meta.dataset || meta.data_set || meta.group_label || meta.group || "Set1");
    const kind = canonicalKind(asset.asset_type);
    return asset.project_id === projectId && dataset === assetSet && ["profile", "transcriptome", "deconvolution"].includes(kind) && (!inputTypes || inputTypes.includes(kind));
  }).map(({id, asset_type, original_name}) => ({id, asset_type, original_name})));
  const [assets, setAssets] = useState<Asset[]>([]);
  const [assetId, setAssetId] = useState("");
  const [schema, setSchema] = useState<Schema | null>(null);
  const [sheet, setSheet] = useState<string | null>(null);
  const [identifier, setIdentifier] = useState("");
  const [orientation, setOrientation] = useState<MatrixOrientation>("genes_are_rows");
  const [batchField, setBatchField] = useState("");
  const [mappingText, setMappingText] = useState("");
  const {mappings: sampleMappings, error: mappingError} = useMemo(() => parseSampleIdMappings(mappingText, Boolean(batchField)), [mappingText, batchField]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const selectedAsset = assets.find(asset => asset.id === assetId);
  const isProfile = ["profile", "datapoint"].includes(selectedAsset?.asset_type || "");
  const isTranscriptome = ["transcriptome", "expression"].includes(selectedAsset?.asset_type || "");

  useEffect(() => {
    setAssetId(""); setSchema(null); setMappingText(""); setBatchField(""); setAssets([]); setError(""); setMessage("");
  }, [projectId, assetSet, inputScopeKey, selectedAssetsKey]);
  useEffect(() => {
    if (!expanded || !assetSet) return;
    let active = true;
    async function load() {
      if (selectedAssetsKey !== null) {
        if (active) setAssets(JSON.parse(selectedAssetsKey) as Asset[]);
        return;
      }
      const scope: string[] | null = JSON.parse(inputScopeKey);
      const kinds = ["profile", "transcriptome", "deconvolution"].filter(kind => !scope || scope.includes(kind));
      const pages = await Promise.all(kinds.map(assetType => listProjectAssets(projectId, {page: 1, pageSize: 50, inputsOnly: true, assetSet, assetType})));
      const rows = pages.flatMap(page => page.assets as unknown as Asset[]).filter(asset => {
        const meta = asset.metadata_json || asset.metadata || {};
        const dataset = String(meta.asset_set || meta.dataset || meta.data_set || meta.group_label || meta.group || "Set1");
        return dataset === assetSet && kinds.includes(canonicalKind(asset.asset_type));
      });
      if (active) setAssets([...new Map(rows.map(asset => [asset.id, asset])).values()]);
    }
    load().catch(reason => {if (active) setError(reason instanceof Error ? reason.message : "文件列表读取失败");});
    return () => {active = false;};
  }, [expanded, projectId, assetSet, inputScopeKey, selectedAssetsKey]);
  async function inspect(id: string, selectedSheet?: string) {
    setBusy(true); setSchema(null); setError(""); setMessage(""); setIdentifier(""); setMappingText(""); setBatchField("");
    try {
      const result = await apiClient.post<Schema>(`/api/projects/${projectId}/assets/${id}/input-schema`, selectedSheet === undefined ? {} : {sheet_name: selectedSheet});
      setSchema(result); setSheet(result.selected_sheet);
      const restoredBatch = result.input_preparation?.batch_field || "";
      setBatchField(restoredBatch);
      setMappingText((result.input_preparation?.sample_mappings || []).map(item => `${item.source_sample}\t${item.target_sample}${restoredBatch ? `\t${item.source_batch || ""}` : ""}`).join("\n"));
      setOrientation(result.input_preparation?.orientation || "genes_are_rows");
      if (result.input_preparation?.identifier_column && result.columns.includes(result.input_preparation.identifier_column)) setIdentifier(result.input_preparation.identifier_column);
    } catch (reason) {setError(reason instanceof Error ? reason.message : "工作表读取失败");}
    finally {setBusy(false);}
  }
  async function save() {
    if (mappingError) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await apiClient.post(`/api/projects/${projectId}/assets/${assetId}/prepare-input`, {identifier_column: identifier, ...(isProfile && batchField ? {batch_field: batchField} : {}), ...(sampleMappings.length ? {sample_mappings: sampleMappings} : {}), ...(isTranscriptome ? {orientation} : {}), ...(sheet === null ? {} : {sheet_name: sheet})});
      setSchema(previous => previous ? {...previous, input_preparation: {identifier_column: identifier, orientation: isTranscriptome ? orientation : undefined, sample_mappings: sampleMappings, batch_field: batchField || undefined}} : previous);
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
      setOrientation("genes_are_rows"); setMappingText(""); setBatchField("");
      setMessage("已恢复使用原始文件，正在重新检查…");
      await onSaved();
      setMessage("已恢复使用原始文件，请重新确认分析配置。历史整理文件仍保留。");
    } catch (reason) {setError(reason instanceof Error ? reason.message : "恢复原始输入失败");}
    finally {setBusy(false);}
  }
  return <details open={expanded} onToggle={event => setExpanded(event.currentTarget.open)} style={{padding: 16, border: "1px solid var(--separator)", borderRadius: 8}}>
    <summary onClick={event => {event.preventDefault(); setExpanded(value => !value);}}>工作表、编号列与样本编号对应</summary>
    {expanded && <>
    {!assetSet ? <p>请先选择本次分析的数据集。</p> : selectedAssetsKey !== null && !assets.length && <p>本次未选择可整理的表格，请先在数据选择步骤选择文件。</p>}
    <p>{isTranscriptome ? "选择工作表、矩阵方向和对应编号列。保存后会整理成基因按行、样本按列的分析输入，原文件保留。" : "选择数据所在的工作表和样本编号列。保存后生成整理后的分析输入，原文件保留。"}</p>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    <label className="field-label">原始数据文件<select aria-label="原始数据文件" className="input" value={assetId} disabled={busy} onChange={event => {setAssetId(event.target.value); if(event.target.value) void inspect(event.target.value); else setSchema(null);}}>
      <option value="">请选择文件</option>{assets.map(asset => <option key={asset.id} value={asset.id}>{asset.original_name || "未命名文件"}</option>)}
    </select></label>
    {schema && <div style={{display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: 12, marginTop: 12}}>
      {!!schema.sheets.length && <label className="field-label">数据工作表<select aria-label="数据工作表" className="input" value={schema.requires_sheet_selection ? "" : sheet || ""} disabled={busy} onChange={event => void inspect(assetId, event.target.value)}><option value="">请选择工作表</option>{schema.sheets.map(name => <option key={name} value={name}>{name}</option>)}</select></label>}
      {isTranscriptome && <label className="field-label">转录组矩阵方向<select aria-label="转录组矩阵方向" className="input" value={orientation} disabled={busy} onChange={event => {setOrientation(event.target.value as MatrixOrientation); setIdentifier("");}}>
        <option value="genes_are_rows">基因按行、样本按列</option>
        <option value="samples_are_rows">样本按行、基因按列</option>
      </select></label>}
      <label className="field-label">{isTranscriptome && orientation === "samples_are_rows" ? "样本编号列" : isTranscriptome ? "基因编号列" : "样本编号列"}<select aria-label={isTranscriptome && orientation !== "samples_are_rows" ? "基因编号列" : "样本编号列"} className="input" value={identifier} disabled={busy} onChange={event => {setIdentifier(event.target.value); if (event.target.value === batchField) setBatchField("");}}><option value="">请选择编号列</option>{schema.columns.map((name, index) => <option key={index} value={name}>{name || "空列名"}</option>)}</select></label>
      {isProfile && <div style={{display: "grid", gap: 6}}>
        <label className="field-label">输入表批次字段（可选）<select aria-label="输入表批次字段（可选）" className="input" value={batchField} disabled={busy || Boolean(schema.requires_sheet_selection)} onChange={event => setBatchField(event.target.value)}>
          <option value="">不使用批次，样本编号须唯一</option>{schema.columns.filter(name => name !== identifier).map(name => <option key={name} value={name}>{name}</option>)}
        </select></label>
        <p style={{margin: 0, fontSize: "0.85rem", color: "var(--text-secondary)"}}>不同批次存在同名样本时请选择批次字段。批次值应与克隆序列所在的批次目录一致，分析配置也需选择该批次字段。</p>
      </div>}
      <div className="input-mapping-table-wrap"><table className="input-mapping-table"><caption>原始数据预览（前五行）</caption><thead><tr>{schema.columns.map((column,index) => <th key={index}>{column}</th>)}</tr></thead><tbody>{schema.preview_rows.map((row,index) => <tr key={index}>{row.map((cell,column) => <td key={column}>{cell}</td>)}</tr>)}</tbody></table></div>
      <SampleIdMappingEditor batchScoped={Boolean(batchField)} value={mappingText} mappings={sampleMappings} error={mappingError} disabled={busy || Boolean(schema.requires_sheet_selection)} onChange={setMappingText} />
      {schema.requires_sheet_selection && <p role="status">检测到多个工作表，请先选择实际数据所在的工作表。</p>}
      {schema.input_preparation && <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => void reset()}>恢复使用原始文件</button>}
      <button type="button" className="btn btn-primary" disabled={busy || !identifier || Boolean(schema.requires_sheet_selection) || Boolean(mappingError)} onClick={() => void save()}>保存映射并重新检查</button>
    </div>}
    {busy && <p role="status">正在处理数据…</p>}
    </>}
  </details>;
}
