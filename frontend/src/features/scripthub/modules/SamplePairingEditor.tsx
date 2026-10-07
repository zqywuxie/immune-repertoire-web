import {useId,useState} from 'react';

export type SamplePair = {deconvolution_sample:string;profile_sample:string};

export function SamplePairingEditor({deconvolutionSamples,profileSamples,value,onChange,disabled=false}:{deconvolutionSamples:string[];profileSamples:string[];value:SamplePair[];onChange:(value:SamplePair[])=>void;disabled?:boolean}) {
  const [page,setPage]=useState(0);
  const id=useId();
  const pages=Math.max(1,Math.ceil(deconvolutionSamples.length/20));
  const currentPage=Math.min(page,pages-1);
  const paired=new Map(value.map(pair=>[pair.deconvolution_sample,pair.profile_sample]));
  const profileSet=new Set(profileSamples);
  const targets=value.map(pair=>pair.profile_sample);
  const invalid=targets.filter(target=>!profileSet.has(target)).length;
  const duplicate=targets.length-new Set(targets).size;
  function update(sample:string,target:string){
    const next=value.filter(pair=>pair.deconvolution_sample!==sample);
    if(target)next.push({deconvolution_sample:sample,profile_sample:target});
    onChange(next);
  }
  return <fieldset disabled={disabled} style={{border:'1px solid var(--separator)',borderRadius:'var(--radius-control)',padding:16,marginTop:16}}>
    <legend>确认样本配对 · 已填写 {value.length} 对</legend>
    <p>每行填写对应的指标样本编号，留空的浸润样本不参与。分组来自指标表；仅在确认编号代表同一样本时使用同编号填写。</p>
    <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:12}}>
      <button type="button" className="btn btn-secondary" onClick={()=>onChange(deconvolutionSamples.filter(sample=>profileSet.has(sample)).map(sample=>({deconvolution_sample:sample,profile_sample:sample})))}>按完全相同编号填写</button>
      <button type="button" className="btn btn-secondary" onClick={()=>onChange([])}>清空配对</button>
    </div>
    <datalist id={id}>{profileSamples.map(sample=><option key={sample} value={sample}/>)}</datalist>
    <div style={{display:'grid',gap:10}}>{deconvolutionSamples.slice(currentPage*20,(currentPage+1)*20).map(sample=><label key={sample} style={{display:'grid',gridTemplateColumns:'minmax(0,1fr) minmax(0,1fr)',alignItems:'center',gap:12}}>
      <span style={{overflowWrap:'anywhere'}}>浸润样本：{sample}</span>
      <input aria-label={`指标样本：${sample}`} list={id} value={paired.get(sample)||''} placeholder="填写对应编号" onChange={event=>update(sample,event.target.value)} style={{width:'100%',minWidth:0,border:'1px solid var(--separator)',borderRadius:'var(--radius-control)',padding:'8px 10px',background:'var(--bg-surface)',color:'var(--text-primary)'}}/>
    </label>)}</div>
    {pages>1&&<div style={{display:'flex',gap:12,alignItems:'center',marginTop:12}}><button type="button" className="btn btn-secondary" disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>上一页</button><span>{currentPage+1} / {pages}</span><button type="button" className="btn btn-secondary" disabled={currentPage+1>=pages} onClick={()=>setPage(currentPage+1)}>下一页</button></div>}
    {(invalid>0||duplicate>0)&&<p role="alert" style={{color:'var(--danger)'}}>未知指标编号 {invalid} 项，重复使用指标样本 {duplicate} 项；请修正后核对。</p>}
  </fieldset>;
}
