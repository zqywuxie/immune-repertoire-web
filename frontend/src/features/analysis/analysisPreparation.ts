import type { AnalysisTool } from "./tools";
import { getModuleInspectionInputs, type RequiredAsset } from "../scripthub/moduleRequirements";

const preparationModes: Record<string, Array<{value:string; label:string; config:Record<string,unknown>}>> = {
  "go-kegg": [
    {value:"expression",label:"从转录组表达矩阵开始",config:{input_mode:"expression"}},
    {value:"deg",label:"复用已完成的差异表达结果",config:{input_mode:"deg"}},
  ],
  ml: [
    {value:"profile",label:"使用样本指标",config:{mode:"profile"}},
    {value:"vj",label:"使用 V/J 特征与样本标签",config:{mode:"vj"}},
    {value:"profile_vj",label:"合并样本指标与 V/J 特征",config:{mode:"profile_vj"}},
  ],
};
export function getPreparationModes(toolId:string) { return preparationModes[toolId] || []; }
/** Allowlisted entry defaults; module forms remain editable and validate the final configuration. */
export function getPreparationConfig(toolId:string, mode:string):Record<string,unknown> {
  return getPreparationModes(toolId).find(item=>item.value===mode)?.config || {};
}
export function preparationInputs(tool:AnalysisTool, mode:string):RequiredAsset[] {
  if(tool.scheme === "sequencing_reads_chart") return ["profile"];
  return getModuleInspectionInputs(tool.module || "", {...getPreparationConfig(tool.id,mode), ...tool.preset});
}
export type PreparationSource = {kind:"pep"|"differential"|"pathway"; cacheType?:string; title:string; upstreamTool:string; hint:string};
export function preparationSource(tool:AnalysisTool, mode:string):PreparationSource|null {
  if(tool.id === "go-kegg" && mode === "deg") return {kind:"differential",title:"完整差异表达结果",upstreamTool:"expression",hint:"沿用来源比较和统计值，在配置中选择具体结果。"};
  if(tool.id === "infiltration-pathway") return {kind:"pathway",title:"完整 GO-BP 富集结果",upstreamTool:"go-kegg",hint:"前置富集需启用 GSEA，并保留完整通路表及比较方向。"};
  const cacheType = tool.id === "vj-difference" ? "volcano" : tool.id === "umapin" ? "umapin" : tool.id === "mait-nkt" ? "mait-nkt" : tool.id === "ml" && ["vj","profile_vj"].includes(mode) ? "ml-vj" : "";
  return cacheType ? {kind:"pep",cacheType,title:tool.id === "mait-nkt" ? "受体 α 链共享结果" : "V/J 基因使用与特征结果",upstreamTool:"sharing",hint:tool.id === "mait-nkt" ? "默认复用 TRA 共享结果；也可在分析配置中改用已有 TRA 文件。" : "选择与本次链、分组和样本范围匹配的前置结果。"} : null;
}
