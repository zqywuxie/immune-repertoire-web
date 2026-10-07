import { GroupSpecCatalog } from "./GroupSpecCatalog";
import { getGroupSpec } from "../../shared/api/groupSpecs";
import { GroupValueEditor } from "./GroupValueEditor";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Pencil, Trash2, Save, X } from "lucide-react";
import { ApiError, apiClient } from "../../shared/api/client";
import type { PaginationInfo } from "../../shared/components/Pagination";
import { getProjectAsset, listProjectAssets } from "../../shared/api/projects";
import type { ProjectAsset } from "../../shared/types/domain";
import { Select } from "../../shared/components/Select";
import { Sheet } from "../../shared/components/Sheet";
import { getAssetSetName } from "../assets/assetSets";
import "../assets/DataManagement.css";

type Group = string | { name?: string; label?: string; [key: string]: unknown };
type Scheme = { id: string; revision?: string; name: string; source?: {available:boolean;reason:string;name:string;asset_set:string}; spec_json: { groups?: Group[]; group_field?: string; source_asset_id?: string; source_content_version?: string; source_sheet?: string | null; [key: string]: unknown } };
type Schema = { columns: string[]; sheets: string[]; selected_sheet: string | null; requires_sheet_selection: boolean };
type Values = { values: string[]; samples_by_value: Record<string, string[]>; sample_counts?: Record<string, number>; row_counts: Record<string, number>; sample_column: string; asset_set: string; content_version: string };
const groupName = (group: Group) => typeof group === "string" ? group : group.name || group.label || "";

type Props = { groupSpecs?: unknown[]; loading: boolean; projectId?: string; managed?: boolean; revision?: number;
  onChanged: () => void; onDraftChange?: (dirty: boolean) => void };
