import { AssetResultProvenance } from "./AssetResultProvenance";
import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { Download, Trash2, Pencil, Save, FileSearch, MoreHorizontal, X } from "lucide-react";
import { assetDownloadUrl, assetPreviewUrl, getProjectAsset } from "../../shared/api/projects";
import { useApi } from "../../shared/hooks/useApi";
import { apiClient } from "../../shared/api/client";
import { AssetLineage } from "./AssetLineage";
import { AssetInputPreview } from "./AssetInputPreview";
import type { ProjectAsset } from "../../shared/types/domain";
import { UnsavedChangesGuard } from "../../shared/components/UnsavedChangesGuard";
import { Sheet } from "../../shared/components/Sheet";
import { InputValidationGuidance, inputValidationAction } from "./InputValidationGuidance";
import { Select } from "../../shared/components/Select";
import { StatusBadge } from "../../shared/components/StatusBadge";
import { getAssetSetName, getAssetSetLabel, isInputAsset } from "./assetSets";
import { projectAssetDetailPath } from "./assetSets";
import "./DataManagement.css";

import { assetTypeLabels, validationLabels } from "./assetLabels";
export { assetTypeLabels, validationLabels } from "./assetLabels";
import { AssetMobileList } from "./AssetMobileList";
import { useMediaQuery } from "../../shared/hooks/useMediaQuery";
import { usePageActivity } from "../../shared/hooks/usePageActivity";

import { FILE_SELECTION_LIMIT, type AssetSelection } from "./useAssetSelection";

type Props = { selection?: AssetSelection; active?: boolean; assetSet?: string; focusedAssetId?: string; onViewAsset?: (id: string) => void; onCloseDetail?: () => void; assets: ProjectAsset[]; loading: boolean; emptyLabel?: string; projectId?: string;
  onAssetDeleted?: () => void; onDraftChange?: (dirty: boolean) => void; showSelect?: boolean; showGroup?: boolean; showStatus?: boolean; showDatasetFilter?: boolean; };

