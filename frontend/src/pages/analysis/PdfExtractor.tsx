import { useState } from 'react';
import { PageHeader } from '../../shared/components/PageHeader';
import { Card } from '../../shared/components/Card';
import { uploadDocument, documentAction } from '../../shared/api/documentTools';
type PdfResult = { table_data?: { headers?: string[]; rows?: unknown[][] }; extracted_images?: Record<string, { index: number; image: string }[]>; error_messages?: Record<string,string>; success_count?: number };
export function PdfExtractor() {
  const [file,setFile]=useState<File|null>(null), [fileId,setFileId]=useState('');
  const [mode,setMode]=useState('table'), [indices,setIndices]=useState('0,-1');
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  const [result,setResult]=useState<PdfResult|null>(null);
  async function run(event: React.FormEvent) {
    event.preventDefault(); if(!file) return;
    setBusy(true);setError('');setResult(null);
    try {
      const selected=indices.split(',').map(value=>Number(value.trim()));
      if(mode==='image' && (!indices.trim() || indices.split(',').some(value=>!value.trim()) || selected.some(value=>!Number.isInteger(value)))) throw new Error('图片序号请输入逗号分隔的整数，例如 0,1,-1。');
      const id=fileId || (await uploadDocument<{file_id:string}>('/api/pdf/upload',file)).file_id;
      setFileId(id);
      setResult(await documentAction<PdfResult>(mode==='table'?'/api/pdf/extract-tables':'/api/pdf/extract-images',{file_ids:[id],...(mode==='image'?{indices:selected}:{})}));
    } catch(reason){setError(reason instanceof Error?reason.message:'提取失败');} finally{setBusy(false);}
  }
  const headers=result?.table_data?.headers || [], rows=result?.table_data?.rows || [];
  const csv=[headers,...rows].map(row=>row.map(value=>'"'+String(value??'').replaceAll('"','""')+'"').join(',')).join('\r\n');
  return <>
    <PageHeader title="PDF 提取" subtitle="从报告提取 B 细胞同型表格或内嵌图片" />
    <form onSubmit={run} style={{display:'grid',gap:20}}><Card><fieldset disabled={busy} style={{border:0,padding:0,display:'grid',gap:16}}>
      <label>上传 PDF（最大 50 MB）<input className="input" type="file" accept=".pdf" onChange={event=>{const next=event.target.files?.[0]||null;setResult(null);setFileId('');setError('');if(next && (!next.name.toLowerCase().endsWith('.pdf') || next.size>50*1024*1024)){setError('请选择不超过 50 MB 的 PDF 文件。');setFile(null);}else setFile(next);}}/></label>
      <label>提取内容<select className="select" value={mode} onChange={event=>{setMode(event.target.value);setResult(null);}}><option value="table">B 细胞同型表格</option><option value="image">内嵌图片</option></select></label>
      {mode==='image'?<label>图片序号<input className="input" value={indices} onChange={event=>setIndices(event.target.value)}/><small>从 0 开始；-1 表示最后一张图片。这里填写图片序号，不是 PDF 页码。</small></label>:<p>用于报告中的 Expression 和 Unique CDR3 同型指标表；扫描件需要先完成文字识别。</p>}
      <button className="btn btn-primary" disabled={!file || busy}>{busy?'正在提取…':'开始提取'}</button>
    </fieldset></Card></form>
    {error && <p role="alert" style={{color:'var(--danger)'}}>{error}</p>}
    {result && <Card><h3>提取结果</h3>
      {Object.entries(result.error_messages||{}).map(([name,message])=><p role="alert" key={name}>{name}：{message}</p>)}
      {!!headers.length && <><a className="btn btn-secondary" download="pdf-table.csv" href={'data:text/csv;charset=utf-8,'+encodeURIComponent('\ufeff'+csv)}>下载 CSV</a><div style={{overflowX:'auto'}}><table style={{width:'100%',textAlign:'left'}}><thead><tr>{headers.map((value,index)=><th key={index}>{value}</th>)}</tr></thead><tbody>{rows.map((row,index)=><tr key={index}>{row.map((value,column)=><td key={column}>{String(value??'')}</td>)}</tr>)}</tbody></table></div></>}
      {Object.entries(result.extracted_images||{}).map(([name,images])=><section key={name}><h4>{name}</h4><div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(min(260px,100%),1fr))',gap:20}}>{images.map((item,index)=><figure key={index} style={{margin:0}}><img style={{maxWidth:'100%'}} alt={`图片 ${item.index}`} src={'data:image/png;base64,'+item.image}/><figcaption><a download={`image-${item.index}.png`} href={'data:image/png;base64,'+item.image}>下载图片 {item.index}</a></figcaption></figure>)}</div></section>)}
      {!headers.length && !Object.values(result.extracted_images||{}).some(images=>images.length>0) && <p>未提取到可展示的内容，请检查报告类型或图片序号后重试。</p>}
      <a download="pdf-extraction.json" href={'data:application/json;charset=utf-8,'+encodeURIComponent(JSON.stringify(result,null,2))}>下载完整提取结果</a>
    </Card>}
  </>;
}
