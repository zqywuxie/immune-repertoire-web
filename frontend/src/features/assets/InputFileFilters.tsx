import { useEffect, useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { Select } from "../../shared/components/Select";
import { Sheet } from "../../shared/components/Sheet";

type Filters = { type: string; status: string; history: boolean; sort: string };
type Props = Filters & {
  mobile: boolean;
  search: string;
  searchDraft: string;
  types: { value: string; label: string }[];
  onSearchChange: (value: string) => void;
  onSearchSubmit: () => void;
  onApply: (filters: Filters) => void;
  onClear: () => void;
};
const statuses = [{value:"",label:"全部校验状态"},{value:"needs_attention",label:"需要处理"},{value:"valid",label:"校验通过"},{value:"pending",label:"等待校验"},{value:"needs_mapping",label:"待确认映射"},{value:"invalid",label:"校验未通过"},{value:"failed",label:"校验失败"}];

export function InputFileFilters(props: Props) {
  const {type,status,history,sort}=props;
  const [open,setOpen]=useState(false);
  const [draft,setDraft]=useState<Filters>({type:"",status:"",history:false,sort:"uploaded_desc"});
  useEffect(()=>{if(!props.mobile)setOpen(false);},[props.mobile]);
  const applied={type,status,history,sort};
  const count=Number(Boolean(type))+Number(Boolean(status))+Number(history)+Number(sort!=="uploaded_desc");
  const controls=(values:Filters,onChange:(next:Filters)=>void)=><>
    <Select value={values.type} ariaLabel="输入类型筛选" options={[{value:"",label:"全部输入类型"},...props.types]} onChange={value=>onChange({...values,type:value})}/>
    <Select value={values.status} ariaLabel="校验状态筛选" options={statuses} onChange={value=>onChange({...values,status:value})}/>
    <Select value={values.sort} ariaLabel="文件排序" options={[
      {value:"uploaded_desc",label:"上传时间：最新优先"},{value:"uploaded_asc",label:"上传时间：最早优先"},
      {value:"name_asc",label:"名称：升序"},{value:"name_desc",label:"名称：降序"},
      {value:"size_desc",label:"大小：从大到小"},{value:"size_asc",label:"大小：从小到大"}
    ]} onChange={value=>onChange({...values,sort:value})}/>
    <label><input type="checkbox" checked={values.history} onChange={event=>onChange({...values,history:event.target.checked})}/> 显示历史版本</label>
  </>;
  const search=<input className="input" aria-label="搜索输入文件" placeholder="搜索文件名或说明" value={props.searchDraft} onChange={event=>props.onSearchChange(event.target.value)} onKeyDown={event=>{if(event.key==="Enter")props.onSearchSubmit();}}/>;
  if(!props.mobile)return <div className="data-query-bar">{search}{controls(applied,props.onApply)}{(props.search||count>0)&&<button className="btn btn-secondary" onClick={props.onClear}>清除文件筛选</button>}</div>;
  return <>
    <div className="data-mobile-query">{search}<button className="btn btn-secondary" aria-label={`文件筛选（${count}）`} onClick={()=>{setDraft(applied);setOpen(true);}}><SlidersHorizontal size={16}/>筛选{count?`（${count}）`:""}</button></div>
    {count>0&&<div className="data-active-filters" aria-label="生效文件筛选">
      {type&&<button onClick={()=>props.onApply({...applied,type:""})} aria-label="移除输入类型筛选">{props.types.find(item=>item.value===type)?.label||"指定输入类型"} ×</button>}
      {status&&<button onClick={()=>props.onApply({...applied,status:""})} aria-label="移除校验状态筛选">{statuses.find(item=>item.value===status)?.label||"指定校验状态"} ×</button>}
      {sort!=="uploaded_desc"&&<button onClick={()=>props.onApply({...applied,sort:"uploaded_desc"})} aria-label="恢复最新上传优先">已调整文件排序 ×</button>}
      {history&&<button onClick={()=>props.onApply({...applied,history:false})} aria-label="隐藏历史版本">包含历史版本 ×</button>}
    </div>}
    <Sheet open={open} title="文件筛选" onClose={()=>setOpen(false)}>
      <p className="data-muted">应用后更新当前数据集的文件列表。关闭保留已生效条件。</p>
      <div className="data-file-filter-fields">{controls(draft,setDraft)}</div>
      <div className="data-filter-footer"><button className="btn btn-secondary" onClick={()=>setDraft({type:"",status:"",history:false,sort:"uploaded_desc"})}>重置文件条件</button><button className="btn btn-primary" onClick={()=>{props.onApply(draft);setOpen(false);}}>应用文件筛选</button></div>
      {(props.search||count>0)&&<button className="btn btn-secondary" onClick={()=>{props.onClear();setOpen(false);}}>清除文件筛选</button>}
    </Sheet>
  </>;
}
