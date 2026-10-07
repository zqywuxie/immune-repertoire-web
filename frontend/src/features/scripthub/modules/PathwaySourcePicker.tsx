import {useEffect,useId,useState} from "react";
import {apiClient} from "../../../shared/api/client";
import {SourceTaskLink,formatSourceTime} from "./SourceSelection";

type Source={id:string;job_id:string;status:string;reason:string;comparison?:{group1:string;group2:string};created_at?:string};
type Props={projectId?:string;assetSet?:string;value:string;disabled:boolean;onChange:(id:string,comparison:string[])=>void};
const readySource=(source:Source)=>source.status==="available"&&!!source.comparison?.group1&&!!source.comparison?.group2&&source.comparison.group1!==source.comparison.group2;

export function PathwaySourcePicker({projectId,assetSet,value,disabled,onChange}:Props){
  const [sources,setSources]=useState<Source[]>([]);
  const [busy,setBusy]=useState(true);
  const [error,setError]=useState("");
  const [revision,setRevision]=useState(0);
  const radioName=useId();
  useEffect(()=>{
    let active=true;
    setBusy(true);setError("");setSources([]);
    if(!projectId||!assetSet){setBusy(false);return;}
    apiClient.get<{candidates:Source[]}>("/api/script-hub/immune-infiltration-pathway/sources",{project_id:projectId,asset_set:assetSet},{skipCache:true,deduplicate:false})
      .then(result=>{if(active)setSources(result.candidates||[]);})
      .catch(reason=>{if(active)setError(reason instanceof TypeError?"网络连接中断，请重新读取。":reason instanceof Error?reason.message:"通路来源读取失败");})
      .finally(()=>{if(active)setBusy(false);});
    return()=>{active=false;};
  },[projectId,assetSet,revision]);
  const available=sources.filter(readySource);
  const refresh=()=>{
    const selected=sources.find(item=>item.id===value);
    // An explicit refresh invalidates the confirmed parent analysis scope.
    // Preserve a recorded direction; missing metadata is not a replacement direction.
    if(selected?.comparison)onChange(value,[selected.comparison.group1,selected.comparison.group2]);
    setRevision(count=>count+1);
  };
  const upstreamQuery=new URLSearchParams();
  if(projectId)upstreamQuery.set("project",projectId);
  if(assetSet)upstreamQuery.set("asset_set",assetSet);
  return <section className="source-selection" aria-label="通路来源选择" aria-busy={busy}>
    <fieldset disabled={disabled} style={{border:"1px solid var(--separator)",borderRadius:"var(--radius-control)",padding:16,marginTop:16,minWidth:0}}>
      <legend>选择已有 GO-BP 富集结果</legend>
      <p style={{color:"var(--text-secondary)",lineHeight:1.7}}>选择当前数据集的完整通路结果。比较方向沿用来源：前一组相对于后一组；本次不重新计算富集。</p>
      {!projectId||!assetSet ? <p>请先选择项目和数据集。</p> : <>
        <div className="source-selection-actions"><span>{busy?"正在读取通路来源…":error?"来源读取未完成":available.length+"/"+sources.length+" 项来源可用"}</span>
          <button type="button" className="btn btn-secondary" disabled={busy} onClick={refresh}>刷新来源</button></div>
        {busy&&<p role="status">正在核对当前项目和数据集的通路来源…</p>}
        {error&&<div role="alert" className="source-selection-message"><p>通路来源读取失败：{error}</p><button type="button" className="btn btn-secondary" onClick={refresh}>重新读取通路来源</button></div>}
        {!busy&&!error&&!available.length&&<div className="source-selection-message">
          <p>{sources.length?"已有通路来源目前均不可用，请查看对应原因。":"暂无来源。请先在“GO / KEGG 富集”中启用 GSEA 并完成分析，再返回刷新。"}</p>
          <a className="source-task-link" href={"/analysis/tools/go-kegg?" + upstreamQuery} target="_blank" rel="noreferrer">前往 GO / KEGG 富集 ↗</a>
        </div>}
        <div style={{display:"grid",gap:12}}>{sources.map(item=>{
          const ready=readySource(item),direction=item.comparison?item.comparison.group1+" 相对于 "+item.comparison.group2:"来源方向缺失";
          return <div key={item.id} className="pathway-source-card" data-selected={value===item.id}>
            <label style={{cursor:ready&&!busy?"pointer":"default"}}>
              <input type="radio" name={"pathway-source-"+radioName} aria-label={direction+" · "+item.job_id} checked={value===item.id} disabled={!ready||busy}
                onChange={()=>item.comparison&&onChange(item.id,[item.comparison.group1,item.comparison.group2])}/>
              <span><strong>{direction}</strong><small>来源任务：{item.job_id}</small>
                <small>{formatSourceTime(item.created_at)} · {ready?"完整通路表可用":"暂不可用"}</small>
                {!ready&&<span style={{display:"block",marginTop:6}}>{item.reason||"来源比较方向不完整，不能使用。"}</span>}
              </span>
            </label>
            <SourceTaskLink jobId={item.job_id} projectId={projectId} assetSet={assetSet}/>
          </div>;
        })}</div>
        {value&&!busy&&!error&&!sources.some(item=>item.id===value&&readySource(item))&&<p role="alert">所选来源当前不可用，请重新选择。</p>}
      </>}
    </fieldset>
  </section>;
}
