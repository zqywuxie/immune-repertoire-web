import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { GitBranch, Pencil, Search, Trash2, Copy, X } from "lucide-react";
import { getGroupSpec, listGroupSpecCatalog, type FullGroupSpec, type GroupSpecSummary } from "../../shared/api/groupSpecs";
import { useApi } from "../../shared/hooks/useApi";
import { Pagination } from "../../shared/components/Pagination";
import { Sheet } from "../../shared/components/Sheet";
import { DataReadError } from "../assets/DataReadError";

type Props = {projectId:string; dataset:string; revision:number; busy:boolean;
  onDetailBusyChange:(busy:boolean)=>void; onEdit:(scheme:FullGroupSpec)=>void;
  onCopy:(scheme:FullGroupSpec)=>void; onDelete:(scheme:Pick<FullGroupSpec,"id"|"name">)=>void};
export function GroupSpecCatalog({projectId,dataset,revision,busy,onDetailBusyChange,onEdit,onCopy,onDelete}:Props) {
  const [query,setQuery] = useSearchParams();
  const search = query.get("group_q") || "";
  const page = Math.max(1,Math.floor(Number(query.get("group_page")) || 1));
  const focusedId = query.get("group_spec") || "";
  const [draft,setDraft] = useState(search);
  const [action,setAction] = useState<GroupSpecSummary|null>(null);
  const [readingId,setReadingId] = useState("");
  const [detailError,setDetailError] = useState("");
  const live = useRef(true);
  useEffect(()=>{live.current=true;return()=>{live.current=false;};},[]);
  useEffect(()=>setDraft(search),[search]);
  useEffect(()=>{onDetailBusyChange(!!readingId);},[readingId,onDetailBusyChange]);
  useEffect(()=>()=>onDetailBusyChange(false),[onDetailBusyChange]);
  const catalog = useApi(()=>listGroupSpecCatalog(projectId,{assetSet:dataset,search,page,pageSize:20}),[projectId,dataset,search,page,revision]);
  const items = catalog.status === "ready" ? catalog.data.items : [];
  const outsidePage = catalog.status === "ready" && !!focusedId && !items.some(item=>item.id===focusedId);
  const focused = useApi(()=>getGroupSpec(projectId,focusedId),[projectId,focusedId],outsidePage);
  useEffect(()=>{
    if(catalog.status!=="ready")return;
    const last=Math.max(1,catalog.data.pagination.total_pages);
    if(page>last)setQuery(previous=>{const next=new URLSearchParams(previous);last>1?next.set("group_page",String(last)):next.delete("group_page");return next;},{replace:true});
  },[catalog.status,catalog.status==="ready"?catalog.data.pagination:null,page,setQuery]);
  useEffect(()=>{
    if(!focusedId)return;
    document.getElementById("group-spec-"+focusedId)?.scrollIntoView?.({block:"center"});
  },[focusedId,catalog.status,focused.status]);
  function filter(value:string) {
    setQuery(previous=>{const next=new URLSearchParams(previous);value.trim()?next.set("group_q",value.trim()):next.delete("group_q");next.delete("group_page");return next;});
  }
  async function load(item:GroupSpecSummary, mode:"edit"|"copy") {
    if(busy || readingId)return;
    setReadingId(item.id);setDetailError("");setAction(null);
    try {
      const full=await getGroupSpec(projectId,item.id);
      if(!live.current)return;
      if(full.spec_json.groups!==undefined && !Array.isArray(full.spec_json.groups))throw new Error("完整分组格式不正确，请重新读取；当前编辑仍保留。");
      mode==="edit"?onEdit(full):onCopy(full);
    }catch(reason){if(live.current)setDetailError(reason instanceof Error?reason.message:"完整方案读取失败，当前编辑仍保留。");}
    finally{if(live.current)setReadingId("");}
  }
  const blocked=busy || !!readingId;
  function card(item:GroupSpecSummary, pinned=false) {
    const mismatch=!!dataset && !!item.asset_set && item.asset_set!==dataset;
    return <article className="data-group-card data-group-catalog-card" key={item.id} id={"group-spec-"+item.id} data-focused={focusedId===item.id}>
      <div className="data-group-catalog-copy"><div className="data-group-catalog-title"><GitBranch size={18} aria-hidden="true"/><h4>{item.name}</h4>
        <span className="data-group-count">{item.group_count} 组</span></div>
        {pinned && <p className="data-muted">链接指定的方案 · 不在当前列表页</p>}
        <p className="data-group-preview">{item.group_preview.join(" → ")}{item.group_count>item.group_preview.length?" …":""}</p>
        <p className="data-muted">{item.project_wide?"项目通用方案":`数据集：${item.asset_set}`} · {item.group_field?`分组字段：${item.group_field}`:"使用分析配置中的分组字段"}</p>
        {item.source?.name && <p className="data-muted">来源：{item.source.name}{item.source_content_version?` · 版本 ${item.source_content_version.slice(0,8)}`:""}</p>}
        {item.source?.available===false && <p className="data-error" role="status">{item.source.reason}</p>}
        {mismatch && <p className="data-scope-mismatch">此方案属于其他数据集。<a className="btn btn-secondary" href={`?${new URLSearchParams({...Object.fromEntries(query),asset_set:item.asset_set,group_spec:item.id,group_page:"1"})}`}>切换到所属数据集查看</a></p>}
      </div>
      {!mismatch && <div className="data-row-actions"><button className="btn btn-secondary" disabled={blocked} onClick={()=>load(item,"edit")} aria-label={`编辑方案：${item.name}`}><Pencil size={15}/>编辑</button>
        <button className="btn btn-secondary" disabled={blocked} aria-label={`更多操作：${item.name}`} onClick={()=>{setDetailError("");setAction(item);}}>更多操作</button></div>}
    </article>;
  }
  return <div className="data-group-catalog">
    <form className="data-group-catalog-query" onSubmit={event=>{event.preventDefault();filter(draft);}}>
      <label className="data-group-search"><Search size={16} aria-hidden="true"/><input className="input" aria-label="搜索分组方案名称" placeholder="按方案名称查找" value={draft} onChange={event=>setDraft(event.target.value)}/></label>
      <button className="btn btn-secondary" type="submit">查询方案</button>
      {search && <button className="btn btn-secondary" type="button" onClick={()=>{setDraft("");filter("");}}>清除方案搜索</button>}
    </form>
    {readingId && <p role="status" className="data-notice">正在读取完整方案，当前编辑保留…</p>}
    {detailError && <p role="alert" className="data-error">{detailError}</p>}
    {catalog.status==="error" && <DataReadError title="分组方案暂时无法读取" message={catalog.error} onRetry={catalog.refetch} retryLabel="重新读取方案"/>}
    {(catalog.status==="loading" || catalog.status==="idle") && <p role="status">正在读取分组方案…</p>}
    {catalog.status==="ready" && <><p className="data-muted" role="status">当前范围匹配 {catalog.data.pagination.total} 个方案 · 每页最多 20 个</p>
      {!items.length && <div className="data-group-catalog-empty"><GitBranch size={24} aria-hidden="true"/><p>{search?"没有匹配的方案，请调整名称搜索。":"当前范围暂无分组方案，可点击上方「新建分组方案」开始。"}</p></div>}
      {items.map(item=>card(item))}<nav aria-label="分组方案分页"><Pagination pagination={catalog.data.pagination} onPageChange={value=>setQuery(previous=>{const next=new URLSearchParams(previous);value>1?next.set("group_page",String(value)):next.delete("group_page");return next;})}/></nav></>}
    {outsidePage && <section className="data-group-pinned" aria-label="链接指定分组方案">
      <button className="btn btn-secondary" onClick={()=>setQuery(previous=>{const next=new URLSearchParams(previous);next.delete("group_spec");return next;},{replace:true})}><X size={14}/>取消方案定位</button>
      {focused.status==="error"?<DataReadError title="指定方案暂时无法读取" message={focused.error} onRetry={focused.refetch} retryLabel="重新读取指定方案"/>
        :focused.status==="ready"?card(toSummary(focused.data),true):<p role="status">正在读取链接指定的方案…</p>}
    </section>}
    <Sheet open={!!action} title="分组方案操作" onClose={()=>setAction(null)}>{action && <><p>{action.name} · {action.group_count} 组</p><div className="data-row-actions">
      <button className="btn btn-secondary" disabled={blocked} onClick={()=>load(action,"copy")}><Copy size={15}/>{action.source?.asset_id?"复制并绑定新版本":"复制手工方案"}</button>
      <button className="btn btn-danger" disabled={blocked} onClick={()=>{onDelete(action);setAction(null);}}><Trash2 size={15}/>删除方案</button></div></>}</Sheet>
  </div>;
}
function toSummary(full:FullGroupSpec):GroupSpecSummary {
  const definition=full.spec_json;
  const groups=Array.isArray(definition.groups)?definition.groups:[];
  const assetSet=String(definition.asset_set || full.source?.asset_set || "");
  return {...full,group_count:groups.length,group_preview:groups.slice(0,6).map(group=>typeof group==="string"?group:String(group?.name || group?.label || "")),
    group_field:String(definition.group_field || ""),asset_set:assetSet,project_wide:!assetSet,source_content_version:String(definition.source_content_version || "")};
}
