import { useEffect, useState } from "react";
import { previewUploadImpact, uploadImpactKey } from "../../shared/api/projects";
import type { UploadImpact, UploadImpactItem } from "../../shared/api/projects";

export function UploadImpactPreview({projectId,pending,impacts,replaceExisting,loading,error,conflict,onRetry,onConflict,busy}:{
  projectId:string;pending:UploadImpactItem[];impacts:UploadImpact[];replaceExisting:boolean;
  loading:boolean;error:string;conflict:boolean;onRetry:()=>void;onConflict:()=>void;busy:boolean;
}) {
  const byKey = new Map(impacts.map(item=>[uploadImpactKey(item),item]));
  return <section className="data-upload-impact" aria-label="本次更新影响">
    <div className="data-section-header"><h4>确认保存范围</h4><span className="data-muted">原文件与历史任务继续保留</span></div>
    {replaceExisting && conflict ? <div className="data-impact-conflict" role="alert"><strong>当前文件版本已变化</strong><p>本次选择仍保留，请重新查看最新更新范围，再确认保存。</p><button className="btn btn-secondary" disabled={busy} onClick={onRetry}>重新核对更新范围</button></div>
    : replaceExisting && loading ? <p role="status">正在核对当前文件…</p>
    : replaceExisting && error ? <div className="data-impact-conflict" role="alert"><p>暂时无法核对更新范围：{error}</p><button className="btn btn-secondary" onClick={onRetry}>重新核对更新范围</button></div>
    : <ul>{pending.map((item,index)=><li key={uploadImpactKey(item)+index}>
      <div><strong>{item.name}</strong><small>数据集：{item.asset_set} · {item.directory ? "新增目录登记" : replaceExisting && byKey.get(uploadImpactKey(item))?.pagination.total ? `更新 ${byKey.get(uploadImpactKey(item))!.pagination.total} 个当前文件` : "新增输入"}</small></div>
      {replaceExisting && byKey.get(uploadImpactKey(item))?.pagination.total ? <AffectedVersions key={JSON.stringify(byKey.get(uploadImpactKey(item)))} projectId={projectId} impact={byKey.get(uploadImpactKey(item))!} onConflict={onConflict} busy={busy}/>
        : <p className="data-muted">{item.directory ? "目录登记不更新已有文件版本。" : "现有当前文件不会因本项退出当前版本。"}</p>}
    </li>)}</ul>}
  </section>;
}

function AffectedVersions({projectId,impact,onConflict,busy}:{projectId:string;impact:UploadImpact;onConflict:()=>void;busy:boolean}) {
  const [current,setCurrent] = useState(impact);
  const [loading,setLoading] = useState(false);
  const [error,setError] = useState("");
  const [target,setTarget] = useState<number | null>(null);
  useEffect(()=>{
    if(target===null)return;
    let active=true;setLoading(true);setError("");
    previewUploadImpact(projectId,[impact],{page:target,pageSize:impact.pagination.page_size}).then(result=>{
      if(!active)return;
      const next=result.impacts[0];
      if(!next || JSON.stringify(next.expected_versions)!==JSON.stringify(impact.expected_versions)){onConflict();return;}
      setCurrent(next);
    }).catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"受影响文件读取失败");})
      .finally(()=>{if(active){setLoading(false);setTarget(null);}});
    return ()=>{active=false;};
  },[projectId,impact,target]);
  return <div className="data-upload-replaced"><span>以下文件将保留为历史版本：</span>
    <ul>{current.assets.map(asset=><li key={asset.id}><span>{asset.original_name}</span><small>{asset.uploaded_at?.replace("T"," ").slice(0,16)||"时间未记录"} · 版本 {asset.content_version.slice(0,12)}</small></li>)}</ul>
    {current.pagination.total_pages>1 && <div className="data-impact-pages"><span>共 {current.pagination.total} 个 · 第 {current.pagination.page} / {current.pagination.total_pages} 页</span><div>
      <button className="btn btn-secondary" disabled={busy||loading||current.pagination.page<=1} onClick={()=>setTarget(current.pagination.page-1)}>上一页受影响文件</button>
      <button className="btn btn-secondary" disabled={busy||loading||current.pagination.page>=current.pagination.total_pages} onClick={()=>setTarget(current.pagination.page+1)}>下一页受影响文件</button></div></div>}
    {loading && <p role="status">正在读取受影响文件…</p>}
    {error && <p role="alert" className="data-error">{error}<button className="btn btn-secondary" onClick={()=>setTarget(current.pagination.page)}>重试影响清单</button></p>}
  </div>;
}
