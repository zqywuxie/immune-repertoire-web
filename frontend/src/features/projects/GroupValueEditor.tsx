import { useEffect, useMemo, useState } from "react";
import { ArrowUp, ArrowDown, Search } from "lucide-react";
const PAGE_SIZE=20;

export function GroupValueEditor({values,order,onChange,countLabel,disabled}:{
  values:string[];order:string[];onChange:(next:string[])=>void;countLabel:(value:string)=>string;disabled:boolean;
}) {
  const [search,setSearch]=useState("");
  const [orderSearch,setOrderSearch]=useState("");
  const [page,setPage]=useState(1);
  const [orderPage,setOrderPage]=useState(1);
  const [hiddenAdded,setHiddenAdded]=useState("");
  const selected=useMemo(()=>new Set(order),[order]);
  const candidates=useMemo(()=>values.filter(value=>value.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())),[values,search]);
  const positions=useMemo(()=>order.map((value,index)=>({value,index})).filter(item=>item.value.toLocaleLowerCase().includes(orderSearch.trim().toLocaleLowerCase())),[order,orderSearch]);
  const candidatePage=Math.min(page,Math.max(1,Math.ceil(candidates.length/PAGE_SIZE)));
  const selectedPage=Math.min(orderPage,Math.max(1,Math.ceil(positions.length/PAGE_SIZE)));
  function move(index:number,position:number) {
    if(position<0||position>=order.length||position===index)return;
    const next=[...order];const [value]=next.splice(index,1);next.splice(position,0,value);onChange(next);
    if(!orderSearch.trim())setOrderPage(Math.floor(position/PAGE_SIZE)+1);
  }
  return <div className="data-group-selection-grid">
    <div className="data-group-selection-panel">
      <div className="data-group-selection-heading"><strong>选择分组</strong><span>已纳入 {order.length} / {values.length} 组</span></div>
      <label className="data-group-search"><Search size={16} aria-hidden="true"/><input className="input" aria-label="搜索可选分组" placeholder="搜索分组名称" value={search} disabled={disabled} onChange={event=>{setSearch(event.target.value);setPage(1);}}/></label>
      <fieldset className="data-group-values"><legend>纳入方案的分组</legend>{candidates.slice((candidatePage-1)*PAGE_SIZE,candidatePage*PAGE_SIZE).map(value=><label key={value}>
        <input type="checkbox" disabled={disabled} checked={selected.has(value)} onChange={event=>{onChange(event.target.checked?[...order,value]:order.filter(item=>item!==value));setHiddenAdded(event.target.checked && orderSearch.trim() && !value.toLocaleLowerCase().includes(orderSearch.trim().toLocaleLowerCase())?value:"");}}/>
        <span>{value}</span><small>{countLabel(value)}</small></label>)}</fieldset>
      {!candidates.length && <p className="data-muted">没有匹配的分组；已纳入的其他分组仍保留。</p>}
      <GroupPages total={candidates.length} page={candidatePage} onPage={setPage} label="可选分组" disabled={disabled}/>
    </div>
    <div className="data-group-selection-panel">
      <div className="data-group-selection-heading"><strong>展示顺序</strong><span>完整方案共 {order.length} 组</span></div>
      <label className="data-group-search"><Search size={16} aria-hidden="true"/><input className="input" aria-label="搜索已选分组" placeholder="定位已纳入的分组" value={orderSearch} disabled={disabled} onChange={event=>{setOrderSearch(event.target.value);setOrderPage(1);}}/></label>
      <p className="data-group-order-hint">序号为完整方案的位置，搜索和翻页不会移除分组。</p>
      {hiddenAdded && selected.has(hiddenAdded) && orderSearch.trim() && !hiddenAdded.toLocaleLowerCase().includes(orderSearch.trim().toLocaleLowerCase()) && <p className="data-group-added" role="status">已加入「{hiddenAdded}」，当前搜索下不可见。<button type="button" className="btn btn-secondary" disabled={disabled} onClick={()=>{setOrderSearch("");setOrderPage(Math.floor(order.indexOf(hiddenAdded)/PAGE_SIZE)+1);setHiddenAdded("");}}>定位新增分组</button></p>}
      <ol className="data-group-order" aria-label="分组展示顺序">{positions.slice((selectedPage-1)*PAGE_SIZE,selectedPage*PAGE_SIZE).map(item=><OrderRow key={item.value} {...item} total={order.length} move={move} disabled={disabled}/>)}</ol>
      {!positions.length && <p className="data-muted">{order.length?"没有匹配的已选分组；完整顺序仍保留。":"请从左侧选择分组。"}</p>}
      <GroupPages total={positions.length} page={selectedPage} onPage={setOrderPage} label="已选分组" disabled={disabled}/>
    </div>
  </div>;
}
function OrderRow({value,index,total,move,disabled}:{value:string;index:number;total:number;move:(index:number,position:number)=>void;disabled:boolean}) {
  const [position,setPosition]=useState(String(index+1));
  useEffect(()=>setPosition(String(index+1)),[index,value]);
  const target=Number(position);
  return <li><strong>{index+1}. {value}</strong><div className="data-group-order-controls">
    <div className="data-row-actions"><button type="button" className="btn btn-secondary" disabled={disabled||index===0} aria-label={`上移 ${value}`} onClick={()=>move(index,index-1)}><ArrowUp size={15}/></button>
      <button type="button" className="btn btn-secondary" disabled={disabled||index===total-1} aria-label={`下移 ${value}`} onClick={()=>move(index,index+1)}><ArrowDown size={15}/></button></div>
    <div className="data-group-position"><input className="input" type="number" min={1} max={total} value={position} disabled={disabled} aria-label={`将 ${value} 移到第几位`} onChange={event=>setPosition(event.target.value)} />
      <button type="button" className="btn btn-secondary" disabled={disabled||!Number.isInteger(target)||target<1||target>total||target===index+1} aria-label={`移动 ${value}`} onClick={()=>move(index,target-1)}>移动</button></div>
  </div></li>;
}
function GroupPages({total,page,onPage,label,disabled}:{total:number;page:number;onPage:(page:number)=>void;label:string;disabled:boolean}) {
  const pages=Math.max(1,Math.ceil(total/PAGE_SIZE));
  return <div className="data-group-paging" aria-label={`${label}分页`}><span>匹配 {total} 组{pages>1?` · 第 ${page} / ${pages} 页`:""}</span>{pages>1&&<div>
    <button type="button" className="btn btn-secondary" disabled={disabled||page<=1} onClick={()=>onPage(page-1)}>{label}上一页</button>
    <button type="button" className="btn btn-secondary" disabled={disabled||page>=pages} onClick={()=>onPage(page+1)}>{label}下一页</button></div>}</div>;
}
