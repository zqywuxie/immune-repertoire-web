import {ProjectDatasetDetails} from "./ProjectDatasetDetails";
import { useAssetSelection } from "./useAssetSelection";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Plus, Upload, ArrowRight } from "lucide-react";
import { useApi } from "../../shared/hooks/useApi";
import { usePageActivity } from "../../shared/hooks/usePageActivity";
import { useMediaQuery } from "../../shared/hooks/useMediaQuery";
import { apiClient } from "../../shared/api/client";
import { listProjectAssets, listProjectDatasets } from "../../shared/api/projects";
import { Select } from "../../shared/components/Select";
import { Sheet } from "../../shared/components/Sheet";
import { Pagination } from "../../shared/components/Pagination";
import { AssetTable, assetTypeLabels } from "./AssetTable";
import { AssetUpload } from "./AssetUpload";
import { InputValidationStatus } from "./InputValidationStatus";
import { InputFileFilters } from "./InputFileFilters";
import { AnalysisPreparation } from "./AnalysisPreparation";
import { DataReadError } from "./DataReadError";
import "./DataManagement.css";

const kinds = [
  { type: "pep", aliases: ["pep"], title: "克隆序列表" },
  { type: "profile", aliases: ["profile", "datapoint"], title: "样本指标表" },
  { type: "transcriptome", aliases: ["transcriptome"], title: "转录组" },
  { type: "deconvolution", aliases: ["deconvolution", "cibersort"], title: "免疫细胞浸润" },
];
export function ProjectDatasetManager({ projectId, revision, active = true, onChange, onDraftChange, onUploadBusyChange, onFileDraftChange }: { projectId: string; revision: number; active?: boolean; onChange: () => void; onDraftChange?: (count: number) => void; onUploadBusyChange?: (busy: boolean) => void; onFileDraftChange?: (dirty: boolean) => void }) {
  const [query, setQuery] = useSearchParams();
  const fileFilters = useRef<HTMLDivElement>(null);
  const pageActive = usePageActivity(active);
  const lastValidation = useRef<{scope:string; states:string} | null>(null);
  const mobile = useMediaQuery("(max-width: 768px)");
  const [importOpen, setImportOpen] = useState(query.get("import") === "1");
  const [importSet, setImportSet] = useState(query.get("import") === "1" ? query.get("asset_set") || "" : "");
  const [importType, setImportType] = useState(query.get("import") === "1" ? query.get("file_type") || "" : "");
  const explicitImport = useRef(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [draftCount, setDraftCount] = useState(0);
  const [draftRevision, setDraftRevision] = useState(0);
  const [importStarted, setImportStarted] = useState(query.get("import") === "1");
  const [uploadSets, setUploadSets] = useState<string[]>([]);
  useEffect(() => { onDraftChange?.(draftCount); }, [draftCount, onDraftChange]);
  useEffect(() => { onUploadBusyChange?.(uploadBusy); }, [uploadBusy, onUploadBusyChange]);
  const [discardOpen, setDiscardOpen] = useState(false);
  const [fileDirty,setFileDirty]=useState(false),[datasetDirty,setDatasetDirty]=useState(false);
  useEffect(()=>{onFileDraftChange?.(fileDirty || datasetDirty);return ()=>onFileDraftChange?.(false);},[fileDirty,datasetDirty,onFileDraftChange]);
  const page = Math.max(1, Number(query.get("file_page")) || 1);
  const search = query.get("file_q") || "";
  const [searchDraft, setSearchDraft] = useState(search);
  useEffect(() => setSearchDraft(search), [search]);
  useEffect(() => {
    if (searchDraft.trim() === search) return;
    const timer = setTimeout(() => setQuery(previous => { const next = new URLSearchParams(previous);
      searchDraft.trim() ? next.set("file_q", searchDraft.trim()) : next.delete("file_q"); next.delete("file_page"); return next; }, { replace: true }), 300);
    return () => clearTimeout(timer);
  }, [searchDraft, search, setQuery]);
  const type = query.get("file_type") || "";
  const status = query.get("file_status") || "";
  const history = query.get("history") === "1";
  const sort = query.get("file_sort") || "uploaded_desc";
  const allInputs = useApi(() => listProjectDatasets(projectId, {skipCache:true}), [projectId, revision], pageActive && !importOpen);
  const sets = allInputs.status === "ready" ? allInputs.data.datasets : [];
  const activeSets=sets.filter(set=>!set.archived);
  const showArchived=query.get("archived_datasets")==="1";
  const selectedName = query.has("asset_set") ? query.get("asset_set") || "" : (activeSets.length === 1 ? activeSets[0].name : "");
  const visibleSets=sets.filter(set=>!set.archived || showArchived || set.name===selectedName);
  const selected = sets.find(set => set.name === selectedName);
  const preparationOpen = query.has("prepare_open") ? query.get("prepare_open") === "1" : Boolean(query.get("prepare_tool"));
  const selection = useAssetSelection(JSON.stringify([projectId,selectedName,type,search,status,history]));
  const fileRequest = JSON.stringify([projectId,revision,selectedName,type,search,status,history,sort,page]);
  const files = useApi(async () => ({...await listProjectAssets(projectId, { inputsOnly: true, assetSet: selectedName, assetType: type,
    search, validationStatus: status, includeSuperseded: history, sort, page, pageSize: 50, skipCache:true }), request:fileRequest}), [projectId, revision, selectedName, type, search, status, history, sort, page], pageActive);
  const filePageReady = files.status === "ready" && files.data.request === fileRequest;
  useEffect(() => {
    if(files.status!=="ready" || files.data.request!==fileRequest || !files.data.pagination || files.data.pagination.page!==page)return;
    const last=Math.max(1,files.data.pagination.total_pages);
    if(page>last)setQuery(previous=>{const next=new URLSearchParams(previous);last>1?next.set("file_page",String(last)):next.delete("file_page");return next;},{replace:true});
  },[files.status,files.status==="ready"?files.data.pagination:null,page,setQuery]);
  function update(key: string, value: string) {
    setQuery(previous => { const next = new URLSearchParams(previous); value || key === "asset_set" ? next.set(key, value) : next.delete(key); next.delete("file_page"); if (key === "asset_set") for (const field of ["sample_page", "asset", "group_spec", "group_page"]) next.delete(field); return next; });
  }
  function showFiles(kind = "", attention = false) {
    setSearchDraft("");
    setQuery(previous => {
      const next = new URLSearchParams(previous);
      kind ? next.set("file_type", kind) : next.delete("file_type");
      attention ? next.set("file_status", "needs_attention") : next.delete("file_status");
      for (const key of ["file_q", "file_page", "history", "asset"]) next.delete(key);
      return next;
    });
    fileFilters.current?.scrollIntoView({block:"start"});
    fileFilters.current?.focus({preventScroll:true});
  }
  function openImport(existing: boolean, kind = "") {
    explicitImport.current = true;
    if (!draftCount) { setImportSet(existing ? selectedName : ""); setImportType(kind); setDraftRevision(value => value + 1); }
    setImportStarted(true);
    setQuery(previous => { const next = new URLSearchParams(previous); next.set("import", "1"); return next; });
  }
  function closeImport() {
    if (uploadBusy) return;
    setQuery(previous => { const next = new URLSearchParams(previous); next.delete("import"); return next; }, { replace: true });
  }
  useEffect(() => {
    const requested = query.get("import") === "1";
    if (requested) {
      setImportStarted(true);
      if (!importOpen && !draftCount && !uploadBusy && !explicitImport.current) {
        setImportSet(query.get("asset_set") || "");
        setImportType(query.get("file_type") || "");
        setDraftRevision(value => value + 1);
      }
    }
    explicitImport.current = false;
    if (!requested && uploadBusy) {
      setQuery(previous => { const next = new URLSearchParams(previous); next.set("import", "1"); return next; }, { replace: true });
      return;
    }
    setImportOpen(requested);
  }, [query.get("import"), query.get("asset_set"), query.get("file_type"), importOpen, draftCount, uploadBusy, setQuery]);
  const scopeSets = selected ? [selected] : selectedName ? [] : sets;
  const inputCount = scopeSets.reduce((total, set) => total + set.input_count, 0);
  const attentionCount = scopeSets.reduce((total, set) => total + Object.values(set.kinds).reduce((sum, kind) => sum + (kind.statuses.failed || 0) + (kind.statuses.invalid || 0) + (kind.statuses.needs_mapping || 0) + (kind.statuses.unknown || 0), 0), 0);
  const pendingCount = scopeSets.reduce((total, set) => total + Object.values(set.kinds).reduce((sum, kind) => sum + (kind.statuses.pending || 0), 0), 0);
  const validationStates = JSON.stringify(scopeSets.map(set => [set.name, set.input_count, set.kinds]));
  useEffect(() => {
    if (!pageActive || importOpen || allInputs.status !== "ready") return;
    const scope = JSON.stringify([projectId, selectedName]);
    const previous = lastValidation.current;
    lastValidation.current = {scope, states:validationStates};
    // Include the final pending -> terminal transition before stopping refresh.
    if (previous?.scope === scope && previous.states !== validationStates) files.refetch();
  }, [projectId, selectedName, validationStates, pageActive, importOpen, allInputs.status, files.refetch]);
  useEffect(() => {
    if (!pageActive || importOpen || !pendingCount || allInputs.status !== "ready") return;
    const timer = setInterval(allInputs.refetch, 5000);
    return () => clearInterval(timer);
  }, [pageActive, importOpen, pendingCount, allInputs.status, allInputs.refetch]);

  const inputOverview = <>
    <div className="data-input-grid">{kinds.map(kind => {
      const stats = (selected ? [selected] : selectedName ? [] : sets).map(set => set.kinds[kind.type]).filter(Boolean);
      const count = stats.reduce((total, item) => total + item.count, 0);
      const invalid = stats.reduce((total, item) => total + (item.statuses.invalid || 0) + (item.statuses.failed || 0), 0);
      const pending = stats.reduce((total, item) => total + (item.statuses.pending || 0), 0);
      const mapping = stats.reduce((total, item) => total + (item.statuses.needs_mapping || 0), 0);
      const unknown = stats.reduce((total, item) => total + (item.statuses.unknown || 0), 0);
      const valid = stats.reduce((total, item) => total + (item.statuses.valid || 0), 0);
      return <article className="data-input-tile" key={kind.type}><h4>{kind.title}</h4><strong>{allInputs.status !== "ready" ? "—" : count}<span className="data-muted"> 个文件</span></strong>
        <p>{allInputs.status !== "ready" ? "正在读取输入概况…" : !count ? "按分析需要添加" : `${valid} 个通过${pending ? ` · ${pending} 个等待` : ""}${invalid ? ` · ${invalid} 个需处理` : ""}${mapping ? ` · ${mapping} 个待映射` : ""}${unknown ? ` · ${unknown} 个尚未校验` : ""}`}</p>
        <div className="data-row-actions"><button className="btn btn-secondary" disabled={allInputs.status !== "ready"} onClick={() => count ? showFiles(kind.type) : openImport(true, kind.type)}>{count ? "查看文件" : "添加输入"}</button>
          {(invalid + mapping + unknown) > 0 && <button className="data-attention-button" onClick={() => showFiles(kind.type, true)}>处理 {invalid + mapping + unknown} 项</button>}</div></article>;
    })}</div>
    <p className="data-muted">四类输入按需提供。列映射、样本对应和具体可运行模块在分析配置中检查；存在多个版本时须明确选择。</p>
  </>;

  return <section className="data-section">
    <div className="data-section-header"><div><h3>项目数据集</h3>{!mobile && <p>按分析需要准备输入，保存与校验分别确认。</p>}</div>
      <div className="data-row-actions"><button className="btn btn-secondary" onClick={() => openImport(false)}><Plus size={16} />创建并导入数据集</button>
        <button className="btn btn-primary" onClick={() => openImport(true)}><Upload size={16} />导入文件</button></div></div>
    {!importOpen && draftCount > 0 && <div className="data-draft-warning" role="status"><p>已保留 {draftCount} 项未保存选择，可继续上传。</p>
      <div className="data-row-actions"><button className="btn btn-primary" onClick={() => openImport(true)}>继续编辑上传</button>
        <button className="btn btn-secondary" onClick={() => setDiscardOpen(true)}>放弃上传草稿</button></div></div>}
    {allInputs.status === "error" && <DataReadError title="数据集概况暂时无法读取" message={allInputs.error} onRetry={allInputs.refetch} retryLabel="重新读取数据集" />}
    <div className="data-query-bar data-dataset-context"><label>当前数据集</label><Select value={selectedName} ariaLabel="当前项目数据集"
      disabled={allInputs.status !== "ready"}
      options={[...(selectedName && !selected ? [{value:selectedName,label:selectedName}] : []), { value: "", label: "全部数据集" }, ...visibleSets.map(set => ({ value: set.name, label: `${set.display_name || set.name}${set.archived ? " · 已归档" : ""} · ${set.input_count} 个输入文件` }))]}
      onChange={value => update("asset_set", value)} />
      {sets.some(set=>set.archived) && <label className="data-dataset-archive-filter"><input type="checkbox" checked={showArchived} onChange={event=>{const checked=event.currentTarget.checked;setQuery(previous=>{const next=new URLSearchParams(previous);checked?next.set("archived_datasets","1"):next.delete("archived_datasets");return next;});}}/>显示已归档数据集</label>}
      {selected && !selected.archived && !query.get("prepare_tool") && <a className="btn btn-secondary" href={`/analysis/center?project=${encodeURIComponent(projectId)}&asset_set=${encodeURIComponent(selectedName)}`}>使用此数据集分析<ArrowRight size={15} /></a>}</div>
    {selectedName && allInputs.status === "ready" && !selected && <p className="data-error" role="alert">当前数据集不存在或已移除。<button className="btn btn-secondary" onClick={() => update("asset_set", "")}>查看全部数据集</button></p>}
    {selected && <ProjectDatasetDetails key={`${projectId}:${selected.name}`} projectId={projectId} dataset={selected} onDirty={setDatasetDirty} onChange={()=>{allInputs.refetch();onChange();}}/>}
    {!selectedName && visibleSets.length > 1 && <details className="data-coverage-matrix"><summary>各数据集输入覆盖 · {visibleSets.length} 个数据集</summary>
      <p className="data-muted">未提供的输入是否需要补充，由所选分析决定。</p><div className="data-table-scroll"><table className="data-file-table"><thead><tr><th>数据集</th>{kinds.map(kind => <th key={kind.type}>{kind.title}</th>)}</tr></thead>
        <tbody>{visibleSets.map(set => <tr key={set.name}><th scope="row">{set.display_name || set.name}{set.archived ? "（已归档）" : ""}</th>{kinds.map(kind => { const item=set.kinds[kind.type];const states=item?.statuses || {};const attention=(states.failed || 0)+(states.invalid || 0)+(states.needs_mapping || 0)+(states.unknown || 0);
          const label=!item?.count ? "未提供" : attention ? `${attention} 项需处理` : states.pending ? `${states.pending} 项等待校验` : `${states.valid || 0} 项通过`;
          return <td key={kind.type}><button className={`data-coverage-cell${attention ? " needs-attention" : ""}`} aria-label={`查看 ${set.name} 的${kind.title}：${label}`} onClick={() => setQuery(previous => {const next=new URLSearchParams(previous);next.set("asset_set",set.name);for(const field of ["sample_page","asset","group_spec","group_page"])next.delete(field);next.set("file_type",kind.type);attention ? next.set("file_status","needs_attention") : next.delete("file_status");next.delete("file_q");next.delete("file_page");return next;})}>{label}</button></td>;
        })}</tr>)}</tbody></table></div></details>}
    {allInputs.status === "ready" && selected && <details className="data-preparation-disclosure" open={preparationOpen}
      onToggle={event=>{if(event.currentTarget.open!==preparationOpen){const opened=event.currentTarget.open;setQuery(previous=>{const next=new URLSearchParams(previous);next.set("prepare_open",opened?"1":"0");return next;});}}}>
      <summary>按分析目标准备数据<span>{preparationOpen ? "收起准备步骤" : "查看所需输入与前置结果"}</span></summary>
      <AnalysisPreparation active={pageActive && preparationOpen} projectId={projectId} dataset={selected} revision={revision}
        onImport={kind=>openImport(true,kind)} onFiles={showFiles}/></details>}
    {allInputs.status !== "error" && (mobile ? <div className="data-mobile-input-overview"><details className="data-input-summary"><summary>输入概况 · {allInputs.status !== "ready" ? "读取中" : `${inputCount} 个文件`}{pendingCount > 0 ? ` · ${pendingCount} 项等待校验` : ""}</summary>{inputOverview}</details>
      {attentionCount > 0 && <button className="data-attention-button" onClick={() => showFiles("", true)}>处理 {attentionCount} 项输入问题</button>}</div> : inputOverview)}
    <div ref={fileFilters} tabIndex={-1} aria-label="输入文件筛选"><InputFileFilters mobile={mobile} search={search} searchDraft={searchDraft} type={type} status={status} history={history} sort={sort}
      types={kinds.map(kind => ({ value:kind.type,label:assetTypeLabels[kind.type] }))} onSearchChange={setSearchDraft} onSearchSubmit={() => update("file_q",searchDraft.trim())}
      onApply={filters => setQuery(previous => {const next=new URLSearchParams(previous);for(const [key,value] of [["file_type",filters.type],["file_status",filters.status],["history",filters.history?"1":""],["file_sort",filters.sort==="uploaded_desc"?"":filters.sort]])value?next.set(key,value):next.delete(key);next.delete("file_page");return next;})}
      onClear={() => {setSearchDraft("");setQuery(previous => {const next=new URLSearchParams(previous);for(const key of ["file_q","file_type","file_status","history","file_sort","file_page"])next.delete(key);return next;});}}/></div>
    {files.status === "ready" && filePageReady && <p className="data-muted" role="status">当前筛选共 {files.data.pagination?.total ?? files.data.assets.length} 个文件；每页显示最多 50 个。</p>}
    {files.status === "error" && <DataReadError title="输入文件暂时无法读取" message={files.error} onRetry={files.refetch} retryLabel="重新读取文件" />}
    {(files.status !== "error" || selection.items.length>0) && <AssetTable key={`${projectId}:${selectedName}:${type}:${search}:${status}:${history}`} projectId={projectId} assetSet={selectedName} assets={files.status === "ready" && filePageReady ? files.data.assets : []}
          selection={selection} active={pageActive} focusedAssetId={query.get("asset") || ""}
          onViewAsset={id => setQuery(previous => {const next=new URLSearchParams(previous);next.set("asset", id);return next;})}
          onCloseDetail={() => setQuery(previous => {const next=new URLSearchParams(previous);next.delete("asset");return next;}, {replace:true})}
          loading={files.status === "loading" || files.status === "idle" || (files.status === "ready" && !filePageReady)} onDraftChange={setFileDirty} onAssetDeleted={onChange} showGroup showDatasetFilter={false} emptyLabel={files.status === "error" ? "文件列表暂时无法读取，所选文件仍保留。" : allInputs.status !== "ready" || sets.length || !!(selectedName || type || search || status || history) ? "当前筛选下没有文件，请调整筛选。" : "尚未导入分析输入，点击“导入文件”开始。"} />}
    {files.status === "ready" && filePageReady && <Pagination pagination={files.data.pagination} onPageChange={value => setQuery(previous => { const next = new URLSearchParams(previous); next.set("file_page", String(value)); return next; })} />}
    <Sheet open={importOpen} keepMounted={importStarted} onClose={closeImport} title={uploadSets.length === 1 ? `导入数据：${uploadSets[0]}` : "导入分析数据"}>
      <AssetUpload key={`${projectId}:${draftRevision}`} projectId={projectId} initialAssetSet={importSet} initialAssetType={importType} onBusyChange={setUploadBusy} onPendingChange={setDraftCount} onScopeChange={setUploadSets} onSuccess={() => { apiClient.invalidateCache(); onChange(); }} />
      {importOpen && uploadSets.map(name => <InputValidationStatus key={name} projectId={projectId} revision={revision} assetSet={name} active={pageActive && importOpen} />)}
    </Sheet>
    <Sheet open={discardOpen} onClose={() => setDiscardOpen(false)} title="放弃上传草稿">
      <p>将清除 {draftCount} 项未保存选择；已经保存的文件仍在项目中。</p>
      <div className="data-row-actions"><button className="btn btn-primary" onClick={() => {setDiscardOpen(false);openImport(true);}}>继续编辑</button>
        <button className="btn btn-danger" onClick={() => {setDraftCount(0);setDraftRevision(value => value + 1);setImportStarted(false);setDiscardOpen(false);}}>放弃本次选择</button></div>
    </Sheet>
  </section>;
}
