import {useEffect, useRef, useState} from "react";
import {Download, Check, RotateCcw} from "lucide-react";
import {Sheet} from "../../shared/components/Sheet";
import {downloadSamples, type ListSamplesParams} from "../../shared/api/samples";
import {sampleFieldLabels, speciesLabel, healthyLabel, pairedLabel} from "./sampleDisplay";
import "./SampleExport.css";

export type SampleExportScope = {filters:ListSamplesParams; projectName:string; count:number; recordIds?:string[]};
const labels:Record<string,string> = {...sampleFieldLabels,q:"搜索",sample_id:"样本编号",input_sample_id:"核对的输入编号",project_name:"项目名称"};
function labelValue(key:string,value:string) {
  if(key === "spices") return value.split(",").map(speciesLabel).join("、");
  if(key === "is_healthy") return healthyLabel(value);
  if(key === "is_pe") return pairedLabel(value);
  return value;
}
export function SampleExportSheet({scope,onClose}:{scope:SampleExportScope;onClose:()=>void}) {
  const [format,setFormat]=useState<"xlsx"|"csv">("xlsx");
  const [source,setSource]=useState(false);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [download,setDownload]=useState<{url:string;name:string;count:string|null}|null>(null);
  const controller=useRef<AbortController|null>(null);
  const pending=useRef(false);
  useEffect(()=>()=>{controller.current?.abort();},[]);
  useEffect(()=>()=>{if(download) URL.revokeObjectURL(download.url);},[download]);
  const active=Object.entries(scope.filters).filter(([key,value])=>!["project_id","asset_set","page","page_size"].includes(key) && value !== undefined && value !== "");
  function trigger(url:string,name:string) {const link=document.createElement("a");link.href=url;link.download=name;link.click();}
  async function start() {
    if(pending.current) return;
    pending.current=true;setBusy(true);setError("");setDownload(null);
    const request=new AbortController();controller.current=request;
    try {
      const result=scope.recordIds
        ? await downloadSamples(scope.filters,format,source,request.signal,scope.recordIds)
        : await downloadSamples(scope.filters,format,source,request.signal);
      if(request.signal.aborted) return;
      const file={url:URL.createObjectURL(result.blob),name:`样本登记.${format}`,count:result.count};
      setDownload(file);trigger(file.url,file.name);
    } catch(reason) {if(!request.signal.aborted) setError(reason instanceof Error?reason.message:"导出未完成，请重试。");}
    finally {pending.current=false;if(!request.signal.aborted) setBusy(false);}
  }
  return <Sheet open onClose={onClose} title="导出样本登记">
    <div className="sample-export-flow">
      <section className="sample-export-scope" aria-label="本次导出范围"><span className="sample-export-eyebrow">{scope.recordIds?"所选登记":"已应用的筛选"}</span>
        <h3>{scope.projectName}</h3><p>数据集：{scope.filters.asset_set || "全部数据集"}</p>
        <strong>{scope.count.toLocaleString()} 条登记<span>{scope.recordIds?" · 仅导出勾选项，包含跨页选择":" · 包含全部匹配页"}</span></strong>
        {!!active.length && <dl>{active.map(([key,value])=><div key={key}><dt>{labels[key] || key}</dt><dd>{labelValue(key,String(value))}</dd></div>)}</dl>}
        <p className="data-muted">{scope.recordIds?"勾选范围按打开窗口时固定；已移除或不再符合筛选的记录会提示重新选择。":"范围按打开窗口时的筛选固定；记录内容以生成文件时为准。"}</p>
      </section>
      <fieldset className="sample-export-formats" disabled={busy}><legend>下载格式</legend>
        <label className={format === "xlsx"?"is-selected":""}><input type="radio" name="sample-export-format" checked={format==="xlsx"} onChange={()=>{setFormat("xlsx");setDownload(null);setError("");}}/><span><strong>表格文件（推荐）</strong><small>保留 001 等文本编号，可直接查看</small></span></label>
        <label className={format === "csv"?"is-selected":""}><input type="radio" name="sample-export-format" checked={format==="csv"} onChange={()=>{setFormat("csv");setDownload(null);setError("");}}/><span><strong>逗号分隔文件</strong><small>适合脚本读取，采用中文列名</small></span></label>
      </fieldset>
      <label className="sample-export-source"><input type="checkbox" checked={source} disabled={busy} onChange={event=>{setSource(event.target.checked);setDownload(null);setError("");}}/><span>附带来源字段<small>增加登记、项目、来源文件标识和原始补充信息</small></span></label>
      {format === "csv" && <p className="data-muted">使用表格软件打开时，请将编号列按文本导入，避免前导零被自动转换。</p>}
      {busy && <p role="status" className="sample-export-status">正在整理并下载登记文件…</p>}
      {error && <div role="alert" className="data-error">{error}<p>本次范围与格式已保留。</p></div>}
      {download && <p role="status" className="sample-export-status"><Check size={18}/>已生成{download.count !== null ? ` ${download.count} 条登记的` : ""}文件，并发起下载。</p>}
      <div className="sample-export-actions"><button className="btn btn-secondary" onClick={onClose}>{busy?"关闭下载窗口":"关闭"}</button>
        {download ? <button className="btn btn-primary" onClick={()=>trigger(download.url,download.name)}><Download size={16}/>再次下载文件</button> : <button className="btn btn-primary" disabled={busy} onClick={start}>{error?<RotateCcw size={16}/>:<Download size={16}/>} {busy?"正在准备…":error?"重新导出":"生成并下载"}</button>}
      </div>
    </div>
  </Sheet>;
}
