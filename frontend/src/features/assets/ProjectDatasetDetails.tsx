import {useEffect,useState} from "react";
import {ApiError} from "../../shared/api/client";
import {updateProjectDataset,type DatasetSummary} from "../../shared/api/projects";
import {Sheet} from "../../shared/components/Sheet";
import "./ProjectDatasetDetails.css";

type Draft={display_name:string;description:string;source:string;batch:string;archived:boolean};
function fields(dataset:DatasetSummary):Draft {
 return {display_name:dataset.display_name || dataset.name,description:dataset.description || "",source:dataset.source || "",batch:dataset.batch || "",archived:!!dataset.archived};
}
const labels:Record<keyof Draft,string>={display_name:"显示名称",description:"数据集说明",source:"数据来源",batch:"采集批次",archived:"归档状态"};
export function ProjectDatasetDetails({projectId,dataset,onChange,onDirty}:{projectId:string;dataset:DatasetSummary;onChange:()=>void;onDirty?:(dirty:boolean)=>void}) {
 const [open,setOpen]=useState(false),[confirmClose,setConfirmClose]=useState(false),[busy,setBusy]=useState(false);
 const [baseline,setBaseline]=useState(dataset),[draft,setDraft]=useState<Draft>(fields(dataset));
 const [error,setError]=useState(""),[latest,setLatest]=useState<DatasetSummary|null>(null),[notice,setNotice]=useState("");
 const before=fields(baseline);
 const changes=(Object.keys(draft) as Array<keyof Draft>).filter(key=>draft[key]!==before[key]);
 const dirty=open && changes.length>0;
 useEffect(()=>{onDirty?.(dirty || busy);return ()=>onDirty?.(false);},[dirty,busy,onDirty]);
 function edit(){setBaseline(dataset);setDraft(fields(dataset));setError("");setLatest(null);setNotice("");setOpen(true);}
 function close(){if(busy)return;if(dirty){setConfirmClose(true);return;}setOpen(false);}
 async function save(){
  if(!changes.length || busy || latest)return;
  setBusy(true);setError("");
  try{
   const updates=Object.fromEntries(changes.map(key=>[key,draft[key]]));
   await updateProjectDataset(projectId,{asset_set:dataset.name,expected_revision:baseline.revision || 0,...updates});
   setOpen(false);setNotice(draft.archived ? "数据集说明已保存，此数据集已归档；输入和历史任务保留。" : "数据集说明已保存。");onChange();
  }catch(reason){
   setError(reason instanceof Error ? reason.message : "数据集说明保存失败，修改已保留。");
   if(reason instanceof ApiError && reason.status===409){
    const value=reason.payload as {details?:{dataset?:DatasetSummary}};
    if(value.details?.dataset)setLatest(value.details.dataset);
   }
  }finally{setBusy(false);}
 }
 function review(){
  if(!latest)return;
  const next=fields(latest);
  for(const key of changes)Object.assign(next,{[key]:draft[key]});
  setDraft(next);setBaseline(latest);setLatest(null);setError("");
 }
 const title=dataset.display_name || dataset.name;
 return <section className="dataset-details" aria-label="数据集说明">
  <div className="dataset-details__heading"><div><strong>{title}</strong>{dataset.archived && <span className="dataset-details__archived">已归档</span>}{title!==dataset.name && <small>原关联标识：{dataset.name}</small>}</div>
   <button type="button" className="btn btn-secondary" onClick={edit}>编辑数据集说明</button></div>
  {dataset.description && <p>{dataset.description}</p>}
  {(dataset.source || dataset.batch) && <dl><div><dt>数据来源</dt><dd>{dataset.source || "未填写"}</dd></div><div><dt>采集批次</dt><dd>{dataset.batch || "未填写"}</dd></div></dl>}
  {dataset.archived && <p role="status">此数据集已从默认候选列表收起。可恢复；原始输入、样本登记、任务与结果继续保留。</p>}
  {notice && <p role="status">{notice}</p>}
  <Sheet open={open} onClose={close} title="编辑数据集说明" panelClassName="dataset-details__sheet">
   <p className="dataset-details__hint">关联标识「{dataset.name}」保持不变。修改显示名称不会改写已有任务和结果。</p>
   <form onSubmit={event=>{event.preventDefault();void save();}}>
    {(["display_name","source","batch"] as const).map(key=><label key={key}>{labels[key]}{key==="display_name" ? "（必填）" : ""}<input className="input" required={key==="display_name"} maxLength={key==="source"?500:120} value={draft[key]} disabled={busy} onChange={event=>setDraft(previous=>({...previous,[key]:event.target.value}))}/></label>)}
    <label>数据集说明<textarea className="input" maxLength={4000} rows={4} disabled={busy} value={draft.description} onChange={event=>setDraft(previous=>({...previous,description:event.target.value}))}/></label>
    <label className="dataset-details__archive"><input type="checkbox" checked={draft.archived} disabled={busy} onChange={event=>setDraft(previous=>({...previous,archived:event.target.checked}))}/>归档此数据集</label>
    <p className="dataset-details__hint">归档用于整理列表，不会删除文件、取消任务或断开历史引用。取消勾选并保存即可恢复。</p>
    {error && <p role="alert" className="data-error">{error}</p>}
    {latest && <div role="region" aria-label="核对数据集说明变化" className="dataset-details__conflict"><strong>其他页面已修改说明，请先核对</strong><dl>{(Object.keys(draft) as Array<keyof Draft>).filter(key=>fields(latest)[key]!==before[key]).map(key=><div key={key}><dt>{labels[key]}</dt><dd>最新：{typeof fields(latest)[key]==="boolean" ? fields(latest)[key] ? "已归档" : "未归档" : fields(latest)[key] || "未填写"}</dd><dd>本次：{typeof draft[key]==="boolean" ? draft[key] ? "已归档" : "未归档" : draft[key] || "未填写"}</dd></div>)}</dl><button type="button" className="btn btn-secondary" onClick={review}>保留修改，更新对照</button></div>}
    <div className="data-row-actions"><button type="button" className="btn btn-secondary" disabled={busy} onClick={close}>取消</button><button type="submit" className="btn btn-primary" disabled={busy || !changes.length || !draft.display_name.trim() || !!latest}>{busy?"正在保存…":"保存说明"}</button></div>
   </form>
  </Sheet>
  <Sheet layer={200} open={confirmClose} onClose={()=>setConfirmClose(false)} title="放弃未保存的数据集说明？"><p>当前修改尚未保存。</p><div className="data-row-actions"><button type="button" className="btn btn-primary" onClick={()=>setConfirmClose(false)}>继续编辑</button><button type="button" className="btn btn-danger" onClick={()=>{setConfirmClose(false);setOpen(false);}}>放弃修改</button></div></Sheet>
 </section>;
}
