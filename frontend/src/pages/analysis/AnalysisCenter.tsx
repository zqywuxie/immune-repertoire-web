import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowUpRight, Search } from "lucide-react";
import { analysisCategories, analysisTools, toolPath } from "../../features/analysis/tools";
import { useAnalysisData } from "../../features/analysis/AnalysisDataContext";
import { useApi } from "../../shared/hooks/useApi";
import { listScriptHubModules } from "../../shared/api/scriptHub";
import { listAnalysisSchemes } from "../../shared/api/unified";
import "./AnalysisCenter.css";
import { AnalysisProjectPanel } from "../../features/projects/AnalysisProjectPanel";

export function AnalysisCenter() {
  const [query,setQuery]=useSearchParams();
  const [search,setSearch]=useState("");
  const {data}=useAnalysisData();
  const modules=useApi(listScriptHubModules,[]);
  const schemes=useApi(listAnalysisSchemes,[]);
  const category=query.get("category") || "all";
  const project=query.get("project") || data?.projectId;
  const suffix=project ? `?project=${encodeURIComponent(project)}` : "";
  const visible=analysisTools.filter(tool=>(category === "all" || tool.category === category) && `${tool.title} ${tool.description} ${tool.input}`.toLowerCase().includes(search.trim().toLowerCase()));
  return <div className="analysis-center">
    <header className="analysis-center-heading"><div><p className="analysis-eyebrow">免疫组库 · 分析工作台</p><h1>分析中心</h1><p>从科研问题出发，选择一项分析。已选项目与数据可在工具间继续使用。</p></div><div className="analysis-center-actions"><Link className="btn btn-secondary" to={`/analysis/script-hub${suffix}`}>组合分析</Link><Link className="btn btn-secondary" to="/analysis/script-hub/jobs">任务与结果 <ArrowUpRight size={15}/></Link></div></header>
    <AnalysisProjectPanel />
    <div className="analysis-discovery"><label className="analysis-search"><Search size={18}/><input type="search" aria-label="搜索分析工具" placeholder="搜索分析、科研问题或输入数据…" value={search} onChange={event=>setSearch(event.target.value)}/></label><span role="status">{visible.length} 项分析工具</span></div>
    <nav className="analysis-filters" aria-label="分析分类">{[{id:"all",title:"全部分析"},...analysisCategories].map(item=><button key={item.id} aria-pressed={category===item.id} onClick={()=>setQuery(previous=>{const next=new URLSearchParams(previous); if(item.id === "all") next.delete("category"); else next.set("category",item.id); return next;})}>{item.title}</button>)}</nav>
    {(modules.status === "error" || schemes.status === "error") && <p role="alert">部分工具状态读取失败。<button className="btn btn-secondary" onClick={()=>{modules.refetch();schemes.refetch();}}>重新读取</button></p>}
    {analysisCategories.map(group=>{const tools=visible.filter(tool=>tool.category===group.id);return tools.length ? <section className="analysis-group" key={group.id}><div className="analysis-group-heading"><h2>{group.title}</h2><p>{group.description}</p></div><div className="analysis-tool-grid">{tools.map(tool=>{
      const state=tool.module ? modules.status : schemes.status;
      const found=tool.module ? modules.status === "ready" && modules.data.modules.find(item=>item.key===tool.module) : schemes.status === "ready" && schemes.data.schemes.find(item=>item.id===tool.scheme);
      const unavailable=!!found && "status" in found && found.status === "unavailable";
      const disabled=state !== "ready" || !found || unavailable;
      const status=state === "error" ? "状态读取失败" : state !== "ready" ? "正在检查环境" : !found ? "当前未配置" : unavailable ? "运行环境未启用" : "打开分析";
      return <article className="analysis-tool" key={tool.id}><h3>{tool.title}</h3><p>{tool.description}</p><dl><div><dt>输入</dt><dd>{tool.input}</dd></div><div><dt>输出</dt><dd>{tool.output}</dd></div></dl>{disabled ? <span className="analysis-tool-state">{status}</span> : <Link to={`${toolPath(tool)}${suffix}`}>{status}<ArrowUpRight size={17}/></Link>}</article>;
    })}</div></section> : null;})}
    {!visible.length && <p className="analysis-no-results">没有匹配的工具，请更换关键词或分析分类。</p>}
  </div>;
}
