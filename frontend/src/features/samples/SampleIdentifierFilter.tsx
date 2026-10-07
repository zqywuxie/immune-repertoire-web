import { useEffect, useState } from "react";
import { Search } from "lucide-react";
import { getSampleFieldCandidates, type SampleIdentifierField } from "../../shared/api/samples";
import { useApi } from "../../shared/hooks/useApi";
import { Pagination } from "../../shared/components/Pagination";

export function SampleIdentifierFilter({field,label,value,projectId,dataset,onChange}:{field:SampleIdentifierField;label:string;value:string;projectId:string;dataset:string;onChange:(value:string)=>void}) {
  const [open,setOpen]=useState(false),[draft,setDraft]=useState(""),[search,setSearch]=useState(""),[page,setPage]=useState(1);
  const tag=JSON.stringify([projectId,dataset,field,search,page]);
  const response=useApi(()=>getSampleFieldCandidates(projectId,dataset,field,search,page).then(data=>({tag,data})),[tag],open);
  const data=response.status==="ready" && response.data.tag===tag ? response.data.data : null;
  useEffect(()=>{if(data && page>Math.max(1,data.pagination.total_pages))setPage(Math.max(1,data.pagination.total_pages));},[data,page]);
  function choose(next:string){onChange(next);setOpen(false);}
  return <details className="data-identifier-filter" open={open} onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary aria-label={`${label}筛选`}><span>{label}</span><strong>{value || "全部编号"}</strong></summary>
    {open && <div className="data-identifier-options" aria-label={`${label}候选`}>
      <form className="data-query-bar" onSubmit={event=>{event.preventDefault();setSearch(draft.trim());setPage(1);}}>
        <input className="input" aria-label={`搜索${label}候选`} maxLength={200} value={draft} onChange={event=>setDraft(event.target.value)} placeholder="输入编号查找"/>
        <button className="btn btn-secondary" type="submit"><Search size={15}/>查询</button>
      </form>
      {value && <p className="data-muted">当前条件：{value}</p>}
      <button className="btn btn-secondary" onClick={()=>choose("")}>全部{label}</button>
      {response.status==="error" ? <div role="alert"><p className="data-error">候选读取失败：{response.error}</p><button className="btn btn-secondary" onClick={response.refetch}>重新读取候选</button></div>
        :data ? <><p className="data-muted" role="status">匹配 {data.pagination.total} 个编号 · 每页最多 20 个</p>
          <div className="data-identifier-values">{data.values.map(item=><button key={item} className={value===item?"is-selected":""} aria-pressed={value===item} onClick={()=>choose(item)}>{item}</button>)}</div>
          {!data.values.length && <p>没有匹配的编号，请调整搜索。</p>}
          <nav aria-label={`${label}候选分页`}><Pagination pagination={data.pagination} onPageChange={setPage}/></nav></>
          :<p role="status">正在读取编号候选…</p>}
    </div>}
  </details>;
}
