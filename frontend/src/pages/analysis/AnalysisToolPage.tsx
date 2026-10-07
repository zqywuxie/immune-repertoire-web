import {Link, useParams, useSearchParams} from "react-router-dom";
import {projectReturnPath} from "../../features/assets/assetSets";
import {analysisTools} from "../../features/analysis/tools";
import {ScriptHubWizard} from "./ScriptHubWizard";
import {UnifiedAnalysis} from "./UnifiedAnalysis";
import "../../features/scripthub/modules/SourceSelection.css";

export function AnalysisToolPage() {
  const {toolId} = useParams();
  const [query] = useSearchParams();
  const tool = analysisTools.find(item => item.id === toolId);
  if (!tool) return <section><h1>未找到该分析工具</h1><Link to="/analysis/center">返回分析中心</Link></section>;
  const context = new URLSearchParams();
  const project = query.get("project") || query.get("project_id");
  const dataset = query.get("asset_set");
  if (project) context.set("project", project);
  if (query.has("asset_set")) context.set("asset_set", dataset || "");
  for(const key of ["input_asset","return_to","reuse_inputs","prepare_mode"])if(query.get(key))context.set(key,query.get(key)!);
  const center = new URLSearchParams(context);
  center.set("category", tool.category);
  const category = ({overview: "组库概览与多样性", clones: "克隆特征与共享", genes: "V/J 基因特征",
    annotation: "注释与生成概率", transcriptome: "转录组与通路", modeling: "降维与建模"})[tool.category];
  const returnPath = project && query.get("return_to") ? projectReturnPath(project,query.get("return_to")!,"") : "";
  return <>
    {returnPath && <Link className="btn btn-secondary" to={returnPath}>返回数据准备</Link>}
    <Link className="btn btn-secondary" to={"/analysis/center?" + center}>返回{category}</Link>
    {["vj-difference", "umapin"].includes(tool.id) && <p className="source-selection-message">
      需要新的共享分析结果？<Link to={"/analysis/tools/sharing" + (context.size ? "?" + context : "")}
        target="_blank" rel="noreferrer">进入 CDR3 共享分析</Link>，
      在新标签页完成前置分析后，返回本页刷新结果来源。当前配置会保留。
    </p>}
    {tool.scheme ? <UnifiedAnalysis key={tool.id} fixedScheme={tool.scheme} title={tool.title} description={tool.description}/>
      : <ScriptHubWizard key={tool.id} tool={tool}/>}
  </>;
}
