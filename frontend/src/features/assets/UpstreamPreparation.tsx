import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowRight, Files, Search } from "lucide-react";
import { analysisTools } from "../analysis/tools";
import type { PreparationSource } from "../analysis/analysisPreparation";
import { SourceTaskLink, formatSourceTime } from "../scripthub/modules/SourceSelection";
import { getUpstreamSummary, getUpstreamCatalog } from "../../shared/api/upstreamSources";
import { useApi } from "../../shared/hooks/useApi";
import { Select } from "../../shared/components/Select";
import { Pagination } from "../../shared/components/Pagination";

export function UpstreamPreparation({projectId,dataset,source,revision,returnPath,active=true}:{projectId:string;dataset:string;source:PreparationSource;revision:number;returnPath:string;active?:boolean}) {
  const [query,setQuery]=useSearchParams();
  const open=query.get("prepare_sources")==="1",search=query.get("prepare_q") || "",status=["available","unavailable"].includes(query.get("prepare_status") || "")?query.get("prepare_status")!:"";
  const page=Math.max(1,Math.floor(Number(query.get("prepare_page")) || 1));
  const [draft,setDraft]=useState(search),[refresh,setRefresh]=useState(0);
  useEffect(()=>setDraft(search),[search]);
  const scope=JSON.stringify([projectId,dataset,source.kind,source.cacheType,revision,refresh]);
  const request=JSON.stringify([scope,search,status,page]);
  const summary=useApi(async()=>({...await getUpstreamSummary(projectId,dataset,source),scope}),[scope],active&&!open);
  const catalog=useApi(async()=>({...await getUpstreamCatalog(projectId,dataset,source,{page,search,status}),request}),[request],active&&open);
  const ready=catalog.status==="ready"&&catalog.data.request===request;
  const counts=open ? (ready?catalog.data.summary:undefined) : summary.status==="ready"&&summary.data.scope===scope?summary.data.summary:undefined;
  const error=open?(catalog.status==="error"?catalog.error:""):(summary.status==="error"?summary.error:"");
  function update(key:string,value:string) {
    setQuery(previous=>{const next=new URLSearchParams(previous);value?next.set(key,value):next.delete(key);if(key!=="prepare_page")next.delete("prepare_page");return next;});
  }
  useEffect(()=>{if(ready&&page>Math.max(1,catalog.data.pagination.total_pages || 0))update("prepare_page",String(Math.max(1,catalog.data.pagination.total_pages || 0)));},[ready,ready?catalog.data.pagination.total_pages:0,page]);
  const params=new URLSearchParams({project:projectId,asset_set:dataset,return_to:returnPath});
  return <section className="preparation-upstream" aria-label="前置结果准备">
    <div className="preparation-step"><Files size={19} className="preparation-status" aria-hidden="true"/><div className="preparation-step-copy"><strong>{source.title}</strong><p>{source.hint}</p></div>
      <button type="button" className="btn btn-secondary" disabled={!active || (!counts&&!error)} onClick={()=>setRefresh(value=>value+1)}>刷新前置结果</button></div>
    {error?<p role="alert" className="data-error">前置结果读取失败：{error}。可点击“刷新前置结果”重试。</p>:counts?<p role="status">{counts.available?`${counts.available} 项前置结果可用，请在分析配置中选择。`:counts.total?"已有前置结果目前不可用，请查看原因或重新运行。":"当前数据集尚无可用前置结果。"}{counts.unavailable>0?` 另有 ${counts.unavailable} 项不可用。`:""}</p>:<p role="status">正在核对当前数据集的前置结果…</p>}
    {!open&&counts&&counts.unavailable>0&&<ul className="preparation-reasons">{counts.reasons.slice(0,3).map(item=><li key={item.reason}>{item.reason}（{item.count} 项）</li>)}</ul>}
    <details open={open} onToggle={event=>{if(event.currentTarget.open!==open)update("prepare_sources",event.currentTarget.open?"1":"");}}>
      <summary>查找来源任务与状态{counts?`（${counts.total}）`:""}</summary>
      {open&&<><form className="preparation-source-query" onSubmit={event=>{event.preventDefault();update("prepare_q",draft.trim());}}>
        <label><Search size={16} aria-hidden="true"/><input className="input" maxLength={200} aria-label="查找前置结果" placeholder="搜索任务名称、编号或比较组别" value={draft} onChange={event=>setDraft(event.target.value)}/></label>
        <Select ariaLabel="前置结果状态" value={status} options={[{value:"",label:"全部状态"},{value:"available",label:"可用结果"},{value:"unavailable",label:"不可用结果"}]} onChange={value=>update("prepare_status",value)}/>
        <button type="submit" className="btn btn-secondary">查询来源</button>
        {(search||status)&&<button type="button" className="btn btn-secondary" onClick={()=>{setDraft("");setQuery(previous=>{const next=new URLSearchParams(previous);for(const key of ["prepare_q","prepare_status","prepare_page"])next.delete(key);return next;});}}>清除来源筛选</button>}
      </form>
      {ready?<><p className="data-muted">当前筛选共 {catalog.data.pagination.total} 项；每页最多 20 项。</p>
        {!catalog.data.candidates.length&&<p className="preparation-source-empty">{search||status?"没有符合筛选的前置结果，请调整查询条件。":"当前数据集没有前置结果，可先运行来源分析。"}</p>}
        <ul className="preparation-sources">{catalog.data.candidates.map(item=><li key={item.id}>
          <div className="preparation-source-copy"><strong>{item.source_task_name}</strong><small>{formatSourceTime(item.created_at).replace(/\bUTC\b/g,"协调世界时")}</small>{item.description&&<small>{item.description}</small>}<p className={item.status==="available"?"preparation-source-available":""}>{item.status==="available"?"可用；具体版本和样本范围在配置中确认。":item.reason||"来源暂不可用。"}</p></div>
          {item.job_id?<SourceTaskLink jobId={item.job_id} projectId={projectId} assetSet={dataset}/>:<span>未记录来源任务</span>}</li>)}</ul>
        <Pagination pagination={catalog.data.pagination} onPageChange={value=>update("prepare_page",String(value))}/></>:!error&&<p role="status">正在读取来源列表…</p>}</>}
    </details>
    <Link className="preparation-link" to={`/analysis/tools/${source.upstreamTool}?${params}`}>前往{analysisTools.find(tool=>tool.id===source.upstreamTool)?.title}<ArrowRight size={14} aria-hidden="true"/></Link>
  </section>;
}
