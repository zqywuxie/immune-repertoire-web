import {projectAssetDetailPath} from "../assets/assetSets";
import "../assets/AssetLineage.css";
import { useState } from "react";
import type { JobSummary } from "../../shared/types/domain";
import { analysisLabel } from "../../shared/utils/analysisLabels";
import { statusLabels } from "../../shared/components/StatusBadge";
import { configurationRows, jobInputs, jobSettings, objectValue, taskName, type ConfigRow, type RecordValue } from "./jobConfiguration";
import "./JobConfigurationPanel.css";

export function JobConfigurationPanel({job}: {job: JobSummary}) {
 const payload=objectValue(job.payload),settings=jobSettings(payload);
 const projectValue=job.project_id || payload.project_id || payload._project_id;
 const project=typeof projectValue==="string"?projectValue:"";
 const projectName=payload.project_name;
 const items=Array.isArray(payload.items)?payload.items.map(objectValue):[];
 return <section className="job-configuration" aria-label="任务配置摘要">
  <dl className="job-configuration-context">
   <Fact label="任务名称">{taskName(job)}</Fact><Fact label="分析模块">{analysisLabel(job.module)}</Fact>
   <Fact label="所属项目">{typeof projectName==="string"&&projectName ? projectName : project ? "项目已记录" : "未记录项目"}{project&&<a href={"/management/projects/"+encodeURIComponent(String(project))}>查看项目</a>}</Fact>
   <Fact label="数据集">{typeof settings.asset_set==="string"&&settings.asset_set ? settings.asset_set : "未记录数据集"}</Fact>
  </dl>
  <p className="job-configuration-hint">这里展示任务保存的输入与条件；历史记录缺少的参数不会用当前默认值补齐。</p>
  {!items.length && <ConfigurationBlock settings={settings} payload={payload} project={project}/>}
  {!!items.length && <section><h4>批次计划（{items.length} 项）</h4><ol className="job-configuration-plan">{items.map((item,index)=>{
   const depends=Array.isArray(item.depends_on)?item.depends_on:[];
   const childId=typeof item.job_id==="string"?item.job_id:"";
   return <li key={index}><div className="job-configuration-plan-heading"><strong>{analysisLabel(String(item.module||""))}</strong><span>{typeof item.status==="string" ? statusLabels[item.status] || "未识别状态" : "未记录状态"}</span></div>
    {depends.length>0&&<p>依赖：{depends.map(value=>typeof value==="number"&&Number.isInteger(value)&&value>=0&&value<items.length?"第 "+(value+1)+" 项":"未识别的依赖记录").join("、")}</p>}
    {typeof item.upstream_from==="number"&&item.upstream_from>=0&&item.upstream_from<items.length&&<p>使用第 {item.upstream_from+1} 项的分析产物</p>}
    {childId&&<a href={"/analysis/script-hub/jobs?job="+encodeURIComponent(childId)}>查看子任务</a>}
    <details><summary>查看本项保存的条件</summary><ConfigurationBlock payload={objectValue(item.payload)} settings={jobSettings(objectValue(item.payload))} project={project}/></details>
   </li>;
  })}</ol></section>}
  <details className="job-configuration-raw"><summary>完整技术参数</summary>
   {Object.keys(payload).length ? <pre tabIndex={0}>{JSON.stringify(payload,null,2)}</pre> : <p>尚未记录分析参数。</p>}
  </details>
 </section>;
}
function ConfigurationBlock({payload,settings,project}:{payload:RecordValue;settings:RecordValue;project:string}){
 const inputs=jobInputs(settings),scope=configurationRows(settings,true),conditions=configurationRows(settings,false);
 const upstream=objectValue(payload.upstream_input);
 const source=upstream.source_job_id || settings.source_job_id;
 const sourceId=typeof source==="string"?source:"";
 const artifactValue=upstream.artifact_id || settings.upstream_artifact_id;
 const artifact=typeof artifactValue==="string"?artifactValue:"";
 const module=typeof upstream.module==="string" ? upstream.module:"";
 return <div className="job-configuration-block">
  <section><h4>输入与来源</h4>{inputs.length ? <ul className="job-configuration-inputs">{inputs.map((input,index)=><li key={index}><strong>{input.label}</strong><div className="job-input-origin"><span>{input.name}</span>{input.version&&<small>保存的版本：{input.version}</small>}{input.id&&project ? <a href={projectAssetDetailPath(project,input.id,input.dataset || String(settings.asset_set || ""))}>查看执行时的文件</a> : <small>历史记录未保存可定位的资产标识</small>}</div></li>)}</ul> : <p className="job-configuration-hint">未记录可展示的输入文件；如有历史执行参数，可在完整技术参数中核对。</p>}
   {(sourceId||artifact)&&<div className="job-configuration-upstream"><strong>使用前置分析产物</strong>{module&&<span>{analysisLabel(module)}</span>}{sourceId ? <a href={"/analysis/script-hub/jobs?job="+encodeURIComponent(sourceId)}>查看来源任务</a> : <p>未记录来源任务</p>}<p className="job-configuration-hint">来源信息反映本次保存的引用，不代表文件当前仍可用。</p></div>}
  </section>
  <SavedGroup snapshot={objectValue(settings.group_spec_snapshot)} project={project}/>
  {scope.length>0&&<section><h4>样本与分组</h4><Rows rows={scope}/></section>}
  {conditions.length>0&&<section><h4>分析条件</h4><Rows rows={conditions}/></section>}
  {!scope.length&&!conditions.length&&<p className="job-configuration-hint">未记录可展示的分析条件，其他字段保留在完整技术参数中。</p>}
 </div>;
}
function Rows({rows}:{rows:ConfigRow[]}){
 return <dl className="job-configuration-values">{rows.map((row,index)=><Fact key={index} label={row.label}><Value value={row.value} options={row.options}/></Fact>)}</dl>;
}
function Value({value,options}:{value:unknown;options?:Record<string,string>}){
 const [expanded,setExpanded]=useState(false);
 if(typeof value==="boolean")return <>{value?"是":"否"}</>;
 if(Array.isArray(value)){
  if(!value.length)return <>未指定名单</>;
  const values=expanded?value:value.slice(0,8);
  return <div className="job-configuration-list"><span>已记录 {value.length} 项</span><div className="job-configuration-list-values">{values.map((item,index)=><div key={index}><Value value={item} options={options}/></div>)}</div>{value.length>8&&<button type="button" className="btn btn-secondary" aria-expanded={expanded} onClick={()=>setExpanded(previous=>!previous)}>{expanded?"收起完整名单":"查看完整名单"}</button>}</div>;
 }
 if(value&&typeof value==="object"){
  const record=objectValue(value);
  if("group1" in record&&"group2" in record)return <span>前组：{String(record.group1)}；后组：{String(record.group2)}</span>;
  return <dl className="job-configuration-nested">{Object.entries(record).map(([key,item])=><Fact key={key} label={Object.hasOwn(mappingLabels,key)?mappingLabels[key]:key}><Value value={item}/></Fact>)}</dl>;
 }
 if(value===null||value===undefined||value==="")return <>未记录</>;
 const text=String(value);return <>{options&&Object.hasOwn(options,text)?options[text]:text}</>;
}
const mappingLabels:Record<string,string>={sample_column:"样本列",sample_id:"样本标识",sample_key:"样本标识",group:"分组",batch:"批次",cdr3_column:"CDR3 列",copy_column:"拷贝数列",sample:"样本",gene:"基因",chain:"受体链"};
function Fact({label,children}:{label:string;children:React.ReactNode}){return <div><dt>{label}</dt><dd>{children}</dd></div>;}

