import type {ProjectAsset,JobSummary} from "../../shared/types/domain";
import {JobConfigurationPanel} from "../jobs/JobConfigurationPanel";
import {objectValue} from "../jobs/jobConfiguration";

export function AssetResultProvenance({asset,projectId}:{asset:ProjectAsset;projectId:string}){
 const metadata=objectValue(asset.metadata),nested=objectValue(metadata.metadata);
 const saved={...nested,...metadata};
 const id=typeof saved.job_id==="string"?saved.job_id.trim():"";
 const query=new URLSearchParams({project:projectId,job:id});
 const job:JobSummary={id:asset.id,job_type:"script-hub",progress:100,project_id:projectId,module:String(saved.analysis_type || ""),status:"completed",
  payload:{...saved,_task_name:asset.original_name || "保存的分析结果"}};
 return <section className="asset-result-provenance" aria-label="结果来源">
  {id ? <a className="btn btn-primary" href={"/analysis/script-hub/jobs?"+query}>查看来源任务与输入</a> : <p className="data-muted">此结果未保存来源任务标识。</p>}
  <details><summary>结果保存的输入与分组</summary><JobConfigurationPanel job={job}/></details>
 </section>;
}
