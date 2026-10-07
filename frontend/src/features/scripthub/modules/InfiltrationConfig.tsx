import {PathwaySourcePicker} from "./PathwaySourcePicker";
import { useEffect, useRef, useState } from "react";
import { SamplePairingEditor, type SamplePair } from "./SamplePairingEditor";
import type { ModuleFormProps } from "../../jobs/forms";
import { inspectScriptHubModule } from "../../../shared/api/scriptHub";
import { Field, GroupFieldSelect, inputStyle, ModuleShell, Section, stringValue, useSyncedDefaults, withDefaults } from "./shared";
import { UmapinSampleSelection } from "./UmapinSampleSelection";

type Inspection = {samples_by_value?:Record<string,string[]>;selected_infiltration_samples?:string[];excluded_group_sample_count?:number;profile_samples?:string[]; deconvolution_samples?:string[]; unused_deconvolution_count?:number; subclass_columns?: string[]; cell_columns: string[]; sample_count: number; group_counts?: Record<string,number>; comparison_groups?:string[]; expression_match_count?:number; unused_expression_sample_count?:number; unmatched_deconvolution_sample_count?:number; unused_profile_count?: number};

export function InfiltrationConfig({projectId,module,sourceContext,value:rawValue,onChange}:ModuleFormProps) {
  const value=withDefaults(rawValue,{output_name:"",score_type:"",infiltration_checked:false});
  useSyncedDefaults(rawValue,value,onChange);
  const latest=useRef({value,onChange});latest.current={value,onChange};
  const pathway=module==="immune-infiltration-pathway";
  const samplePathway=module==="immune-infiltration-sample-pathway";
  const paired=module==="immune-infiltration-paired";
  const concordance=module==="immune-infiltration-concordance";
  const consistency=module==="immune-infiltration-consistency";
  const [inspection,setInspection]=useState<Inspection|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [comparisonGroups,setComparisonGroups]=useState<string[]>([]);
  const [groupsBusy,setGroupsBusy]=useState(false);
  const version=useRef(0);
  const [inspectionRevision,setInspectionRevision]=useState(0);
  const [sampleScope,setSampleScope]=useState<Record<string,string[]>>({});
  const sourceKey=`${module}:${projectId}:${sourceContext?.assetSetId}:${sourceContext?.profilePath}:${sourceContext?.deconvolutionPath}:${sourceContext?.transcriptomePath}`;
  const priorSource=useRef(sourceKey);
  const source={project_id:projectId,asset_set:sourceContext?.assetSetId,profile_path:sourceContext?.profilePath,deconvolution_path:sourceContext?.deconvolutionPath,transcriptome_path:sourceContext?.transcriptomePath};
  useEffect(()=>{
    const current=++version.current;
    setInspection(null);setSampleScope({});setComparisonGroups([]);setError("");setBusy(true);
    const {value:active,onChange:change}=latest.current;
    const changed=priorSource.current!==sourceKey;priorSource.current=sourceKey;
    change({...active,...(changed?{cell_columns:undefined,subclass_columns:undefined,sample_pairs:undefined,score_type:"",upstream_artifact_id:undefined,comparison:undefined,selected_infiltration_samples:undefined,selected_infiltration_groups:undefined}:{}),infiltration_checked:false});
    inspectScriptHubModule<Inspection>(module,source).then(result=>{
      if(current!==version.current)return;
      setInspection(previous=>({...previous,...result}));
      const {value:currentValue,onChange:update}=latest.current;
      const defaults:Record<string,unknown>={};
      if(!Array.isArray(currentValue.cell_columns))defaults.cell_columns=result.cell_columns;
      if(!Array.isArray(currentValue.subclass_columns))defaults.subclass_columns=result.subclass_columns||[];
      if(!Array.isArray(currentValue.sample_pairs))defaults.sample_pairs=[];
      if(Object.keys(defaults).length)update({...currentValue,...defaults,infiltration_checked:false});
    }).catch(reason=>{if(current===version.current)setError(reason instanceof Error?reason.message:"输入读取失败");})
      .finally(()=>{if(current===version.current)setBusy(false);});
    return ()=>{version.current++;};
  },[sourceKey,inspectionRevision]);
  const cells=Array.isArray(value.cell_columns)?value.cell_columns as string[]:[];
  const subclasses=Array.isArray(value.subclass_columns)?value.subclass_columns as string[]:[];
  const pairs=Array.isArray(value.sample_pairs)?value.sample_pairs as SamplePair[]:[];
  const comparison=Array.isArray(value.comparison)?value.comparison as string[]:[];
  useEffect(()=>{
    setSampleScope({});setComparisonGroups([]);
    if(paired||!value.group_field||!value.score_type){setGroupsBusy(false);return;}
    let active=true;setGroupsBusy(true);
    inspectScriptHubModule<Inspection>(module,{...source,group_field:value.group_field,score_type:value.score_type,sample_scope_only:true})
      .then(result=>{
        if(!active)return;
        setSampleScope(result.samples_by_value||{});setComparisonGroups(result.comparison_groups||Object.keys(result.samples_by_value||{}));
        const {value:currentValue,onChange:update}=latest.current;
        if(!Array.isArray(currentValue.selected_infiltration_samples)&&result.samples_by_value)
          update({...currentValue,selected_infiltration_samples:Object.values(result.samples_by_value).flat(),infiltration_checked:false});
      })
      .catch(reason=>{if(active)setError(reason instanceof Error?reason.message:"读取实际匹配样本失败");})
      .finally(()=>{if(active)setGroupsBusy(false);});
    return()=>{active=false;};
  },[paired,module,sourceKey,value.group_field,value.score_type]);
  function update(next:Record<string,unknown>){
    version.current++;setBusy(false);setError("");setInspection(previous=>previous?{...previous,group_counts:undefined}:null);
    onChange({...value,...next,infiltration_checked:false});
  }
  async function verify(){
    const current=++version.current;setBusy(true);setError("");
    try{
      const result=await inspectScriptHubModule<Inspection>(module,{...source,group_field:value.group_field,cell_columns:cells,score_type:value.score_type,
        ...(!paired?{selected_infiltration_samples:value.selected_infiltration_samples,selected_infiltration_groups:value.selected_infiltration_groups}:{}),
        ...((concordance||paired)?{subclass_columns:subclasses}:{}),...(paired?{sample_pairs:pairs}:{}),
        ...(pathway?{upstream_artifact_id:value.upstream_artifact_id,comparison}:{}),...(samplePathway?{comparison}:{})});
      if(current!==version.current)return;
      setInspection(result);const {value:currentValue,onChange:change}=latest.current;change({...currentValue,infiltration_checked:true});
    }catch(reason){if(current===version.current){setError(reason instanceof Error?reason.message:"范围检查失败");const active=latest.current;active.onChange({...active.value,infiltration_checked:false});}}
    finally{if(current===version.current)setBusy(false);}
  }
  return <ModuleShell title={samplePathway?"GO-BP 与浸润样本级相关性":pathway?"GO-BP 与浸润方向比较":paired?"浸润与亚类配对相关性":concordance?"浸润与亚类方向比较":consistency?"免疫浸润细胞相关性":"免疫浸润组成与组间比较"} detail={samplePathway?"联用转录组、浸润结果与样本指标表；按完整样本编号匹配，并明确选择两个比较组。":paired?"先明确样本对应关系，再使用指标表分组计算跨数据相关性。":"分组来自样本指标表；按完整样本编号匹配，不从名称推断分组。"} sourceContext={sourceContext}>
    <Field label="输出名称"><input style={inputStyle} value={stringValue(value.output_name)} onChange={event=>onChange({...value,output_name:event.target.value})} placeholder="默认使用分析名称" /></Field>
    <Section title="选择分析范围">
      <fieldset disabled={busy} style={{border:"1px solid var(--separator)",borderRadius:"var(--radius-control)",padding:16,marginBottom:16}}>
        <legend>本次文件的数值类型</legend>
        <div style={{display:"flex",flexWrap:"wrap",gap:16}}>{[["relative","相对比例"],["absolute","绝对分数"],["other","其他原始估计分数"]].map(([key,label])=><label key={key} style={{display:"flex",gap:8,alignItems:"center"}}><input type="radio" name="infiltration-score-type" value={key} checked={value.score_type===key} onChange={()=>update({score_type:key})}/>{label}</label>)}</div>
        <p style={{color:"var(--text-secondary)",marginBottom:0}}>按生成文件时的设置选择。相对和绝对结果请分别选择文件、分别运行；数值类型会保存在本次结果中，不会自动转换输入。</p>
      </fieldset>
      <fieldset disabled={busy} style={{border:0,padding:0}}><GroupFieldSelect value={String(value.group_field||"")} sourceContext={sourceContext} onChange={next=>update({group_field:next,selected_infiltration_samples:undefined,selected_infiltration_groups:undefined,...(samplePathway?{comparison:[]}: {})})}/></fieldset>
      <fieldset disabled={busy} style={{border:"1px solid var(--separator)",borderRadius:"var(--radius-control)",padding:16,marginTop:16}}>
        <legend>细胞类型 · 已选 {cells.length} 项</legend>
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))",gap:12}}>{inspection?.cell_columns.map(cell=><label key={cell} style={{display:"flex",gap:8,alignItems:"center"}}><input type="checkbox" checked={cells.includes(cell)} onChange={event=>update({cell_columns:event.target.checked?[...cells,cell]:cells.filter(item=>item!==cell)})}/>{cell}</label>)}</div>
      </fieldset>
      {(concordance||paired)&&<fieldset disabled={busy} style={{border:"1px solid var(--separator)",borderRadius:"var(--radius-control)",padding:16,marginTop:16}}>
        <legend>亚类指标 · 已选 {subclasses.length} 项</legend>
        <div style={{display:"flex",flexWrap:"wrap",gap:16}}>{inspection?.subclass_columns?.map(column=><label key={column} style={{display:"flex",gap:8,alignItems:"center"}}><input type="checkbox" checked={subclasses.includes(column)} onChange={event=>update({subclass_columns:event.target.checked?[...subclasses,column]:subclasses.filter(item=>item!==column)})}/>{column}</label>)}</div>
      </fieldset>}
      {!paired&&<fieldset disabled={busy||groupsBusy} style={{border:0,padding:0,minWidth:0,marginTop:16}}>
        {groupsBusy&&<p role="status">正在读取真实匹配样本…</p>}
        {!!Object.keys(sampleScope).length&&<UmapinSampleSelection groups={sampleScope} title="本次匹配样本范围" sampleLabel="分析样本"
          description={samplePathway?"按三类输入共同匹配的完整编号选择，前导零和批次编号保留。仅所选比较组进入分析；核对时检查实际样本数量。":"按浸润结果与样本指标表匹配的完整编号选择，前导零和批次编号保留。核对时检查所选分组的实际样本数量。"}
          value={{selected_categories:value.selected_infiltration_groups,selected_samples:value.selected_infiltration_samples}}
          onChange={next=>update({selected_infiltration_groups:next.selected_categories,selected_infiltration_samples:next.selected_samples})}/>}</fieldset>}
      {pathway&&<PathwaySourcePicker key={`${projectId}:${sourceContext?.assetSetId}`} projectId={projectId} assetSet={sourceContext?.assetSetId} value={String(value.upstream_artifact_id||"")} disabled={busy} onChange={(id,comparison)=>update({upstream_artifact_id:id,comparison})}/>}
      {samplePathway&&<fieldset disabled={busy||groupsBusy} style={{border:"1px solid var(--separator)",borderRadius:"var(--radius-control)",padding:16,marginTop:16}}>
        <legend>明确选择两个比较组</legend>
        <p style={{color:"var(--text-secondary)",lineHeight:1.7}}>组别仅用于去除整体分组效应，并在组内置换浸润分数残差。其他组不进入本次分析。</p>
        {groupsBusy&&<p role="status">正在核对三类输入的共同样本…</p>}
        {!groupsBusy&&!comparisonGroups.length&&<p>当前分组字段没有两个以上可共同匹配的组。</p>}
        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))",gap:12}}>
          {[0,1].map(index=><label key={index} style={{display:"grid",gap:6,color:"var(--text-secondary)"}}>第 {index+1} 组
            <select className="input" aria-label={`第 ${index+1} 组`} value={comparison[index]||""} onChange={event=>{const next=[comparison[0]||"",comparison[1]||""];next[index]=event.target.value;if(next[0]&&next[0]===next[1])next[1-index]="";update({comparison:next});}}>
              <option value="">请选择分组</option>{comparisonGroups.map(group=><option key={group} value={group} disabled={group===comparison[1-index]}>{group}</option>)}
            </select>
          </label>)}
        </div>
      </fieldset>}
      {paired&&<SamplePairingEditor key={`${projectId}:${sourceContext?.assetSetId}:${sourceContext?.profilePath}:${sourceContext?.deconvolutionPath}`} deconvolutionSamples={inspection?.deconvolution_samples||[]} profileSamples={inspection?.profile_samples||[]} value={pairs} onChange={next=>update({sample_pairs:next})} disabled={busy}/>}
      <p style={{color:"var(--text-secondary)",lineHeight:1.8}}>{samplePathway?"使用 org.Hs.eg.db 的 GOALL 注释构建十项固定 GO-BP 基因集，在 log2(表达量+1) 上计算 ssGSEA；随后对通路分数和浸润分数秩转换、去除组别效应，并在组内置换估计 p 值。共同匹配样本至少 10 个，每组至少 2 个；至少有一个 GO-BP 集合保留 10 个以上基因。该结果属于探索性内部生物学一致性分析。":pathway?"固定比较十项 GO-BP 通路，使用来源 NES 方向与细胞组间中位数差组成联合检验。每组至少两个匹配样本，全部通路与细胞组合统一 BH 校正。零效应标为无方向差异；该结果用于内部生物学一致性判断。":paired?"至少两个分组，每组至少三个一对一样本配对。各指标秩转换并去除组别效应后计算残差相关；p 值沿用原脚本的残差 Pearson 检验，亚类与细胞组合统一 BH 校正。配对清单会保存到结果中；本分析不会自动按行配对。":concordance?"比较本次匹配样本中亚类指标与细胞分数的组间中位数变化方向。每组至少两个样本；缺失指标不会自动填零。图中强调方向联合 p 值小于 0.05 的结果，校正结果见统计表。这是组间方向比较，不是样本配对相关性。":consistency?"每种细胞先进行秩转换并去除组别效应，再计算残差间相关。至少选择两个细胞，每组至少三个匹配样本；无组内变化的细胞不能计算。相关性表示共同变化，不表示因果关系；相对比例还可能受到组成约束影响。p 值沿用原脚本的残差 Pearson 检验，q 值为细胞对的 BH 校正结果。":"组成图使用原始脚本的全局平移与按行归一化，不能解释为原始细胞比例。组间比较使用原始数值，输出双侧检验 p 值及 BH 校正 q 值。每组至少两个匹配样本。"}</p>
      <button type="button" className="btn btn-primary" disabled={busy||groupsBusy||(pathway&&!value.upstream_artifact_id)||!value.group_field||!cells.length||((concordance||paired)&&!subclasses.length)||(paired&&!pairs.length)||(samplePathway&&(comparison.length!==2||!comparison[0]||!comparison[1]||comparison[0]===comparison[1]||groupsBusy))||!["relative","absolute","other"].includes(String(value.score_type))} onClick={verify}>{busy?"正在检查…":"核对分析范围"}</button>
      {error&&<div role="alert" style={{color:"var(--danger)"}}><p>{error}</p><button type="button" className="btn btn-secondary" disabled={busy} onClick={()=>setInspectionRevision(count=>count+1)}>重新读取数据</button></div>}
      {value.infiltration_checked===true&&inspection?.group_counts&&<div role="status" style={{marginTop:16,padding:16,background:"var(--bg-inset)",borderRadius:"var(--radius-control)"}}><strong>分析范围已确认 · {inspection.sample_count} 个样本</strong><p>{Object.entries(inspection.group_counts).map(([group,count])=>`${group}：${count} 个`).join("；")}</p>{(pathway||samplePathway)&&<p>其他组别中有 {inspection.excluded_group_sample_count||0} 个样本，不参与本次比较。</p>}{samplePathway&&<p>转录组、浸润结果和样本指标表三类输入共同匹配到 {inspection.expression_match_count||0} 个样本；转录组另有 {inspection.unused_expression_sample_count||0} 个样本未匹配。</p>}<p>浸润表中另有 {inspection.unused_deconvolution_count||0} 个样本未纳入本次范围。</p><p>样本指标表中另有 {inspection.unused_profile_count||0} 个样本不参与本次分析。</p></div>}
    </Section>
  </ModuleShell>;
}