function metadata(asset: ProjectAsset): Record<string, any> { return asset.metadata || {}; }
function fileName(asset: ProjectAsset) {
  return asset.original_name || asset.storage_path?.replace(/\\/g, "/").split("/").filter(Boolean).pop() || asset.id;
}
function downloadHref(asset: ProjectAsset) {
  return String((asset as ProjectAsset & { download_url?: string }).download_url || assetDownloadUrl(asset.id));
}
function formatSize(size: number) {
  let value = size || 0, index = 0; const units = ["B", "KB", "MB", "GB"];
  while (value >= 1024 && index < 3) { value /= 1024; index++; }
  return `${value.toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function AssetTable({ assets, loading, emptyLabel = "暂无文件。", projectId,
  onAssetDeleted, onDraftChange, selection, active = true, assetSet = "", focusedAssetId = "", onViewAsset, onCloseDetail, showSelect = true, showGroup = false, showStatus = false, showDatasetFilter = true }: Props) {
  const mobile = useMediaQuery("(max-width: 768px)");
  const pageActive = usePageActivity(active);
  const [actionAsset, setActionAsset] = useState<ProjectAsset | null>(null);
  const [localSelected, setLocalSelected] = useState<Set<string>>(new Set());
  const selected = selection ? new Set(selection.items.map(asset=>asset.id)) : localSelected;
  const setSelected = (update:Set<string> | ((previous:Set<string>)=>Set<string>)) => {
    if(selection)selection.change(update,assets);else setLocalSelected(update);
  };
  const [selectionOpen,setSelectionOpen] = useState(false);
  const [groupFilter, setGroupFilter] = useState("");
  const [confirmation, setConfirmation] = useState<ProjectAsset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [referenceLinks,setReferenceLinks] = useState<Array<{label:string;href:string}>>([]);
  const [notice, setNotice] = useState("");
  const [editAsset, setEditAsset] = useState<ProjectAsset | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [discardEdit, setDiscardEdit] = useState(false);
  const [viewAsset, setViewAsset] = useState<ProjectAsset | null>(null);
  const scopeMismatch = !!viewAsset && !!assetSet && isInputAsset(viewAsset) && getAssetSetName(viewAsset) !== assetSet;
  const focused = useApi(() => getProjectAsset(projectId!, focusedAssetId), [projectId, focusedAssetId], pageActive && !!projectId && !!focusedAssetId);
  useEffect(() => { setViewAsset(null); }, [focusedAssetId]);
  useEffect(() => {
    if (focusedAssetId && focused.status === "ready" && focused.data.asset.id === focusedAssetId) setViewAsset(focused.data.asset);
  }, [focusedAssetId, focused.status === "ready" ? focused.data : null]);
  const focusedValidationState = viewAsset ? metadata(viewAsset).validation?.status : "";
  useEffect(() => {
    if (!pageActive || !focusedAssetId || focusedValidationState !== "pending") return;
    const timer = setInterval(focused.refetch, 5000);
    return () => clearInterval(timer);
  }, [pageActive, focusedAssetId, focusedValidationState, focused.refetch]);
  function openView(asset: ProjectAsset) { if (onViewAsset) onViewAsset(asset.id); else setViewAsset(asset); }
  function closeView() { setViewAsset(null); onCloseDetail?.(); }
  const groups = useMemo(() => [...new Set(assets.map(getAssetSetName))].sort(), [assets]);
  const filtered = useMemo(() => groupFilter ? assets.filter(asset => getAssetSetName(asset) === groupFilter) : assets, [assets, groupFilter]);
  const selectedAssets = selection ? selection.items.map(item=>assets.find(asset=>asset.id===item.id) || item) : filtered.filter(asset => selected.has(asset.id));
  const offPageCount = selectedAssets.filter(asset=>!filtered.some(item=>item.id===asset.id)).length;
  const atLimit = !!selection && selected.size >= FILE_SELECTION_LIMIT;
  function toggleAll() {
    setSelected(previous=>{
      const next=new Set(previous);
      for(const asset of filtered){if(allSelected)next.delete(asset.id);else if(!selection || next.size<FILE_SELECTION_LIMIT)next.add(asset.id);}
      return next;
    });
  }
  const allSelected = filtered.length > 0 && filtered.every(asset => selected.has(asset.id));
  const hasValidation = assets.some(isInputAsset);
  const assetIds = assets.map(asset => asset.id).join("|");
  useEffect(() => { if (!selection && !loading) setLocalSelected(previous => new Set([...previous].filter(id => assets.some(asset => asset.id === id)))); }, [assetIds, loading]);
  useEffect(() => { if(!selection)setLocalSelected(new Set()); setConfirmation([]); setError(""); setSelectionOpen(false); }, [projectId, groupFilter]);
  useEffect(() => {
    if (!loading) setViewAsset(previous => previous ? assets.find(asset => asset.id === previous.id) || previous : null);
  }, [assets, loading]);
  const editDirty = !!editAsset && (
    (isInputAsset(editAsset) && editLabel.trim() !== getAssetSetName(editAsset)) ||
    editDescription !== String(metadata(editAsset).description || "")
  );
  const editPending = editDirty || (!!editAsset && busy);
  useLayoutEffect(() => { onDraftChange?.(editPending); }, [editPending, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  function closeEdit() {
    if (busy) return;
    if (editDirty) setDiscardEdit(true); else setEditAsset(null);
  }
  const refresh = () => { apiClient.invalidateCache(); onAssetDeleted?.(); };
  const assetUrl = (id: string) => `${import.meta.env.VITE_API_BASE_URL || ""}/api/${projectId ? `projects/${projectId}/` : ""}assets/${id}`;

  async function saveLabel() {
    if (!editAsset) return;
    setBusy(true); setError(""); setReferenceLinks([]);
    try {
      const changes: Record<string, string> = {};
      if (isInputAsset(editAsset) && editLabel.trim() !== getAssetSetName(editAsset)) changes.asset_set = editLabel.trim();
      if (editDescription !== String(metadata(editAsset).description || "")) changes.description = editDescription;
      if (!Object.keys(changes).length) { setEditAsset(null); return; }
      const response = await fetch(assetUrl(editAsset.id), { method: "PATCH", credentials: "include",
        headers: { "Content-Type": "application/json" }, body: JSON.stringify({ metadata_json: changes }) });
      const result = await response.json();
      if (!response.ok) {setReferenceLinks(referenceConflictLinks(projectId,result.details));throw new Error(result.message || "保存失败");}
      setEditAsset(null); setNotice("文件信息已更新。"); refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); }
    finally { setBusy(false); }
  }
  async function removeFiles() {
    setBusy(true); setError(""); setNotice(""); setReferenceLinks([]);
    const links:Array<{label:string;href:string}>=[];
    const failed: ProjectAsset[] = [], messages: string[] = [], retained: string[] = [];
    for (const asset of confirmation) {
      try {
        const response = await fetch(assetUrl(asset.id), { method: "DELETE", credentials: "include" });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {links.push(...referenceConflictLinks(projectId,payload.details));throw new Error(payload.message || "删除失败");}
        if (payload.storage_retained) retained.push(fileName(asset));
      } catch (reason) { failed.push(asset); messages.push(`${fileName(asset)}：${reason instanceof Error ? reason.message : "删除失败"}`); }
    }
    setNotice(`已删除 ${confirmation.length - failed.length} 个文件${failed.length ? `，${failed.length} 个未删除` : ""}。${retained.length ? `共享或外部文件已保留，仅移除登记：${retained.join("、")}。` : ""}`);
    setSelected(previous=>{const next=new Set(previous);for(const asset of confirmation)if(!failed.some(item=>item.id===asset.id))next.delete(asset.id);for(const asset of failed)next.add(asset.id);return next;}); setConfirmation(failed);
    setError(messages.join("；")); setReferenceLinks(links.filter((link,index)=>links.findIndex(item=>item.href===link.href)===index)); setBusy(false); refresh();
  }
  async function downloadSelection() {
    if (!selectedAssets.length) return;
    if (!projectId) { setError("请在项目中进行批量下载。"); return; }
    setBusy(true); setError("");
    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ""}/api/projects/${projectId}/assets/download`, {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ asset_ids: selectedAssets.map(asset => asset.id) }) });
      if (!response.ok) { const result = await response.json().catch(() => ({})); throw new Error(result.message || "打包下载失败"); }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a"); link.href = url; link.download = "项目文件.zip"; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "下载失败"); }
    finally { setBusy(false); }
  }
  async function retryValidation(asset: ProjectAsset) {
    if (!projectId) return;
    setBusy(true); setError("");
    try { await apiClient.post(`/api/projects/${projectId}/assets/${asset.id}/validate`); refresh(); closeView(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "重新校验失败"); }
    finally { setBusy(false); }
  }

  return <div className="data-file-panel">
    {!onDraftChange && <UnsavedChangesGuard when={editPending} />}
    {showGroup && showDatasetFilter && groups.length > 0 && <div className="data-file-toolbar"><span>数据集</span><Select value={groupFilter}
      ariaLabel="文件数据集筛选" options={[{ value: "", label: "全部数据集" }, ...groups.map(name => ({ value: name, label: name }))]} onChange={setGroupFilter} /></div>}
    {selectedAssets.length > 0 && <div className="data-selection-bar"><strong>已选择 {selectedAssets.length} 个{selection ? "文件" : "当前列表文件"}</strong>
      {selection && <><span className="data-muted">{offPageCount ? `${offPageCount} 个在其他页面` : "所选文件均在本页"}</span>
        <button className="btn btn-secondary" disabled={busy} onClick={()=>setSelectionOpen(true)}>查看所选清单</button></>}
      <button className="btn btn-secondary" disabled={busy} onClick={() => setSelected(new Set())}><X size={14} />取消选择</button>
      <button className="btn btn-secondary" disabled={busy} onClick={downloadSelection}><Download size={14} />打包下载</button>
      <button className="btn btn-danger" disabled={busy} onClick={() => { setError(""); setConfirmation(selectedAssets); }}><Trash2 size={14} />删除所选</button></div>}
    {atLimit && <p className="data-notice" role="status">已选择上限 {FILE_SELECTION_LIMIT} 个文件，请先移除部分选择再添加。</p>}
    {notice && <p className="data-notice" role="status">{notice}</p>}
    {error && !editAsset && !confirmation.length && <p className="data-error" role="alert">{error}</p>}
    {mobile ? <AssetMobileList assets={filtered} selected={selected} allSelected={allSelected} loading={loading} busy={busy}
      selectionLimit={selection ? FILE_SELECTION_LIMIT : undefined} showSelect={showSelect} showGroup={showGroup} showStatus={showStatus} emptyLabel={emptyLabel} name={fileName} formatSize={formatSize}
      onToggleAll={toggleAll}
      onToggle={id=>setSelected(previous=>{const next=new Set(previous);next.has(id)?next.delete(id):next.add(id);return next;})}
      onView={openView} onActions={setActionAsset}/> : (<div className="data-table-scroll"><table className="data-file-table" style={{"--data-name-offset": showSelect ? "44px" : "0px"} as React.CSSProperties}><thead><tr>
      {showSelect && <th scope="col" className="data-check-cell"><input type="checkbox" aria-label="选择当前列表全部文件" checked={allSelected} ref={node=>{if(node)node.indeterminate=!allSelected && filtered.some(asset=>selected.has(asset.id));}}
        disabled={busy || !filtered.length || (atLimit && !allSelected)} onChange={toggleAll} /></th>}
      <th scope="col" className="data-name-heading">名称</th>{showGroup && <th scope="col">数据集</th>}<th scope="col">输入类型</th>{(hasValidation || showStatus) && <th scope="col">状态</th>}<th scope="col">大小</th><th scope="col">上传时间</th><th scope="col">操作</th>
    </tr></thead><tbody>
      {loading ? <tr><td colSpan={9} role="status">正在读取文件…</td></tr> : !filtered.length ? <tr><td colSpan={9} className="data-table-empty">{emptyLabel}</td></tr>
        : filtered.map(asset => { const info = metadata(asset), validation = info.validation || {}, input = isInputAsset(asset);
          const status = validation.status || "unknown";
          return <tr key={asset.id} className={selected.has(asset.id) ? "is-selected" : ""}>
            {showSelect && <td className="data-check-cell"><input type="checkbox" aria-label={`选择 ${fileName(asset)}`} checked={selected.has(asset.id)} disabled={busy || (atLimit && !selected.has(asset.id))}
              onChange={() => setSelected(previous => { const next = new Set(previous); next.has(asset.id) ? next.delete(asset.id) : next.add(asset.id); return next; })} /></td>}
            <td className="data-file-name"><button onClick={() => openView(asset)} title={fileName(asset)}>{fileName(asset)}</button>
              {info.description && <small className="data-file-description" title={String(info.description)}>{String(info.description).slice(0,100)}{String(info.description).length>100?"…":""}</small>}
              {info.superseded && <small>历史版本</small>}</td>
            {showGroup && <td><span className="data-dataset-tag">{getAssetSetLabel(asset)}</span></td>}
            <td>{assetTypeLabels[asset.asset_type] || "其他文件"}</td>
            {(hasValidation || showStatus) && <td>{input ? <span className={`data-validation state-${status}`}>{validationLabels[status] || "尚未校验"}</span>
              : <StatusBadge status={String(info.status || info.job_status || "completed")} />}</td>}
            <td>{formatSize(asset.size)}</td><td>{asset.uploaded_at ? new Date(asset.uploaded_at).toLocaleString("zh-CN", { hour12: false }) : "未记录"}</td>
            <td><div className="data-row-actions"><button aria-label={`查看 ${fileName(asset)}`} title="查看文件与校验" onClick={() => openView(asset)}><FileSearch size={15} /></button>
              <a href={downloadHref(asset)} aria-label={`下载 ${fileName(asset)}`} title="下载"><Download size={15} /></a>
              <button aria-label={`更多操作：${fileName(asset)}`} title="修改信息或删除文件" disabled={busy} onClick={() => {setError("");setActionAsset(asset);}}><MoreHorizontal size={17} /></button></div></td>
          </tr>; })}
    </tbody></table></div>)}
    <Sheet open={selectionOpen} onClose={()=>setSelectionOpen(false)} title={`已选择 ${selectedAssets.length} 个文件`}>
      <p className="data-muted">选择仅包括这里列出的文件；翻页保留选择，切换项目、数据集或筛选会清空。</p>
      <ul className="data-selected-files">{selectedAssets.map(asset=><li key={asset.id}><div><strong>{fileName(asset)}</strong><small>{getAssetSetLabel(asset)} · {assetTypeLabels[asset.asset_type] || "项目文件"} · {metadata(asset).superseded ? "历史版本" : "当前版本"}{metadata(asset).content_version ? ` · ${String(metadata(asset).content_version)}` : ""}</small></div>
        <button className="btn btn-secondary" disabled={busy} aria-label={`从选择清单移除 ${fileName(asset)}`} onClick={()=>setSelected(previous=>{const next=new Set(previous);next.delete(asset.id);return next;})}>移除</button></li>)}</ul>
      {!selectedAssets.length && <p>已清空选择，可关闭后继续选择文件。</p>}
      <button className="btn btn-secondary" onClick={()=>setSelectionOpen(false)}>返回文件列表</button>
    </Sheet>
    <Sheet open={!!actionAsset} onClose={()=>setActionAsset(null)} title="文件操作">
      {actionAsset && <><p className="data-action-file-name">{fileName(actionAsset)}</p><dl className="data-file-facts"><dt>数据集</dt><dd>{getAssetSetLabel(actionAsset)}</dd><dt>文件版本</dt><dd>{String(metadata(actionAsset).content_version || "未记录")}{metadata(actionAsset).superseded ? " · 历史版本" : ""}</dd><dt>上传时间</dt><dd>{actionAsset.uploaded_at ? new Date(actionAsset.uploaded_at).toLocaleString("zh-CN",{hour12:false}) : "未记录"}</dd></dl><div className="data-mobile-action-buttons">
        <button className="btn btn-secondary" onClick={()=>{openView(actionAsset);setActionAsset(null);}}>查看文件与校验</button>
        <a className="btn btn-secondary" href={downloadHref(actionAsset)}>下载原文件</a>
        {(isInputAsset(actionAsset) || actionAsset.asset_type === "project_file") && <button className="btn btn-secondary" aria-label={mobile ? undefined : isInputAsset(actionAsset) ? `修改 ${fileName(actionAsset)} 的数据集归属` : `修改 ${fileName(actionAsset)} 的文件说明`} disabled={busy} onClick={()=>{
          setError("");setEditAsset(actionAsset);setEditLabel(getAssetSetName(actionAsset));setEditDescription(String(metadata(actionAsset).description || ""));setActionAsset(null);
        }}><Pencil size={15}/>修改文件信息</button>}
        <button className="btn btn-danger" aria-label={mobile ? undefined : `删除 ${fileName(actionAsset)}`} disabled={busy} onClick={()=>{setError("");setConfirmation([actionAsset]);setActionAsset(null);}}><Trash2 size={15}/>删除文件</button>
      </div></>}
    </Sheet>
    <Sheet open={!!editAsset} onClose={closeEdit} title="修改文件信息">
      <p>{editAsset && fileName(editAsset)}；已有任务引用的文件会保留原归属。</p>
      {editAsset && isInputAsset(editAsset) && <label className="field-label">数据集名称<input className="input" aria-label="数据集名称" maxLength={120} value={editLabel} onChange={event => setEditLabel(event.target.value)} disabled={busy} /></label>}
      <label className="field-label">文件说明<textarea className="input" aria-label="文件说明" rows={4} maxLength={2000} value={editDescription} onChange={event => setEditDescription(event.target.value)} disabled={busy} placeholder="记录来源、用途或需要注意的信息" /></label>
      {error && <p role="alert" className="data-error">{error}</p>}
      {error && <ReferenceLinks links={referenceLinks}/>}
      <button className="btn btn-primary" disabled={busy || !editLabel.trim()} onClick={saveLabel}><Save size={15} />{busy ? "正在保存…" : "保存"}</button>
    </Sheet>
    <Sheet open={discardEdit} layer={200} onClose={() => setDiscardEdit(false)} title="放弃未保存的文件信息">
      <p>文件信息尚未保存。关闭将放弃这些修改。</p>
      <div className="data-row-actions"><button className="btn btn-primary" onClick={() => setDiscardEdit(false)}>继续编辑</button>
        <button className="btn btn-danger" onClick={() => { setDiscardEdit(false); setEditAsset(null); }}>放弃修改并关闭</button></div>
    </Sheet>
    <Sheet open={confirmation.length > 0} onClose={() => !busy && setConfirmation([])} title={`确认删除 ${confirmation.length} 个文件`}>
      <p>独占文件删除后无法恢复；被任务引用的文件不会删除，共享或外部文件只移除当前登记。</p>
      <ul className="data-delete-files">{confirmation.map(asset => <li key={asset.id}>
        <strong>{fileName(asset)}</strong><div className="data-delete-facts"><span>{getAssetSetLabel(asset)}</span><span>{assetTypeLabels[asset.asset_type] || "项目文件"}</span>
          {metadata(asset).content_version && <span>版本：{String(metadata(asset).content_version)}</span>}
          {asset.uploaded_at && <span>上传：{new Date(asset.uploaded_at).toLocaleString("zh-CN",{hour12:false})}</span>}
          {isInputAsset(asset) && <><span className={metadata(asset).superseded ? "is-historical" : ""}>{metadata(asset).superseded ? "历史版本" : "当前版本"}</span><span>{validationLabels[metadata(asset).validation?.status || "unknown"] || "尚未校验"}</span></>}</div>
        <small>版本：{String(metadata(asset).content_version || "未记录")} · 文件标识：{asset.id}</small>
      </li>)}</ul>
      {error && <p role="alert" className="data-error">{error}</p>}
      {error && <ReferenceLinks links={referenceLinks}/>}
      <div className="data-row-actions"><button className="btn btn-secondary" disabled={busy} onClick={() => setConfirmation([])}>取消</button>
        <button className="btn btn-danger" disabled={busy} onClick={removeFiles}>{busy ? "正在删除…" : error ? "重试未删除项" : "确认删除"}</button></div>
    </Sheet>
    <Sheet open={!!viewAsset || !!focusedAssetId} onClose={closeView} title="文件详情与校验">
      {focusedAssetId && !viewAsset && focused.status !== "error" && <p role="status">正在读取指定文件版本…</p>}
      {focusedAssetId && focused.status === "error" && <div><p className="data-error" role="alert">文件详情暂时无法读取；请重试，或返回文件列表确认当前文件。</p>
        <div className="data-row-actions"><button className="btn btn-primary" onClick={focused.refetch}>重新读取文件</button><button className="btn btn-secondary" onClick={closeView}>返回文件列表</button></div></div>}
      {scopeMismatch && viewAsset && <div className="data-scope-mismatch" role="status"><h4>此文件属于其他数据集</h4><p>当前范围为「{assetSet}」，指定文件属于「{getAssetSetName(viewAsset)}」。</p><a className="btn btn-primary" href={projectAssetDetailPath(projectId!,viewAsset.id,getAssetSetName(viewAsset))}>切换到所属数据集查看</a></div>}
      {viewAsset && !scopeMismatch && <><h4>{fileName(viewAsset)}</h4>{metadata(viewAsset).superseded && <p className="data-muted" role="status">这是保留的历史版本；新分析请明确确认使用版本。</p>}<dl className="data-file-facts"><dt>输入类型</dt><dd>{assetTypeLabels[viewAsset.asset_type] || "项目文件"}</dd>
        <dt>数据集</dt><dd>{getAssetSetLabel(viewAsset)}</dd><dt>版本标识</dt><dd>{metadata(viewAsset).content_version || "未记录"}</dd>
        <dt>文件说明</dt><dd>{metadata(viewAsset).description || "未填写"}</dd></dl><details className="data-storage-details"><summary>存储位置</summary><code>{viewAsset.storage_path}</code></details>
        {isInputAsset(viewAsset) && <><p className={`data-validation state-${metadata(viewAsset).validation?.status || "unknown"}`}>
          {validationLabels[metadata(viewAsset).validation?.status || "unknown"]}</p>
          {(metadata(viewAsset).validation?.summary?.errors || []).map((message: string) => <p key={message} className="data-error">{message}</p>)}
          {metadata(viewAsset).validation?.message && <p>{metadata(viewAsset).validation.message}</p>}
          <AssetInputPreview key={viewAsset.id} asset={viewAsset} projectId={projectId} />
          <p className="data-muted">预览只展示部分内容；样本对应和列映射在分析配置中确认。</p>
          <InputValidationGuidance status={metadata(viewAsset).validation?.status || "unknown"}/>
          {projectId && <div className="data-row-actions data-input-guidance-actions"><button className="btn btn-secondary" disabled={busy || metadata(viewAsset).validation?.status === "pending"} onClick={() => retryValidation(viewAsset)}>重新校验</button>
            <a className="btn btn-primary" href={`/analysis/center?${new URLSearchParams({project:projectId,asset_set:getAssetSetName(viewAsset),input_asset:viewAsset.id,return_to:window.location.pathname.startsWith("/management/projects/")?window.location.pathname+window.location.search:`/management/projects/${projectId}?tab=assets&asset_set=${encodeURIComponent(getAssetSetName(viewAsset))}&asset=${encodeURIComponent(viewAsset.id)}`})}`}>{inputValidationAction(metadata(viewAsset).validation?.status || "unknown")}</a></div>}</>}
        {!isInputAsset(viewAsset) && <a className="btn btn-secondary" href={String((viewAsset as ProjectAsset & { preview_url?: string }).preview_url || assetPreviewUrl(viewAsset.id))} target="_blank" rel="noreferrer">打开预览</a>}
        <a className="btn btn-secondary" href={downloadHref(viewAsset)}>下载原文件</a>
        {projectId && viewAsset.asset_type.includes("processed_result") && <AssetResultProvenance key={viewAsset.id} asset={viewAsset} projectId={projectId}/>}
        {projectId && metadata(viewAsset).source!=="mongodb" && <AssetLineage key={viewAsset.id} projectId={projectId} assetId={viewAsset.id}/>}</>}
    </Sheet>
  </div>;
}

function referenceConflictLinks(projectId:string|undefined,details:unknown){
 if(!projectId || !details || typeof details!=="object")return [];
 const value=details as Record<string,unknown>,links:Array<{label:string;href:string}>=[];
 if(typeof value.job_id==="string")links.push({label:"查看引用任务 "+value.job_id,href:"/analysis/script-hub/jobs?"+new URLSearchParams({project:projectId,job:value.job_id})});
 if(Array.isArray(value.group_spec_ids))for(const id of value.group_spec_ids)if(typeof id==="string")links.push({label:"定位引用分组方案",href:`/management/projects/${encodeURIComponent(projectId)}?`+new URLSearchParams({tab:"group-specs",group_spec:id})});
 return links;
}
function ReferenceLinks({links}:{links:Array<{label:string;href:string}>}){
 return links.length ? <div className="data-row-actions">{links.map(link=><a key={link.href} className="btn btn-secondary" href={link.href} target="_blank" rel="noreferrer">{link.label} ↗</a>)}</div> : null;
}
