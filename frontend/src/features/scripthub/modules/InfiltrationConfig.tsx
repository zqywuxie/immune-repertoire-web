import { useEffect, useRef, useState } from "react";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import { GroupFieldSelect, ModuleShell, Section } from "./shared";

type Inspection = {cell_columns: string[]; sample_count: number; group_counts?: Record<string,number>; unused_profile_count?: number};

export function InfiltrationConfig({projectId,sourceContext,value,onChange}:ModuleFormProps) {
  const [inspection,setInspection]=useState<Inspection|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const version=useRef(0);
  const source={project_id:projectId,asset_set:sourceContext?.assetSetId,profile_path:sourceContext?.profilePath,deconvolution_path:sourceContext?.deconvolutionPath};
  useEffect(()=>{
    const current=++version.current;
    setInspection(null);setError("");setBusy(true);
    onChange({...value,cell_columns:[],score_type:"",infiltration_checked:false});
    inspectScriptHubModule<Inspection>("immune-infiltration",source).then(result=>{
      if(current!==version.current)return;
      setInspection(result);onChange({...value,cell_columns:result.cell_columns,score_type:"",infiltration_checked:false});
    }).catch(reason=>{if(current===version.current)setError(reason instanceof Error?reason.message:"输入读取失败");})
      .finally(()=>{if(current===version.current)setBusy(false);});
    return ()=>{version.current++;};
  },[projectId,sourceContext?.assetSetId,sourceContext?.profilePath,sourceContext?.deconvolutionPath]);
  const cells=Array.isArray(value.cell_columns)?value.cell_columns as string[]:[];
  function update(next:Record<string,unknown>){version.current++;setBusy(false);setInspection(previous=>previous?{...previous,group_counts:undefined}:null);onChange({...value,...next,infiltration_checked:false});}
  async function verify(){
    const current=++version.current;setBusy(true);setError("");
    try{
      const result=await inspectScriptHubModule<Inspection>("immune-infiltration",{...source,group_field:value.group_field,cell_columns:cells,score_type:value.score_type});
      if(current!==version.current)return;
      setInspection(result);onChange({...value,infiltration_checked:true});
    }catch(reason){if(current===version.current){setError(reason instanceof Error?reason.message:"范围检查失败");onChange({...value,infiltration_checked:false});}}
    finally{if(current===version.current)setBusy(false);}
  }
  return <ModuleShell title="免疫浸润组成与组间比较" detail="分组来自样本指标表；按完整样本编号匹配，不从名称推断分组。" sourceContext={sourceContext}>
    <Section title="选择分析范围">
      <fieldset disabled={busy} style={{border:"1px solid var(--separator)",borderRadius:"var(--radius-control)",padding:16,marginBottom:16}}>
        <legend>本次文件的数值类型</legend>
        <div style={{display:"flex",flexWrap:"wrap",gap:16}}>{[["relative","相对比例"],["absolute","绝对分数"],["other","其他原始估计分数"]].map(([key,label])=><label key={key} style={{display:"flex",gap:8,alignItems:"center"}}><input type="radio" name="infiltration-score-type" value={key} checked={value.score_type===key} onChange={()=>update({score_type:key})}/>{label}</label>)}</div>
        <p style={{color:"var(--text-secondary)",marginBottom:0}}>按生成文件时的设置选择。相对和绝对结果请分别选择文件、分别运行；数值类型会保存在本次结果中，不会自动转换输入。</p>
      </fieldset>
      <fieldset disabled={busy} style={{border:0,padding:0}}><GroupFieldSelect value={String(value.group_field||"")} sourceContext={sourceContext} onChange={next=>update({group_field:next})}/></fieldset>
      <fieldset disabled={busy} style={{border:"1px solid var(--separator)",borderRadius:"var(--radius-control)",padding:16,marginTop:16}}>
        <legend>细胞类型 · 已选 {cells.length} 项</legend>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:12}}>{inspection?.cell_columns.map(cell=><label key={cell} style={{display:"flex",gap:8,alignItems:"center"}}><input type="checkbox" checked={cells.includes(cell)} onChange={event=>update({cell_columns:event.target.checked?[...cells,cell]:cells.filter(item=>item!==cell)})}/>{cell}</label>)}</div>
      </fieldset>
      <p style={{color:"var(--text-secondary)",lineHeight:1.8}}>组成图使用原始脚本的全局平移与按行归一化，不能解释为原始细胞比例。组间比较使用原始数值，输出双侧检验 p 值及 BH 校正 q 值。每组至少两个匹配样本。</p>
      <button type="button" className="btn btn-primary" disabled={busy||!value.group_field||!cells.length||!["relative","absolute","other"].includes(String(value.score_type))} onClick={verify}>{busy?"正在检查…":"核对分析范围"}</button>
      {error&&<p role="alert" style={{color:"var(--danger)"}}>{error}</p>}
      {value.infiltration_checked===true&&inspection?.group_counts&&<div role="status" style={{marginTop:16,padding:16,background:"var(--bg-inset)",borderRadius:"var(--radius-control)"}}><strong>分析范围已确认 · {inspection.sample_count} 个样本</strong><p>{Object.entries(inspection.group_counts).map(([group,count])=>`${group}：${count} 个`).join("；")}</p><p>样本指标表中另有 {inspection.unused_profile_count||0} 个样本不参与本次分析。</p></div>}
    </Section>
  </ModuleShell>;
}
