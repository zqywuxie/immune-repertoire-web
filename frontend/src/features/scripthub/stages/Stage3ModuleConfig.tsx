import { ConfigurationReview } from "../ConfigurationReview";
import type { ConfigurationReviewItem } from "../configurationValidation";
import { useEffect, useRef, useState } from "react";
import { useApi } from "../../../shared/hooks/useApi";
import { listGroupSpecs, type GroupSpec } from "../../../shared/api/groupSpecs";
import type { JobModule } from "../../../shared/types/domain";
import { getFormComponent, type ScriptHubSourceContext } from "../../jobs/forms";
import { assetLabel, getModuleAvailability, getModuleInspectionInputs } from "../moduleRequirements";

interface Stage3ModuleConfigProps {
  configurationReview?: ConfigurationReviewItem[];
  onGroupSpecIssue?: (issue: string) => void;
  fixedModule?: string;
  fixedParameters?: Record<string,unknown>;
  modules: JobModule[];
  projectId: string;
  selectedModules: string[];
  moduleConfigs: Record<string, Record<string, unknown>>;
  sourceContext?: ScriptHubSourceContext;
  onUpdate: (selectedModules: string[], moduleConfigs: Record<string, Record<string, unknown>>) => void;
}
export function Stage3ModuleConfig({configurationReview=[],onGroupSpecIssue,fixedModule,fixedParameters,modules,projectId,selectedModules,moduleConfigs,sourceContext,onUpdate}: Stage3ModuleConfigProps) {
  const configurationSection = useRef<HTMLElement>(null);
  const [activeKey,setActiveKey] = useState<string | null>(selectedModules[0] || null);
  const [search,setSearch] = useState("");
  const [onlyAvailable,setOnlyAvailable] = useState(false);
  const specs = useApi(() => projectId ? listGroupSpecs(projectId, {profilePath: sourceContext?.profilePath, assetSet: sourceContext?.assetSetId})
    : Promise.resolve({group_specs: [] as GroupSpec[]}),[projectId, sourceContext?.profilePath, sourceContext?.assetSetId]);
  const selectedSpecIds = selectedModules.map(module => String(moduleConfigs[module]?.group_spec_id || "")).filter(Boolean);
  const specIssue = !selectedSpecIds.length ? "" : (specs.status === "loading" || specs.status === "idle") ? "正在核对分组方案来源…"
    : specs.status === "error" ? "分组方案读取失败，请重新核对。"
    : selectedSpecIds.map(id => { const spec = specs.data.group_specs.find(item => item.id === id);
      return !spec ? "所选分组方案已移除，请重新选择。" : spec.source?.available === false ? `${spec.name}：${spec.source.reason}` : "";
    }).find(Boolean) || "";
  useEffect(() => { onGroupSpecIssue?.(specIssue); }, [specIssue, onGroupSpecIssue]);
  useEffect(() => {
    if (fixedModule) return;
    const valid = selectedModules.filter(key => getModuleAvailability(modules.find(module => module.key === key),sourceContext).selectable);
    if (valid.length !== selectedModules.length) onUpdate(valid,Object.fromEntries(valid.map(key => [key,moduleConfigs[key] || {}])));
    if (activeKey && !valid.includes(activeKey)) setActiveKey(null);
  },[modules,selectedModules,moduleConfigs,sourceContext,onUpdate,activeKey,fixedModule]);
  const active = modules.find(module => module.key === (fixedModule || activeKey));
  const ConfigForm = active?.ui_entry ? getFormComponent(active.ui_entry) : null;
  const availableCount = modules.filter(module => getModuleAvailability(module,sourceContext).selectable).length;
  const filtered = modules.filter(module => `${module.label} ${module.description || ""} ${module.key}`.toLowerCase().includes(search.trim().toLowerCase()) && (!onlyAvailable || getModuleAvailability(module,sourceContext).selectable));
  function choose(module: JobModule) {
    if (!getModuleAvailability(module,sourceContext).selectable) return;
    setActiveKey(module.key);
    if (!selectedModules.includes(module.key)) onUpdate([...selectedModules,module.key],{...moduleConfigs,[module.key]:moduleConfigs[module.key] || {}});
  }
  function remove(key: string) {
    const next=selectedModules.filter(item => item !== key);
    const configs={...moduleConfigs};delete configs[key];
    if (activeKey === key) setActiveKey(next[0] || null);
    onUpdate(next,configs);
  }
  return <div style={{display:"grid",gap:24}}>
    {!fixedModule && <>
    <div><h2>选择分析与配置参数</h2><p style={{color:"var(--text-secondary)",marginTop:6}}>当前输入支持选择 {availableCount} / {modules.length} 个模块。选择后核验本次输入，再逐项配置分组与参数。</p></div>
    <div style={{display:"flex",alignItems:"center",flexWrap:"wrap",gap:16}}>
      <label className="field-label" style={{flex:"1 1 220px"}}>搜索分析模块<input className="input" type="search" value={search} onChange={event=>setSearch(event.target.value)} placeholder="输入分析名称或关键词，例如 样本指标表、UMAP" /></label>
      <label style={{display:"flex",gap:8,alignItems:"center"}}><input type="checkbox" checked={onlyAvailable} onChange={event=>setOnlyAvailable(event.target.checked)} />只显示已有输入的模块</label>
    </div>
    {!modules.length ? <p>暂无分析模块。</p> : !filtered.length ? <p role="status">没有匹配的模块，请调整关键词或筛选条件。</p> : <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fit,minmax(min(100%,250px),1fr))",gap:12}}>
      {filtered.map(module=>{const availability=getModuleAvailability(module,sourceContext);const selected=selectedModules.includes(module.key);return <article key={module.key} style={{background:"var(--bg-elevated)",border:`1px solid ${activeKey === module.key ? "var(--accent)" : "var(--separator)"}`,borderRadius:8,padding:16}}>
        <button type="button" aria-label={`配置 ${module.label}`} aria-pressed={selected} aria-disabled={!availability.selectable} onClick={()=>choose(module)} style={{display:"block",width:"100%",textAlign:"left",color:"var(--text-primary)",cursor:availability.selectable?"pointer":"not-allowed"}}><strong>{module.label}</strong><span style={{display:"block",fontSize:13,lineHeight:1.7,color:"var(--text-secondary)",marginTop:8}}>{module.description}</span></button>
        <p style={{fontSize:12,color:"var(--text-secondary)",marginTop:12}}>输出：{module.output_kinds?.join(" / ").toUpperCase() || "以实际分析结果为准"}</p>
        {availability.missing.map(asset=><span key={asset} style={{display:"inline-block",fontSize:12,color:"var(--danger)",marginRight:10}}>缺少 {assetLabel(asset)}</span>)}
        {availability.reason && <p style={{fontSize:12,color:"var(--danger)",marginTop:8}}>{availability.reason}</p>}
        {selected && <button className="btn btn-secondary" aria-label={`移除 ${module.label}`} style={{marginTop:12}} onClick={()=>remove(module.key)}>已选择 · 移除</button>}
      </article>;})}
    </div>}
    {!!selectedModules.length && <div style={{padding:16,background:"var(--bg-inset)",borderRadius:8}}><strong>已选 {selectedModules.length} 个模块</strong><p style={{fontSize:13,marginTop:6}}>{selectedModules.map(key=>modules.find(module=>module.key===key)?.label || key).join("、")}</p><p style={{fontSize:12,color:"var(--text-secondary)",marginTop:6}}>请逐项确认配置。只有本次输入检查通过，才能进入运行步骤。</p></div>}
    </>}
    {fixedModule && <div><h2>配置参数与分组</h2><p>确认下方参数后，进入运行步骤。</p></div>}
    {specIssue && <p role="alert" className="data-error">{specIssue}{specs.status === "error" && <button className="btn btn-secondary" onClick={specs.refetch}>重新读取分组方案</button>}</p>}
    <ConfigurationReview items={configurationReview} onConfigure={module=>{setActiveKey(module);requestAnimationFrame(()=>{configurationSection.current?.focus({preventScroll:true});configurationSection.current?.scrollIntoView?.({block:"start",behavior:"smooth"});});}}/>
    {active && ConfigForm && <section ref={configurationSection} tabIndex={-1} aria-label={`${active.label}参数配置`} style={{padding:20,border:"1px solid var(--accent)",borderRadius:8,background:"var(--bg-elevated)",minWidth:0}}>
      <div style={{display:"flex",justifyContent:"space-between",gap:12,alignItems:"center",marginBottom:20}}><h3>{active.label} · 参数配置</h3>{!fixedModule && <button className="btn btn-secondary" onClick={()=>setActiveKey(null)}>收起配置</button>}</div>
      {specs.status === "error" && <p role="alert">分组方案读取失败：{specs.error}</p>}
      <ConfigForm fixedParameters={fixedParameters} key={JSON.stringify([active.key,projectId,sourceContext?.assetSetId,sourceContext?.profilePath,sourceContext?.pepPaths,sourceContext?.transcriptomePath])} projectId={projectId} module={active.key} sourceContext={sourceContext ? {...sourceContext, inspectedInputTypes:getModuleInspectionInputs(active.key, moduleConfigs[active.key], sourceContext)} : undefined} groupSpecs={specs.status === "ready"?specs.data.group_specs:[]} loadingSpecs={specs.status === "loading"} value={moduleConfigs[active.key] || {}} onChange={value=>onUpdate(selectedModules,{...moduleConfigs,[active.key]:value})} />
    </section>}
  </div>;
}
