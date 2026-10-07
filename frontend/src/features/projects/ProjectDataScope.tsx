import { Layers } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { listProjectDatasets } from "../../shared/api/projects";
import { useApi } from "../../shared/hooks/useApi";
import { Select } from "../../shared/components/Select";
import { DataReadError } from "../assets/DataReadError";

export function ProjectDataScope({projectId,revision}:{projectId:string;revision:number}) {
  const [query,setQuery]=useSearchParams();
  const current=query.get("asset_set") || "";
  const response=useApi(()=>listProjectDatasets(projectId),[projectId,revision]);
  const sets=response.status==="ready" ? response.data.datasets : [];
  const selected=sets.find(item=>item.name===current);
  function select(name:string) {
    if(name===current)return;
    setQuery(previous=>{
      const next=new URLSearchParams(previous);name?next.set("asset_set",name):next.delete("asset_set");
      for(const key of ["sample_page","file_page","asset","group_spec","group_page"])next.delete(key);
      return next;
    });
  }
  return <section className="data-project-scope-picker" aria-label="项目数据范围">
    <div className="data-scope-heading"><span className="data-scope-icon"><Layers size={20} aria-hidden="true"/></span><div><strong>数据范围</strong><p>在此切换样本与分组的所属数据集</p></div></div>
    <div className="data-scope-control"><Select value={current} ariaLabel="切换当前数据集" disabled={response.status!=="ready"}
      options={[...(current&&!selected?[{value:current,label:current}]:[]),{value:"",label:"全部数据集"},...sets.map(item=>({value:item.name,label:(item.display_name || item.name)+(item.archived ? "（已归档）" : "")}))]}
      onChange={select}/><span role="status">{response.status==="error"?"数据集数量暂未读取":response.status!=="ready"?"正在读取数据范围…":current?selected?`${selected.input_count} 个当前输入文件`:"此范围暂无当前输入文件":`${sets.length} 个数据集 · 各数据集同编号分别管理`}</span></div>
    {response.status==="error" && <DataReadError title="数据范围暂时无法读取" message={response.error} onRetry={response.refetch} retryLabel="重新读取数据范围"/>}
  </section>;
}
