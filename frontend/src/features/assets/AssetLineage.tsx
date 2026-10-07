import {useEffect,useState} from "react";
import {getAssetLineage,type LineageSection} from "../../shared/api/assetLineage";
import {useApi} from "../../shared/hooks/useApi";
import {Pagination} from "../../shared/components/Pagination";
import {StatusBadge} from "../../shared/components/StatusBadge";
import {analysisLabel} from "../../shared/utils/analysisLabels";
import {projectAssetDetailPath} from "./assetSets";
import {formatSourceTime} from "../scripthub/modules/SourceSelection";
import "./AssetLineage.css";

const labels:Record<LineageSection,string>={versions:"版本记录",jobs:"引用任务",groups:"引用分组方案"};
export function AssetLineage({projectId,assetId,initialSection="versions",initialOpen=false}:{projectId:string;assetId:string;initialSection?:LineageSection;initialOpen?:boolean}) {
  const [open,setOpen]=useState(initialOpen),[section,setSection]=useState<LineageSection>(initialSection),[page,setPage]=useState(1);
  return <details className="asset-lineage" open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary>版本与引用</summary>
    {open && <><div className="asset-lineage-tabs" role="group" aria-label="版本与引用分类">{Object.entries(labels).map(([key,label])=><button type="button" key={key} className="btn btn-secondary" aria-pressed={section===key} onClick={()=>{setSection(key as LineageSection);setPage(1);}}>{label}</button>)}</div>
      <LineageList key={JSON.stringify([projectId,assetId,section,page])} projectId={projectId} assetId={assetId} section={section} page={page} onPage={setPage}/></>}
  </details>;
}
function LineageList({projectId,assetId,section,page,onPage}:{projectId:string;assetId:string;section:LineageSection;page:number;onPage:(page:number)=>void}) {
  const state=useApi(()=>getAssetLineage(projectId,assetId,section,page),[projectId,assetId,section,page]);
  useEffect(()=>{if(state.status==="ready"&&page>Math.max(1,state.data.pagination.total_pages))onPage(Math.max(1,state.data.pagination.total_pages));},[state.status,state.status==="ready"?state.data.pagination:null,page,onPage]);
  return <section aria-label={labels[section]}>
    {section==="versions" && <p className="asset-lineage-hint">按保存的替换关系展示；批量替换可能包含多份文件。相同文件名不会自动归为同一版本链。</p>}
    {section==="jobs" && <p className="asset-lineage-hint">包含任务保存的文件标识或路径引用。完成的输入校验不占用文件。</p>}
    {state.status==="idle" || state.status==="loading" ? <p role="status">正在读取{labels[section]}…</p> : state.status==="error" ? <div role="alert"><p>读取失败：{state.error}</p><button type="button" className="btn btn-secondary" onClick={state.refetch}>重新读取{labels[section]}</button></div> : <>
      {!state.data.items.length && <p className="asset-lineage-hint">{section==="jobs"?"没有找到引用此文件的任务。":section==="groups"?"没有分组方案引用此文件。":"没有可展示的版本记录。"}</p>}
      {!!state.data.unavailable_links && <p role="status" className="asset-lineage-hint">{state.data.unavailable_links} 项替换记录指向已不可读取的资产。</p>}
      <ol className="asset-lineage-list">{state.data.items.map(item=>{
        const jobQuery=new URLSearchParams({project:projectId,job:item.id});if(item.asset_set)jobQuery.set("asset_set",item.asset_set);
        const groupQuery=new URLSearchParams({tab:"group-specs",group_spec:item.id});
        return <li key={item.id} data-current={item.id===assetId}>
          <div className="asset-lineage-title"><strong>{item.name || (section==="jobs"?analysisLabel(item.module):"未记录名称")}</strong>{section==="versions" ? <span className="asset-lineage-badge">{item.superseded?"历史版本":"当前版本"}</span> : section==="jobs" ? <StatusBadge status={item.status || "unknown"}/> : null}</div>
          <p>{formatSourceTime(item.created_at || undefined)}{item.asset_set?` · ${item.asset_set}`:""}</p>
          <code title={item.id}>{item.id}</code>
          {section==="versions" && <><p>版本：{item.content_version || "未记录"}</p>{item.id===assetId ? <span className="asset-lineage-active">正在查看此版本</span> : <a className="btn btn-secondary" href={projectAssetDetailPath(projectId,item.id,item.asset_type==="group_spec"?"":item.asset_set || "")}>查看此版本</a>}</>}
          {section==="jobs" && <><p>{analysisLabel(item.module)} · {item.match==="asset_id"?"保存了文件标识":"保存了文件或目录路径"}</p><a className="btn btn-secondary" href={"/analysis/script-hub/jobs?"+jobQuery}>查看任务与结果</a></>}
          {section==="groups" && <a className="btn btn-secondary" href={`/management/projects/${encodeURIComponent(projectId)}?${groupQuery}`}>定位分组方案</a>}
        </li>;
      })}</ol>
      <Pagination pagination={state.data.pagination} onPageChange={onPage}/>
    </>}
  </section>;
}
