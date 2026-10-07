import { assetPath } from "../../features/assets/assetSets";
import { AnalysisSelectionNotice } from "../../features/analysis/AnalysisSelectionNotice";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useApi } from "../../shared/hooks/useApi";
import { useJobResult } from "../../shared/hooks/useJobResult";
import { ProjectPicker } from "../../features/projects/ProjectPicker";
import { getAnalysisInputFile, listDataFiles, type UploadedFile } from "../../shared/api/files";
import { getAnalysisScheme, listAnalysisSchemes, unifiedPayload } from "../../shared/api/unified";
import { submitJob } from "../../shared/api/jobs";
import { PageHeader } from "../../shared/components/PageHeader";
import { ResultViewer } from "../../features/results/ResultViewer";

import { useAnalysisData } from "../../features/analysis/AnalysisDataContext";
import { InputAssetNotice, inputAssetKind, inputAssetReturnPath, useInputAssetIntent } from "../../features/analysis/InputAssetIntent";

const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string,unknown> : {};
export function UnifiedAnalysis({fixedScheme,title,description}:{fixedScheme?:string;title?:string;description?:string} = {}) {
  const [query, setQuery] = useSearchParams();
  const {data:sharedData,setData:shareData,selectionState="ready"}=useAnalysisData();
  const [project, setProject] = useState(query.get("project") || sharedData?.projectId || "");
  const dataset=query.has("asset_set")?query.get("asset_set") || "":sharedData?.projectId===project?sharedData.assetSetName:"";
  const requestedId=query.get("input_asset") || "";
  const intent=useInputAssetIntent(project,dataset,requestedId);
  const requestedAsset=intent.status==="ready"?intent.data:null;
  const continuing=query.get("reuse_inputs")==="1" && sharedData?.projectId===project && sharedData.assetSetName===dataset;
  const restoringSelection=continuing && selectionState!=="ready";
  const selectedProfile=continuing && sharedData?.selectionExplicit ? sharedData.inputAssets?.find(asset=>inputAssetKind(asset)==="profile" && assetPath(asset)===sharedData.profilePath) : undefined;
  useEffect(()=>{
    if(restoringSelection || !selectedProfile || (requestedId && (!requestedAsset || inputAssetKind(requestedAsset)==="profile")))return;
    setQuery(previous=>{const next=new URLSearchParams(previous);next.set("input_asset",selectedProfile.id);return next;},{replace:true});
  },[restoringSelection,selectedProfile?.id,requestedId,requestedAsset,setQuery]);
  const requestedFile=useApi(async()=>{
    if(!requestedAsset || restoringSelection)return null;
    if(inputAssetKind(requestedAsset)!=="profile"){
      if(selectedProfile)return null;
      throw new Error("该工具需要样本指标表，请选择本次使用的指标表版本。");
    }
    return getAnalysisInputFile(project,requestedAsset.id,dataset);
  },[project,dataset,requestedAsset?.id,restoringSelection,selectedProfile?.id]);
  const appliedIntent=useRef("");
  const inputPending=restoringSelection || Boolean(requestedId && (intent.status!=="ready" || !requestedAsset || requestedFile.status!=="ready" || !requestedFile.data));
  const [file, setFile] = useState<UploadedFile | null>(null);
  const [mode, setMode] = useState<"scheme" | "custom">("scheme");
  const [schemeId, setSchemeId] = useState(fixedScheme || "");
  const [mapping, setMapping] = useState<Record<string,string>>({});
  const [fields, setFields] = useState<string[]>([]);
  const [sample, setSample] = useState("");
  const [baseline, setBaseline] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const schemes = useApi(listAnalysisSchemes, []);
  const detail = useApi(() => schemeId ? getAnalysisScheme(schemeId) : Promise.resolve(null), [schemeId]);
  const savedFiles = useApi(() => project ? listDataFiles(project,dataset) : Promise.resolve({ files: [] }), [project,dataset]);
  const scheme = detail.status === "ready" && detail.data?.id === schemeId ? detail.data : null;
  const task = useJobResult(query.get("job"));
  const locked = busy || !!task.jobId && !task.error && !["completed","failed","cancelled","interrupted"].includes(task.status);
  function selectFile(next: UploadedFile | null) { setFile(next); setMapping({}); setFields([]); setSample(""); setBaseline(""); setError(""); }
  useEffect(()=>{
    if(!requestedId){appliedIntent.current="";return;}
    if(requestedAsset && requestedFile.status==="ready" && requestedFile.data && appliedIntent.current!==requestedFile.data.id){
      appliedIntent.current=requestedFile.data.id;selectFile(requestedFile.data);
      const same=sharedData?.projectId===project && sharedData.assetSetName===dataset;
      const path=assetPath(requestedAsset);
      if(!same || sharedData?.profilePath!==path || !sharedData.inputAssets?.some(asset=>asset.id===requestedAsset.id)){
        shareData({...(same && sharedData?sharedData:{projectId:project,assetSetName:dataset,pepPaths:[],transcriptomePath:"",deconvolutionPath:""}),profilePath:path,inputAssets:[...(same?sharedData?.inputAssets || []:[]),requestedAsset],selectionExplicit:true});
      }
    }
  },[requestedId,requestedAsset,requestedFile.status,requestedFile.status==="ready"?requestedFile.data:null,sharedData,shareData,project,dataset]);
  const schemeFields = [...(scheme?.required_fields || []), ...(scheme?.optional_fields || [])];
  const effectiveMapping = Object.fromEntries(schemeFields.map(field => {
    const hints = [field.field, ...(field.mapping_hints || [])].map(name => name.toLowerCase());
    return [field.field, mapping[field.field] ?? file?.columns.find(column => hints.includes(column.toLowerCase())) ?? ""];
  }));
  async function run() {
    setError("");
    try {
      if (!project) throw new Error("请选择项目。");
      const request = unifiedPayload(file, mode, scheme, effectiveMapping, fields, sample, baseline.trim());
      setBusy(true);
      const submitted = await submitJob({ ...request, payload:{...request.payload,asset_set:dataset}, projectId: project });
      if (!submitted.success || !submitted.job_id) throw new Error("任务提交失败，请重试。");
      setQuery(previous=>{const next=new URLSearchParams(previous);next.set("job",submitted.job_id!);next.set("project",project);return next;});
    } catch (error) { setError(error instanceof Error ? error.message : "分析提交失败"); }
    finally { setBusy(false); }
  }
  const envelope = object(task.result?.result);
  const response = object(envelope.data || envelope);
  const result = object(response.results);
  const tables = Array.isArray(result.tables) ? result.tables : [];
  const charts = Array.isArray(result.charts) ? result.charts : [];
  return <>
    <PageHeader title={title || "自定义指标与方案"} subtitle={description || "选择真实数据与分析方案，核对字段后执行；也可自行选择指标进行分析。"} />
    {requestedId && <InputAssetNotice asset={requestedAsset} loading={intent.status==="loading" || intent.status==="idle" || requestedFile.status==="loading"} error={intent.status==="error"?intent.error:requestedFile.status==="error"?requestedFile.error:null} returnPath={inputAssetReturnPath(project,requestedAsset,query.get("return_to") || "")} onRetry={()=>{intent.refetch();requestedFile.refetch();}} onClear={()=>{if(continuing && sharedData)shareData({...sharedData,profilePath:"",selectionExplicit:true});setQuery(previous=>{const next=new URLSearchParams(previous);next.delete("input_asset");return next;});selectFile(null);}}/>}
    {continuing && <AnalysisSelectionNotice projectId={project} dataset={dataset} onClear={()=>{
      shareData({projectId:project,assetSetName:dataset,pepPaths:[],profilePath:"",transcriptomePath:"",inputAssets:[],selectionExplicit:false});
      setQuery(previous=>{const next=new URLSearchParams(previous);next.delete("input_asset");return next;});selectFile(null);
    }}/>}
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,380px),1fr))", gap: 24, alignItems: "start" }}>
      <section style={{ padding: 24, background: "var(--bg-elevated)", border: "1px solid var(--separator)", borderRadius: 10 }}>
        <fieldset disabled={locked} style={{ border: 0, minWidth: 0, display: "grid", gap: 18 }}>
          <legend style={{ fontWeight: 600, marginBottom: 18 }}>1 · 选择数据</legend>
          <ProjectPicker value={project} disabled={locked} onChange={value => { setProject(value); selectFile(null); if(sharedData?.projectId !== value) shareData({projectId:value,assetSetName:"",pepPaths:[],profilePath:"",transcriptomePath:""}); setQuery(previous=>{const next=new URLSearchParams(previous);next.set("project",value);next.delete("job");next.delete("asset_set");next.delete("input_asset");next.delete("return_to");return next;},{replace:true}); }} />
          <p className="text-muted">复用本项目已校验的样本指标表。<Link to="/analysis/center">前往分析中心上传或更新数据</Link></p>
          <label className="field-label">选择本项目已上传文件<select className="select" disabled={!project || locked} value={file?.id || ""} onChange={event => {const next=savedFiles.status === "ready" ? savedFiles.data.files.find(item=>item.id===event.target.value) || null : null;selectFile(null);setQuery(previous=>{const query=new URLSearchParams(previous);if(next?.asset_id)query.set("input_asset",next.asset_id);else query.delete("input_asset");return query;});if(next && !next.asset_id)selectFile(next);}}><option value="">请选择文件</option>{file && !(savedFiles.status === "ready" && savedFiles.data.files.some(item => item.id === file.id)) && <option value={file.id}>{file.name}</option>}{savedFiles.status === "ready" && savedFiles.data.files.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
          {savedFiles.status === "error" && <p role="alert">文件列表读取失败：{savedFiles.error}</p>}
          <p style={{ color: "var(--text-secondary)", fontSize: 13 }}>{file ? `${file.name} · ${file.row_count} 行 · ${file.columns.length} 列` : "请先在分析中心上传并完成校验，每次任务分析一份数据表。"}</p>
          <h3>2 · 配置分析</h3>
          {!fixedScheme && <label className="field-label">分析方式<select className="select" value={mode} onChange={event => setMode(event.target.value as typeof mode)}><option value="scheme">预设分析方案</option><option value="custom">自定义指标</option></select></label>}
          {mode === "scheme" ? <>
            {!fixedScheme && <label className="field-label">分析方案<select className="select" value={schemeId} onChange={event => { setSchemeId(event.target.value); setMapping({}); }}><option value="">请选择方案</option>{schemes.status === "ready" && schemes.data.schemes.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
            {schemes.status === "error" && <p role="alert">方案加载失败：{schemes.error}</p>}{detail.status === "error" && <p role="alert">字段要求加载失败：{detail.error}</p>}
            {scheme && <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>{scheme.description}</p>}
            {file && schemeFields.map(field => <label className="field-label" key={field.field}>{field.display_name || field.field} · {scheme?.required_fields?.some(item => item.field === field.field) ? "必填" : "可选"}<select className="select" value={effectiveMapping[field.field]} onChange={event => setMapping(previous => ({ ...previous, [field.field]: event.target.value }))}><option value="">不映射</option>{file.columns.map(column => <option key={column}>{column}</option>)}</select></label>)}
          </> : <>
            <label className="field-label">样本标识列<select className="select" value={sample} onChange={event => { setSample(event.target.value); setFields(previous => previous.filter(field => field !== event.target.value)); }}><option value="">请选择样本列</option>{file?.columns.map(column => <option key={column}>{column}</option>)}</select></label>
            <fieldset style={{ border: "1px solid var(--separator)", borderRadius: 6, padding: 12 }}><legend>选择指标列</legend><div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>{file?.columns.filter(column => column !== sample).map(column => <label key={column} style={{ display: "flex", alignItems: "center", gap: 6 }}><input type="checkbox" checked={fields.includes(column)} onChange={event => setFields(previous => event.target.checked ? [...previous,column] : previous.filter(field => field !== column))} />{column}</label>)}</div></fieldset>
          </>}
          <label className="field-label">基准样本（可选）<input className="input" value={baseline} onChange={event => setBaseline(event.target.value)} placeholder="填写数据中的完整样本名称" /></label>
          <button className="btn btn-primary" onClick={run} disabled={!project || !file || locked || inputPending || mode === "scheme" && !scheme}>开始分析</button>
        </fieldset>
        {busy && <p role="status">正在上传或提交，请稍候…</p>}{error && <p role="alert" style={{ color: "var(--danger)", marginTop: 16 }}>{error}</p>}
      </section>
      <section style={{ minWidth: 0 }}><h2>3 · 分析结果</h2>
        {!task.jobId && <p style={{ marginTop: 16, color: "var(--text-secondary)" }}>提交后在此查看实际生成的结果。</p>}
        {task.jobId && <div style={{ margin: "16px 0" }}><p role="status">{({ queued:"正在排队",running:"正在分析",completed:"分析完成",failed:"分析失败",cancelled:"任务已取消",interrupted:"任务已中断",unknown:"状态读取失败" } as Record<string,string>)[task.status] || task.status}</p><Link to="/analysis/script-hub/jobs">查看任务列表</Link><p style={{ fontSize: 12, color: "var(--text-secondary)" }}>保留当前页面地址，刷新后可继续查看结果。</p></div>}
        {task.error && <div role="alert"><p>{task.error}</p><button className="btn btn-secondary" onClick={task.retry}>重新读取任务</button></div>}
        {response.success === false && <p role="alert">{String(response.error || response.message || "分析失败")}</p>}
        {tables.map((table,index) => <UnifiedTable key={index} table={object(table)} />)}
        {charts.map((raw,index) => { const chart=object(raw); const image=chart.image || chart.base64; return typeof image === "string" ? <figure key={index}><figcaption>{String(chart.title || "分析图表")}</figcaption><img alt={String(chart.title || "分析图表")} src={image.startsWith("data:image/") ? image : `data:image/png;base64,${image}`} style={{ maxWidth: "100%" }} /><a className="btn btn-secondary" download={`analysis-chart-${index + 1}.png`} href={image.startsWith("data:image/") ? image : `data:image/png;base64,${image}`}>下载 PNG</a></figure> : null; })}
        {!!task.result?.outputs?.length && <ResultViewer outputs={task.result.outputs} />}
        {task.result && <a className="btn btn-secondary" download="analysis-results.json" href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(result,null,2))}`}>下载完整结果 JSON</a>}
        {task.result && !tables.length && !charts.length && !task.result.outputs?.length && <p>本次分析未返回可展示的表格或图表，可下载完整结果查看。</p>}
      </section>
    </div>
  </>;
}

function UnifiedTable({ table }: { table: Record<string,unknown> }) {
  const rows = Array.isArray(table.data) ? table.data.map(object) : [];
  const headers = Array.isArray(table.headers) ? table.headers.map(String) : [...new Set(rows.flatMap(row => Object.keys(row)))];
  const title = String(table.title || "分析结果");
  const csv = [headers,...rows.map(row => headers.map(key => row[key] ?? ""))].map(row => row.map(value => `"${String(value).replace(/"/g,'""')}"`).join(",")).join("\r\n");
  return <article style={{ padding: 20, background: "var(--bg-elevated)", border: "1px solid var(--separator)", borderRadius: 8, marginBottom: 20 }}><h3>{title}</h3><a download={`${title}.csv`} href={`data:text/csv;charset=utf-8,${encodeURIComponent('\ufeff'+csv)}`}>下载 CSV</a><div style={{ overflowX: "auto" }}><table style={{ width:"100%",textAlign:"left",borderCollapse:"collapse" }}><thead><tr>{headers.map(header => <th key={header} style={{ padding: 8 }}>{header}</th>)}</tr></thead><tbody>{rows.map((row,index) => <tr key={index}>{headers.map(header => <td key={header} style={{ padding:8,borderTop:"1px solid var(--separator)" }}>{String(row[header] ?? "—")}</td>)}</tr>)}</tbody></table></div></article>;
}
