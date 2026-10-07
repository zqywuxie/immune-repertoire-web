import { useLocation, useSearchParams, Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, CircleDashed, GitBranch } from "lucide-react";
import { analysisTools, analysisCategories, toolPath } from "../analysis/tools";
import { getPreparationModes, preparationInputs, preparationSource } from "../analysis/analysisPreparation";
import { assetLabel, type RequiredAsset } from "../scripthub/moduleRequirements";
import { Select } from "../../shared/components/Select";
import type { DatasetSummary } from "../../shared/api/projects";
import "./AnalysisPreparation.css";
import { UpstreamPreparation } from "./UpstreamPreparation";

type Props = { projectId:string; dataset:DatasetSummary; revision:number; active?:boolean;
  onImport:(kind:string)=>void; onFiles:(kind:string, attention:boolean)=>void };
export function AnalysisPreparation({projectId,dataset,revision,onImport,onFiles,active=true}:Props) {
  const [query,setQuery] = useSearchParams();
  const location = useLocation();
  const tool = analysisTools.find(item=>item.id===query.get("prepare_tool"));
  const modes = getPreparationModes(tool?.id || "");
  const mode = modes.find(item=>item.value===query.get("prepare_mode"))?.value || modes[0]?.value || "";
  const inputs = tool ? preparationInputs(tool,mode) : [];
  const source = tool ? preparationSource(tool,mode) : null;
  const context = new URLSearchParams({project:projectId,asset_set:dataset.name,return_to:location.pathname+location.search});
  if(mode) context.set("prepare_mode",mode);
  const configure = tool ? toolPath(tool)+"?"+context : "";
  function change(key:string,value:string) {
    setQuery(previous=>{const next=new URLSearchParams(previous);value?next.set(key,value):next.delete(key);if(key==="prepare_tool")next.delete("prepare_mode");for(const field of ["prepare_sources","prepare_q","prepare_status","prepare_page"])next.delete(field);return next;});
  }
  return <section className="analysis-preparation" aria-label="按分析目标准备数据">
    <div className="preparation-heading"><span className="preparation-icon"><GitBranch size={20} aria-hidden="true"/></span><div><h4>下一步想做什么分析？</h4><p>选择目标，查看「{dataset.name}」需要准备的输入。</p></div></div>
    <div className="preparation-selectors">
      <Select ariaLabel="目标分析" value={tool?.id || ""} options={[{value:"",label:"选择分析目标"},...analysisCategories.flatMap(category=>analysisTools.filter(item=>item.category===category.id).map(item=>({value:item.id,label:item.title})))]} onChange={value=>change("prepare_tool",value)}/>
      {!!modes.length && <Select ariaLabel="数据准备方式" value={mode} options={modes} onChange={value=>change("prepare_mode",value)}/>}
    </div>
    {query.get("prepare_tool") && !tool && <p role="status">此分析目标已不可用，请重新选择。</p>}
    {tool && <>
      <ul className="preparation-checklist">
        {inputs.map(kind=><InputStep key={kind} kind={kind} stats={dataset.kinds[kind]} configure={configure} onImport={()=>onImport(kind)} onFiles={attention=>onFiles(kind,attention)}/>)}
      </ul>
      {!inputs.length && <p className="preparation-caption">本方式直接使用前置结果；无需重复上传四类原始输入。</p>}
      {source && <UpstreamPreparation active={active} key={JSON.stringify([projectId,dataset.name,tool.id,mode])} projectId={projectId} dataset={dataset.name} source={source} revision={revision} returnPath={location.pathname+location.search}/>}
      <div className="preparation-footer"><p>继续确认输入版本、列映射、样本范围和分组，再检查是否可以运行。</p><Link className="btn btn-primary" to={configure}>继续配置并检查<ArrowRight size={16} aria-hidden="true"/></Link></div>
    </>}
  </section>;
}

function InputStep({kind,stats,configure,onImport,onFiles}:{kind:RequiredAsset;stats?:DatasetSummary["kinds"][string];configure:string;onImport:()=>void;onFiles:(attention:boolean)=>void}) {
  const count=stats?.count || 0, states=stats?.statuses || {};
  const invalid=(states.invalid || 0)+(states.failed || 0), mapping=states.needs_mapping || 0, pending=states.pending || 0;
  const valid=states.valid || 0, unknown=Math.max(states.unknown || 0,count-valid-invalid-mapping-pending);
  const hasCandidates=valid>0;
  const detail=!count ? "尚未提供" : [valid && `${valid} 个通过文件校验`,pending && `${pending} 个等待校验`,mapping && `${mapping} 个待映射`,invalid && `${invalid} 个需修正`,unknown && `${unknown} 个尚未确认`].filter(Boolean).join(" · ");
  return <li className="preparation-step">
    {hasCandidates ? <CheckCircle2 className="preparation-status" size={19} aria-hidden="true"/> : <CircleDashed className="preparation-status is-pending" size={19} aria-hidden="true"/>}
    <div className="preparation-step-copy"><strong>{assetLabel(kind)}</strong><p>{detail}</p>{hasCandidates && <small>已有通过文件校验的候选；继续配置确认实际输入。</small>}{count>1 && kind!=="pep" && <small>存在多份候选，请在分析配置中明确选择一份。</small>}</div>
    <div className="preparation-actions">{!count ? <button type="button" className="btn btn-secondary" onClick={onImport}>补充{assetLabel(kind)}</button> : <>
      <button type="button" className="btn btn-secondary" onClick={()=>onFiles(invalid+mapping+unknown>0)}>{invalid+mapping+unknown>0 ? "查看待处理文件" : "查看文件"}</button>
      {mapping>0 && <Link className="preparation-link" to={configure}>进入配置完成映射</Link>}
    </>}</div>
  </li>;
}
