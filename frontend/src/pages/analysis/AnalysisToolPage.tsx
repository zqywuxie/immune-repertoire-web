import { Link, useParams, useSearchParams } from "react-router-dom";
import { analysisTools } from "../../features/analysis/tools";
import { ScriptHubWizard } from "./ScriptHubWizard";
import { UnifiedAnalysis } from "./UnifiedAnalysis";
export function AnalysisToolPage() {
  const {toolId}=useParams();
  const [query]=useSearchParams();
  const project=query.get("project");
  const tool=analysisTools.find(item=>item.id===toolId);
  if(!tool) return <section><h1>未找到该分析工具</h1><Link to="/analysis/center">返回分析中心</Link></section>;
  return <><Link className="btn btn-secondary" to={`/analysis/center?category=${tool.category}${project ? `&project=${encodeURIComponent(project)}` : ""}`}>返回{({overview:"组库概览与多样性",clones:"克隆特征与共享",genes:"V/J 基因特征",bcr:"BCR 与体细胞突变",annotation:"注释与生成概率",transcriptome:"转录组与通路",modeling:"降维与建模"})[tool.category]}</Link>
    {["vj-difference","umapin"].includes(tool.id) && <p>尚未生成特征缓存？<Link to={`/analysis/tools/sharing${project ? `?project=${encodeURIComponent(project)}` : ""}`}>进入 CDR3 共享分析</Link>，完成后返回本工具选择缓存。</p>}
    {tool.scheme ? <UnifiedAnalysis key={tool.id} fixedScheme={tool.scheme} title={tool.title} description={tool.description}/> : <ScriptHubWizard key={tool.id} tool={tool}/>}</>;
}
