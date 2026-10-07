import {useEffect,useState} from "react";
import {useSearchParams} from "react-router-dom";
import {Search,RotateCcw} from "lucide-react";
import {Select} from "../../shared/components/Select";
import type {ResultFacets} from "../../shared/api/projects";
import {analysisLabel} from "../../shared/utils/analysisLabels";
import "./ProjectResultFilters.css";

export function ProjectResultFilters({facets}:{facets?:ResultFacets}) {
  const [query,setQuery]=useSearchParams();
  const dataset=query.get("result_dataset") || "";
  const unscoped=query.get("result_unscoped")==="1";
  const type=query.get("result_type") || "";
  const job=query.get("result_job") || "";
  const [jobDraft,setJobDraft]=useState(job);
  useEffect(()=>setJobDraft(job),[job]);
  const datasets=[...(facets?.datasets || [])];
  if(dataset && !datasets.some(item=>item.name===dataset))datasets.push({name:dataset,count:0});
  const types=[...(facets?.analysis_types || [])];
  if(type && !types.some(item=>item.name===type))types.push({name:type,count:0});
  function apply(values:Record<string,string>){setQuery(previous=>{const next=new URLSearchParams(previous);for(const [key,value]of Object.entries(values))value?next.set(key,value):next.delete(key);next.delete("result_page");return next;});}
  function clear(){setJobDraft("");apply({result_dataset:"",result_unscoped:"",result_type:"",result_job:""});}
  return <section className="project-result-filters" aria-label="分析结果筛选">
    <div className="project-result-filter-fields">
      <label className="field-label">结果数据集<Select ariaLabel="结果数据集" value={unscoped?"unknown":dataset?`dataset:${dataset}`:""}
        options={[{value:"",label:"全部数据集"},...datasets.map(item=>({value:`dataset:${item.name}`,label:`${item.name}（${item.count}）`})),{value:"unknown",label:`未记录数据集（${facets?.unscoped_count ?? "待核对"}）`}]}
        onChange={value=>apply({result_dataset:value.startsWith("dataset:")?value.slice(8):"",result_unscoped:value==="unknown"?"1":""})}/></label>
      <label className="field-label">分析类型<Select ariaLabel="结果分析类型" value={type} options={[{value:"",label:"全部分析类型"},...types.map(item=>({value:item.name,label:`${analysisLabel(item.name)}（${item.count}）`}))]}
        onChange={value=>apply({result_type:value})}/></label>
      <form className="project-result-job-filter" onSubmit={event=>{event.preventDefault();const value=jobDraft.trim();setJobDraft(value);apply({result_job:value});}}>
        <label className="field-label">来源任务标识<input className="input" aria-label="来源任务标识" value={jobDraft} maxLength={255} placeholder="填写完整任务标识" onChange={event=>setJobDraft(event.target.value)}/></label>
        <button className="btn btn-secondary" type="submit"><Search size={16}/>查询任务</button>
      </form>
    </div>
    <div className="project-result-filter-summary"><span>{dataset?`数据集：${dataset}`:unscoped?"范围：未记录数据集的结果":"范围：项目全部数据集"}{type?` · ${analysisLabel(type)}`:""}{job?` · 任务：${job}`:""}</span>
      {(dataset || unscoped || type || job || jobDraft) && <button className="btn btn-ghost" onClick={clear}><RotateCcw size={14}/>清除结果筛选</button>}
    </div>
    {jobDraft!==job && <p className="data-muted" role="status">任务标识尚未应用，请点击“查询任务”或按回车。</p>}
  </section>;
}
