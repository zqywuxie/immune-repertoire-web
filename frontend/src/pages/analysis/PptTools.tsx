import { useState } from 'react';
import { PageHeader } from '../../shared/components/PageHeader';
import { Card } from '../../shared/components/Card';
import { useApi } from '../../shared/hooks/useApi';
import { listProjects, uploadProjectAssets } from '../../shared/api/projects';
import { uploadDocument, documentAction } from '../../shared/api/documentTools';
type Scan = {session_id:string;slide_count:number;heatmap_slides:{slide_index:number;chain_type:string;image_positions:{index:number;metric:string;metric_display?:string;data_url?:string}[]}[]};
type Replacement = {success:boolean;download_url:string;replaced_count:number;total_count:number;warnings?:string[];errors?:string[]};
export function PptTools(){
  const projects=useApi(()=>listProjects(),[]);
  const [project,setProject]=useState(''),[file,setFile]=useState<File|null>(null);
  const [scan,setScan]=useState<Scan|null>(null),[images,setImages]=useState<Record<string,File>>({});
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Replacement|null>(null);
  async function inspect(){if(!file)return;setBusy(true);setError('');setResult(null);setScan(null);setImages({});try{setScan(await uploadDocument<Scan>('/api/ppt/analyze',file));}catch(reason){setError(reason instanceof Error?reason.message:'解析失败');}finally{setBusy(false);}}
  const slots=Array.from(new Map((scan?.heatmap_slides||[]).flatMap(slide=>(slide.image_positions||[]).filter(image=>slide.chain_type&&image.metric).map(image=>[`${slide.chain_type}/${image.metric}`,{...image,chain:slide.chain_type,slide:slide.slide_index}] as const))).entries());
  async function generate(){if(!scan || !project)return;setBusy(true);setError('');setResult(null);try{
    const heatmaps:Record<string,Record<string,string>>={};
    for(const [key,image] of Object.entries(images)){
      const response=await uploadProjectAssets(project,{assetType:'image',files:[image]});
      const path=response.assets[0]?.storage_path;
      if(!path)throw new Error('图片上传未返回有效文件路径');
      const [chain,metric]=key.split('/');(heatmaps[chain] ||= {})[metric]=path;
    }
    setResult(await documentAction<Replacement>('/api/ppt/replace',{session_id:scan.session_id,heatmaps,apply_borders:true}));
  }catch(reason){setError(reason instanceof Error?reason.message:'生成失败');}finally{setBusy(false);}}
  return <><PageHeader title="PPT 图表替换" subtitle="解析真实模板位置，上传替换图表并下载演示文稿"/>
    <div style={{display:'grid',gap:20}}><Card><fieldset disabled={busy} style={{border:0,padding:0,display:'grid',gap:16}}>
      <label>项目<select className="select" value={project} onChange={event=>{setProject(event.target.value);setResult(null);}}><option value="">请选择项目</option>{projects.status==='ready'&&projects.data.projects.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      {projects.status==='error'&&<div role="alert">{projects.error}<button type="button" onClick={projects.refetch}>重试</button></div>}
      <label>上传 PPTX 模板<input className="input" type="file" accept=".pptx" onChange={event=>{const next=event.target.files?.[0]||null;setScan(null);setImages({});setResult(null);setError('');if(next&&!next.name.toLowerCase().endsWith('.pptx')){setError('请选择 PPTX 文件。');setFile(null);}else setFile(next);}}/></label>
      <button className="btn btn-primary" disabled={!file||busy} onClick={inspect}>{busy?'正在处理…':'解析模板'}</button>
    </fieldset></Card>
    {error&&<p role="alert" style={{color:'var(--danger)'}}>{error}</p>}
    {scan&&<Card><h3>模板共 {scan.slide_count} 页 · {slots.length} 类可替换图表</h3><p>同一链与指标的图片会用于模板中所有对应位置；未选择的图表保持原样。</p>
      {!slots.length&&<p>没有识别到可替换的免疫组库热图。请使用带链类型与指标标记的分析报告模板。</p>}
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(260px,100%),1fr))',gap:20}}>{slots.map(([key,slot])=><label key={key} style={{minWidth:0}}>{slot.chain} · {slot.metric_display||slot.metric}{slot.data_url&&<img alt={key+' 原图'} src={slot.data_url} style={{display:'block',maxWidth:'100%',maxHeight:220}}/>}<input className="input" type="file" accept=".png,.jpg,.jpeg" disabled={busy} onChange={event=>{const next=event.target.files?.[0];setResult(null);setImages(previous=>{const value={...previous};if(next)value[key]=next;else delete value[key];return value;});}}/></label>)}</div>
      <button className="btn btn-primary" disabled={busy||!project||!Object.keys(images).length} onClick={generate}>{busy?'正在生成…':'生成替换后的 PPT'}</button>
    </Card>}
    {result&&<Card><h3>替换结果</h3><p>已替换 {result.replaced_count} / {result.total_count} 个位置。</p>{[...(result.warnings||[]),...(result.errors||[])].map((message,index)=><p key={index}>{message}</p>)}{result.replaced_count>0&&<a className="btn btn-primary" href={result.download_url} download>下载 PPTX</a>}{result.replaced_count===0&&<p>没有完成替换，请检查模板标记与所选图片。</p>}</Card>}
    </div></>;
}