export function ProjectGroupSpecs(props: Props) {
  const [query] = useSearchParams();
  // Navigation is already guarded by the page. Confirmed scope changes discard the old editor.
  return <GroupSpecEditor key={JSON.stringify([props.projectId, query.get("asset_set") || ""])} {...props}/>;
}
function GroupSpecEditor({ groupSpecs, loading, projectId, managed = false, revision = 0, onChanged, onDraftChange }: Props) {
  const [query] = useSearchParams();
  const dataset = query.get("asset_set") || "";
  const focusedSpec = query.get("group_spec") || "";
  useEffect(()=>{if(!loading && focusedSpec)document.getElementById("group-spec-"+focusedSpec)?.scrollIntoView?.({block:"center"});},[focusedSpec,loading,groupSpecs]);
  const [editing, setEditing] = useState<Scheme | null>(null);
  const [copying, setCopying] = useState<Scheme | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editorDismissed,setEditorDismissed] = useState(false);
  const [name, setName] = useState("");
  const [manual, setManual] = useState(false);
  const [manualGroups, setManualGroups] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [field, setField] = useState("");
  const [sheet, setSheet] = useState<string | null>(null);
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [assetStatus, setAssetStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [assetError, setAssetError] = useState("");
  const [assetPage, setAssetPage] = useState(1);
  const [assetSearch, setAssetSearch] = useState("");
  const [assetDraft, setAssetDraft] = useState("");
  const [assetHistory, setAssetHistory] = useState(false);
  const [assetPagination, setAssetPagination] = useState<PaginationInfo>();
  const [pinned, setPinned] = useState<{scope:string;asset:ProjectAsset} | null>(null);
  const [pinnedError, setPinnedError] = useState("");
  const [pinRetry, setPinRetry] = useState(0);
  const sourceScope = JSON.stringify([projectId, dataset]);
  const [schema, setSchema] = useState<Schema | null>(null);
  const [values, setValues] = useState<Values | null>(null);
  const [order, setOrder] = useState<string[]>([]);
  const [reading, setReading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [sourceError, setSourceError] = useState("");
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState<Pick<Scheme, "id" | "name"> | null>(null);
  const [notice, setNotice] = useState("");
  const [conflict,setConflict] = useState(false);
  const [actionScheme,setActionScheme] = useState<Scheme|null>(null);
  const [readingLatest,setReadingLatest] = useState(false);
  const [loadingDetail,setLoadingDetail] = useState(false);
  const [retry, setRetry] = useState(0);
  const blankDraft = JSON.stringify(["", false, "", "", "", null, []]);
  const baseline = useRef(blankDraft);
  const [pendingAction, setPendingAction] = useState<(() => void) | null>(null);
  const draft = JSON.stringify([name, manual, manualGroups, sourceId, field, sheet, order]);
  const source = assets.find(asset => asset.id === sourceId) || (pinned?.scope === sourceScope && pinned.asset.id === sourceId ? pinned.asset : undefined);
  const displayedAssets = source && !assets.some(asset => asset.id === source.id) ? [source, ...assets] : assets;
  const schemes = ((groupSpecs || []) as Scheme[]).filter(scheme => !dataset || !scheme.spec_json?.asset_set || scheme.spec_json.asset_set === dataset);

  const showEditor = editorOpen || !!editing || (!managed && !editorDismissed && !loading && !schemes.length);
  const dirty = showEditor && draft !== baseline.current;
  useLayoutEffect(() => { onDraftChange?.(dirty || saving); }, [dirty, saving, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  function protect(action: () => void) { if (dirty) setPendingAction(() => action); else action(); }
  function protectSelection(action: () => void) {
    const customized = !manual && order.length > 0 && (!values || JSON.stringify(order) !== JSON.stringify(values.values));
    if (customized) setPendingAction(() => action); else action();
  }
  useEffect(() => {
    let active = true;
    if (!projectId || !showEditor) return;
    setAssetStatus("loading"); setAssetError(""); setAssets([]);
    listProjectAssets(projectId, { inputsOnly: true, assetType: "profile", assetSet: dataset, view: "selector",
      includeSuperseded: !!editing || assetHistory, search: assetSearch, page: assetPage, pageSize: 20 }).then(result => { if (active) {
        setAssets(result.assets); setAssetPagination(result.pagination); setAssetStatus("ready");
        if (result.pagination && assetPage > Math.max(1, result.pagination.total_pages)) setAssetPage(Math.max(1, result.pagination.total_pages));
      } })
      .catch(reason => { if (active) {setAssetError(reason instanceof Error ? reason.message : "指标表读取失败");setAssetStatus("error");} });
    return () => { active = false; };
  }, [projectId, dataset, editing?.id, retry, showEditor, assetHistory, assetSearch, assetPage]);

  const sourcePresent = assets.some(asset => asset.id === sourceId);
  useEffect(() => {
    let active = true;
    if (!projectId || !sourceId || !showEditor || manual || assetStatus !== "ready") return;
    const current = assets.find(asset => asset.id === sourceId);
    if (current) { setPinned({scope:sourceScope,asset:current}); setPinnedError(""); return; }
    if (pinned?.scope === sourceScope && pinned.asset.id === sourceId && !pinnedError && !pinRetry) return;
    setPinnedError("");
    getProjectAsset(projectId, sourceId, {view:"selector"}).then(result => {
      if (!active) return;
      const asset = result.asset;
      if (asset.project_id !== projectId || !["profile","datapoint"].includes(asset.asset_type) || (dataset && getAssetSetName(asset) !== dataset)) throw new Error("当前来源不属于所选项目、数据集或指标类型。");
      setPinned({scope:sourceScope,asset});
    }).catch(reason => {if (active) {setPinned(null);setPinnedError(reason instanceof Error ? reason.message : "当前来源读取失败");}});
    return () => {active=false;};
  }, [projectId, dataset, sourceId, sourceScope, showEditor, manual, sourcePresent, assetStatus, pinRetry]);

  useEffect(() => {
    let active = true;
    setSchema(null); setValues(null); setSourceError("");
    if (!projectId || !sourceId || manual) { setReading(false); return; }
    setReading(true);
    apiClient.post<Schema>(`/api/projects/${projectId}/assets/${sourceId}/input-schema`, sheet ? { sheet_name: sheet } : {})
      .then(result => { if (active) setSchema(result); })
      .catch(reason => { if (active) setSourceError(reason instanceof Error ? reason.message : "字段读取失败"); })
      .finally(() => { if (active) setReading(false); });
    return () => { active = false; };
  }, [projectId, sourceId, sheet, manual, retry]);

  useEffect(() => {
    let active = true;
    setValues(null);
    if (!projectId || !sourceId || !field || !schema || schema.requires_sheet_selection || manual) return;
    setReading(true); setSourceError("");
    apiClient.get<Values>(`/api/projects/${projectId}/assets/${sourceId}/group-values`, { field, sheet_name: sheet || undefined, include_samples: false }, { skipCache: true })
      .then(result => {
        if (!active) return;
        setValues(result);
        // A saved order stays explicit; absent old values remain visible as a mismatch.
        setOrder(previous => previous.length ? previous : result.values);
      }).catch(reason => { if (active) setSourceError(reason instanceof Error ? reason.message : "分组取值读取失败"); })
      .finally(() => { if (active) setReading(false); });
    return () => { active = false; };
  }, [projectId, sourceId, field, sheet, schema, manual, retry]);

  function reset() {
    baseline.current = blankDraft;
    setEditorOpen(false); setEditorDismissed(true); setCopying(null);
    setConflict(false); setEditing(null); setName(""); setManual(false); setManualGroups(""); setSourceId("");
    setField(""); setSheet(null); setOrder([]); setError(""); setSourceError("");
    setAssetPage(1); setAssetSearch(""); setAssetDraft(""); setAssetHistory(false); setPinnedError(""); setPinRetry(0);
  }
  function edit(scheme: Scheme) {
    setConflict(false); setCopying(null); setEditorOpen(true);
    const definition = scheme.spec_json || {};
    baseline.current = JSON.stringify([scheme.name, !definition.source_asset_id,
      (definition.groups || []).map(groupName).join("、"), String(definition.source_asset_id || ""),
      String(definition.group_field || ""), definition.source_sheet || null, (definition.groups || []).map(groupName)]);
    setEditing(scheme); setName(scheme.name); setSourceId(String(definition.source_asset_id || ""));
    setField(String(definition.group_field || "")); setSheet(definition.source_sheet || null);
    setOrder((definition.groups || []).map(groupName));
    setManual(!definition.source_asset_id); setManualGroups((definition.groups || []).map(groupName).join("、"));
    setError(""); setNotice("");
  }
  const selected = manual ? manualGroups.split(/[,，、]/).map(value => value.trim()).filter(Boolean) : order;
  const missing = !manual && values ? selected.filter(value => !values.values.includes(value)) : [];
  const invalidOrder = !selected.length || selected.length !== new Set(selected).size || selected.some(value => value.includes(","));
  async function save() {
    if (!projectId || saving || loadingDetail || conflict) return;
    setSaving(true); setError("");
    const original = (editing || copying)?.spec_json || {};
    const groups = selected.map(value => (original.groups || []).find(group => groupName(group) === value) || value);
    const definition = { ...original, groups };
    if (!manual && source && values) Object.assign(definition, { group_field: field, source_asset_id: sourceId,
      source_content_version: values.content_version, source_sheet: sheet, asset_set: values.asset_set });
    try {
      await apiClient.post(`/api/projects/${projectId}/group-specs${managed ? "?view=detail" : ""}`, { ...(editing ? { id: editing.id, expected_revision: editing.revision } : {}), name: name.trim(), spec_json: definition });
      apiClient.invalidateCache(); reset(); setNotice("分组方案已保存；历史任务继续使用提交时的方案快照。"); onChanged();
    } catch (reason) {
      if(reason instanceof ApiError && reason.status===409 && (reason.payload as {error_code?:string})?.error_code==="GROUP_SPEC_CHANGED")setConflict(true);
      setError(reason instanceof Error ? reason.message : "保存失败，编辑内容已保留。");
    }
    finally { setSaving(false); }
  }
  async function readLatest() {
    if(!projectId || !editing || readingLatest)return;
    setReadingLatest(true);setError("");
    try {
      const latest = managed ? await getGroupSpec(projectId, editing.id) as Scheme
        : (await apiClient.get<{group_specs:Scheme[]}>(`/api/projects/${projectId}/group-specs`,undefined,{skipCache:true,deduplicate:false})).group_specs.find(item=>item.id===editing.id);
      if(!latest)throw new Error("此方案已删除；当前草稿仍保留，可另存新方案。");
      protect(()=>edit(latest));
    }catch(reason){setError(reason instanceof Error?reason.message:"最新方案读取失败，草稿已保留。");}
    finally{setReadingLatest(false);}
  }
  function copy(scheme: Scheme) {
    protect(() => {
      reset(); setCopying(scheme); setName(scheme.name + "（新版本）"); setEditorOpen(true);
      if (!scheme.spec_json.source_asset_id) {
        setManual(true); setManualGroups((scheme.spec_json.groups || []).map(groupName).join("、"));
        setOrder((scheme.spec_json.groups || []).map(groupName));
      }
    });
  }
  async function remove() {
    if (!projectId || !confirm || saving) return;
    setSaving(true); setError("");
    try {
      await apiClient.delete(`/api/projects/${projectId}/group-specs/${confirm.id}`);
      if (editing?.id === confirm.id) reset();
      setConfirm(null); apiClient.invalidateCache(); setNotice("分组方案已删除。"); onChanged();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "删除失败，方案已保留。"); }
    finally { setSaving(false); }
  }


  return <section className="data-section">
    <div className="data-section-header"><div><h3>分组方案</h3><p>从指标表选择真实分组，保存字段和展示顺序。</p></div><div className="data-row-actions"><span className="data-muted">{dataset ? `当前数据集：${dataset}` : "当前项目全部数据集"}</span><button className="btn btn-primary" disabled={saving || loadingDetail} onClick={() => protect(() => {reset();setEditorOpen(true);})}>新建分组方案</button></div></div>
    {notice && <p role="status" className="data-notice">{notice}</p>}
    {showEditor && <div className="data-group-editor">
      <div className="data-section-header"><h4>{editing ? `编辑方案：${editing.name}` : copying ? `${manual ? "复制手工方案" : "复制并绑定新版本"}：${copying.name}` : "创建分组方案"}</h4><button className="btn btn-secondary" disabled={saving} onClick={() => protect(reset)}><X size={15} />取消编辑</button></div>
      {copying && <p className="data-muted">复制来源：{copying.name} · 版本 {String(copying.spec_json.source_content_version || "未绑定").slice(0, 8)}。{manual ? "手工分组和原有属性已保留，可调整后另存。" : "请选择目标指标表版本并重新确认分组。"}</p>}
      <label className="field-label">方案名称<input className="input" value={name} onChange={event => setName(event.target.value)} disabled={saving} placeholder="例如：处理组与对照组" maxLength={255} /></label>
      {!manual && <>
        <div className="data-source-picker" role="group" aria-label="指标来源查询">
          <form className="data-query-bar" onSubmit={event => {event.preventDefault();setAssetSearch(assetDraft.trim());setAssetPage(1);}}>
            <input className="input" aria-label="搜索指标表名称" placeholder="按文件名称查找指标版本" value={assetDraft} disabled={saving} onChange={event => setAssetDraft(event.target.value)}/>
            <button type="submit" className="btn btn-secondary" disabled={saving}>查询来源</button>
            {assetSearch && <button type="button" className="btn btn-secondary" disabled={saving} onClick={() => {setAssetDraft("");setAssetSearch("");setAssetPage(1);}}>清除来源搜索</button>}
          </form>
          <label className="data-source-history"><input type="checkbox" checked={!!editing || assetHistory} disabled={saving || !!editing} onChange={event => {setAssetHistory(event.target.checked);setAssetPage(1);}}/>显示历史指标版本</label>
        </div>
        <label className="field-label">来源指标表与版本<Select value={sourceId} ariaLabel="方案来源指标表" disabled={saving || assetStatus !== "ready"}
          options={[{ value: "", label: "请选择指标表版本" }, ...(sourceId && !source ? [{value:sourceId,label:pinnedError ? "当前来源（读取失败）" : "当前来源（正在读取）"}] : []), ...displayedAssets.map(asset => ({ value: asset.id,
            label: `${getAssetSetName(asset)} · ${asset.original_name} · ${String(asset.metadata?.content_version || asset.id).slice(0, 8)}${asset.metadata?.superseded ? " · 历史版本" : ""}` }))]}
          onChange={value => { if (value !== sourceId) protectSelection(() => {
            const chosen = displayedAssets.find(asset => asset.id === value); if (chosen) setPinned({scope:sourceScope,asset:chosen});
            setPinnedError("");setPinRetry(0);setSourceId(value);setField("");setSheet(null);setOrder([]);
          }); }} /></label>
        {source && !sourcePresent && <p className="data-muted">已选来源保留在当前候选页之外：{source.original_name}</p>}
        {pinnedError && <p className="data-error" role="alert">{pinnedError}<button className="btn btn-secondary" onClick={() => setPinRetry(value => value + 1)}>重新读取当前指标</button></p>}
        {assetPagination && assetPagination.total_pages > 1 && <div className="data-source-pages"><span>匹配 {assetPagination.total} 份指标表 · 第 {assetPage} / {assetPagination.total_pages} 页</span><div>
          <button className="btn btn-secondary" aria-label="指标表上一页" disabled={saving || assetStatus !== "ready" || assetPage<=1} onClick={() => setAssetPage(page => page-1)}>上一页</button>
          <button className="btn btn-secondary" aria-label="指标表下一页" disabled={saving || assetStatus !== "ready" || assetPage>=assetPagination.total_pages} onClick={() => setAssetPage(page => page+1)}>下一页</button>
        </div></div>}
        {schema && schema.sheets.length > 1 && <label className="field-label">来源工作表<Select value={sheet || ""} ariaLabel="方案来源工作表" disabled={saving}
          options={[{value:"",label:"请选择工作表"}, ...schema.sheets.map(value => ({value,label:value}))]} onChange={value => {if ((value || null) !== sheet) protectSelection(() => {setSheet(value || null);setField("");setOrder([]);});}} /></label>}
        {schema && !schema.requires_sheet_selection && <label className="field-label">分组字段<Select value={field} ariaLabel="方案分组字段" disabled={saving}
          options={[{value:"",label:"请选择分组字段"}, ...schema.columns.map(value => ({value,label:value}))]} onChange={value => {if(value !== field) protectSelection(() => {setField(value);setOrder([]);});}} /></label>}
        {reading && <p role="status">正在读取实际字段与分组值…</p>}
        {sourceError && <p className="data-error" role="alert">{sourceError}<button className="btn btn-secondary" onClick={() => setRetry(value => value + 1)}>重新读取</button></p>}
        {assetStatus === "loading" && <p role="status">正在读取当前范围的指标表与版本…</p>}
        {assetStatus === "error" && <p className="data-error" role="alert">{assetError}<button className="btn btn-secondary" onClick={() => setRetry(value => value + 1)}>重新读取指标表</button></p>}
        {assetStatus === "ready" && !assets.length && !assetSearch && <div className="data-group-source-empty"><p>当前范围暂无指标表。请先导入用于分组的指标表。</p>
          <a className="btn btn-primary" href={`/management/projects/${encodeURIComponent(projectId || "")}?tab=assets&import=1&file_type=profile&asset_set=${encodeURIComponent(dataset)}`}>导入指标表</a></div>}
        {assetStatus === "ready" && !assets.length && assetSearch && <p className="data-muted">没有符合名称的指标表，请调整搜索；已选来源仍保留。</p>}
        {values && <>
          <p className="data-muted">此方案定义分组字段和展示顺序；分析样本范围仍需在分析配置中确认。</p>
          <GroupValueEditor key={JSON.stringify([sourceId,field,sheet])} values={values.values} order={order} onChange={setOrder} disabled={saving}
            countLabel={value=>values.sample_column ? `${values.sample_counts?.[value] ?? values.samples_by_value[value]?.length ?? 0} 个样本编号` : `${values.row_counts[value] || 0} 行`}/>
          {missing.length > 0 && <p role="alert" className="data-error">以下旧分组不在当前来源中：{missing.join("、")}。请重新选择来源或移除这些分组。<button className="btn btn-secondary" onClick={() => setOrder(previous => previous.filter(value => values.values.includes(value)))}>移除未匹配分组</button></p>}
        </>}
      </>}
      {manual && <><p className="data-muted">当前为手工方案；保留原配置，使用分析时请确认字段及分组值与输入一致。</p><label className="field-label">分组名称（按顺序，用逗号或顿号分隔）<input className="input" value={manualGroups} onChange={event => setManualGroups(event.target.value)} disabled={saving} placeholder="例如：健康组、疾病组" /></label></>}
      {!editing && !copying && <button className="btn btn-secondary" disabled={saving} onClick={() => protectSelection(() => {setManual(!manual);setOrder([]);})}>{manual ? "从指标表选择分组" : "高级选项：手工定义分组"}</button>}
      {invalidOrder && selected.length > 0 && <p role="alert" className="data-error">分组名称不能重复或包含英文逗号。</p>}
      {error && !confirm && <p role="alert" className="data-error">{error}</p>}
      {conflict && <section className="data-group-conflict" role="status"><strong>方案已在其他页面更新</strong><p>本地编辑仍保留。可以查看最新方案，或用新名称另存当前编辑。</p><div className="data-row-actions"><button className="btn btn-secondary" disabled={readingLatest || saving} onClick={readLatest}>{readingLatest?"正在读取…":"读取最新方案"}</button><button className="btn btn-secondary" disabled={saving} onClick={()=>{setName(name+"（副本）");setCopying(editing);setEditing(null);setConflict(false);setError("");}}>另存当前编辑</button></div></section>}
      <div className="data-group-save"><span role="status">{saving?"正在保存完整方案…":`${selected.length} 组 · ${dirty?"有未保存修改":"完整顺序已保留"}`}</span><button className="btn btn-primary" onClick={save} disabled={saving || loadingDetail || conflict || !name.trim() || invalidOrder || (!manual && (assetStatus !== "ready" || !source || !values || reading || !!sourceError || !!missing.length))}><Save size={15} />{saving ? "正在保存…" : "保存"}</button></div>
    </div>}
    {managed && projectId ? <GroupSpecCatalog projectId={projectId} dataset={dataset} revision={revision} busy={saving}
      onDetailBusyChange={setLoadingDetail} onEdit={scheme => protect(() => edit(scheme as Scheme))}
      onCopy={scheme => copy(scheme as Scheme)} onDelete={scheme => {setError("");setConfirm(scheme);}}/>
      : loading ? <p role="status">正在读取方案…</p> : !schemes.length ? <p className="data-muted">暂无分组方案。创建后可用于指标分析中的分组顺序设置。</p> : schemes.map(scheme => <article className="data-group-card" key={scheme.id} id={"group-spec-"+scheme.id} data-focused={focusedSpec===scheme.id}>
      <div><h4>{scheme.name}</h4><p>{(scheme.spec_json?.groups || []).slice(0,6).map(groupName).join(" → ")}{(scheme.spec_json?.groups?.length || 0)>6 ? ` … · 共 ${scheme.spec_json.groups!.length} 组，编辑查看完整顺序` : ""}</p><span className="data-muted">{scheme.spec_json?.group_field ? `分组字段：${scheme.spec_json.group_field}` : "使用分析配置中的分组字段"}{scheme.spec_json?.source_content_version ? ` · 来源版本 ${String(scheme.spec_json.source_content_version).slice(0, 8)}` : ""}</span>{scheme.source?.name && <p className="data-muted">来源：{scheme.source.asset_set} · {scheme.source.name}</p>}{scheme.source?.available === false && <p className="data-error" role="status">{scheme.source.reason}</p>}</div>
      <div className="data-row-actions"><button className="btn btn-secondary" disabled={saving} onClick={() => protect(() => edit(scheme))}><Pencil size={15} />编辑</button><button className="btn btn-secondary" disabled={saving} aria-label={`更多操作：${scheme.name}`} onClick={()=>setActionScheme(scheme)}>更多操作</button></div>
    </article>)}
    <Sheet open={!!actionScheme} onClose={()=>setActionScheme(null)} title="分组方案操作"><p>{actionScheme?.name}</p><div className="data-row-actions"><button className="btn btn-secondary" onClick={()=>{const item=actionScheme!;setActionScheme(null);copy(item);}}>复制并绑定新版本</button><button className="btn btn-danger" onClick={()=>{setError("");setConfirm(actionScheme);setActionScheme(null);}}><Trash2 size={15}/>删除</button></div></Sheet>
    <Sheet open={!!pendingAction} onClose={() => setPendingAction(null)} title="放弃未保存的分组编辑">
      <p>继续操作将替换当前分组编辑或已调整的选择与顺序，请确认是否放弃。</p><div className="data-row-actions">
        <button className="btn btn-primary" onClick={() => setPendingAction(null)}>继续编辑</button>
        <button className="btn btn-danger" onClick={() => { pendingAction?.(); setPendingAction(null); }}>放弃修改并继续</button>
      </div>
    </Sheet>
    <Sheet open={!!confirm} onClose={() => !saving && setConfirm(null)} title="确认删除分组方案">
      <p>将删除“{confirm?.name}”。任务引用的方案版本会受到保护。</p>{error && <p role="alert" className="data-error">{error}</p>}
      <div className="data-row-actions"><button className="btn btn-secondary" disabled={saving} onClick={() => setConfirm(null)}>取消</button><button className="btn btn-danger" disabled={saving} onClick={remove}>{saving ? "正在删除…" : "确认删除"}</button></div>
    </Sheet>
  </section>;
}