function SavedGroup({snapshot,project}:{snapshot:RecordValue;project:string}){
 if(!Object.keys(snapshot).length)return null;
 const definition=objectValue(snapshot.spec_json),name=typeof snapshot.name==="string"?snapshot.name:"未记录名称";
 const asset=typeof snapshot.asset_id==="string"?snapshot.asset_id:"",source=typeof definition.source_asset_id==="string"?definition.source_asset_id:"";
 const snapshotProject=typeof snapshot.project_id==="string"?snapshot.project_id:project;
 return <section className="job-saved-group" aria-label="执行时的分组方案"><h4>执行时的分组方案 · {name}</h4>
  <p className="job-configuration-hint">以下为任务保存的方案快照；后续修改当前方案不会改变这份记录。</p>
  <dl className="job-configuration-values"><Fact label="保存的分组顺序"><Value value={snapshot.group_order || definition.groups}/></Fact>
   <Fact label="分组字段"><Value value={definition.group_field}/></Fact><Fact label="方案版本"><Value value={snapshot.content_version}/></Fact></dl>
  {project&&snapshotProject===project&&asset&&<a className="btn btn-secondary" href={projectAssetDetailPath(project,asset,"")}>查看方案版本文件</a>}
  {project&&snapshotProject===project&&source&&<a className="btn btn-secondary" href={projectAssetDetailPath(project,source,String(definition.asset_set || ""))}>查看分组来源文件</a>}
 </section>;
}
