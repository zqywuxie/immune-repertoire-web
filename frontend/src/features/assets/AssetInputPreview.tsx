import {useEffect,useState} from "react";
import {RefreshCw} from "lucide-react";
import {apiClient} from "../../shared/api/client";
import {readScriptHubTablePreview} from "../../shared/api/scriptHub";
import {Pagination, type PaginationInfo} from "../../shared/components/Pagination";
import {useApi} from "../../shared/hooks/useApi";
import type {ProjectAsset} from "../../shared/types/domain";

type Preview={columns:string[];rows:unknown[][];directory?:boolean;files?:{name:string;size:number}[];pagination?:PaginationInfo};
export function AssetInputPreview(props:{asset:ProjectAsset;projectId?:string}) {
  return <InputPreview key={`${props.projectId || ""}:${props.asset.id}`} {...props}/>;
}
function InputPreview({asset,projectId}:{asset:ProjectAsset;projectId?:string}) {
  const [page,setPage]=useState(1);
  const [file,setFile]=useState("");
  const endpoint=`/api/projects/${projectId}/assets/${asset.id}/table-preview`;
  const listing=useApi<Preview>(()=>projectId
    ? apiClient.get<Preview>(endpoint,{file:"",page,page_size:20},{skipCache:true})
    : readScriptHubTablePreview(asset.storage_path || ""),[projectId,asset.id,page]);
  const table=useApi(()=>apiClient.get<Preview>(endpoint,{file,include_files:false},{skipCache:true}),[projectId,asset.id,file],!!projectId && !!file);
  const list=listing.status === "ready" ? listing.data as Preview : null;
  useEffect(()=>{
    if(!list?.pagination || list.pagination.page !== page) return;
    const last=Math.max(1,list.pagination.total_pages);
    if(page>last){setFile("");setPage(last);}
  },[list?.pagination,page]);
  const current=file?table:listing;
  const preview=current.status === "ready" ? current.data as Preview : null;
  function refresh(){listing.refetch();if(file)table.refetch();}
  return <section className="data-preview-section" aria-label="输入内容预览">
    {list?.directory && <>
      <div className="data-preview-heading"><div><h4>目录内的表格</h4><p className="data-muted">共 {list.pagination?.total ?? list.files?.length ?? 0} 个表格；选择文件查看前五行。</p></div>
        <button className="btn btn-secondary" onClick={refresh}><RefreshCw size={15}/>刷新目录</button></div>
      <div className="data-directory-files">{list.files?.map(entry=><button className="btn btn-secondary" key={entry.name} aria-pressed={file===entry.name} onClick={()=>setFile(entry.name)}>{entry.name}</button>)}</div>
      {!list.files?.length && <p>目录内没有可预览表格。</p>}
      <Pagination pagination={list.pagination} onPageChange={next=>{setFile("");setPage(next);}}/>
    </>}
    {listing.status === "loading" && <p role="status">正在读取文件信息…</p>}
    {listing.status === "error" && <p role="alert" className="data-error">{listing.error}<button className="btn btn-secondary" onClick={listing.refetch}>重新读取文件信息</button></p>}
    {file && table.status === "loading" && <p role="status">正在预览 {file}…</p>}
    {file && table.status === "error" && <p role="alert" className="data-error">{table.error}<button className="btn btn-secondary" onClick={table.refetch}>重新预览所选表格</button></p>}
    {preview && !!preview.columns.length && <>{file && <h4 className="data-preview-filename">{file}</h4>}<div className="data-table-scroll"><table className="data-file-table"><thead><tr>{preview.columns.map(column=><th key={column}>{column}</th>)}</tr></thead>
      <tbody>{preview.rows.map((row,index)=><tr key={index}>{row.map((cell,position)=><td key={position}>{String(cell ?? "")}</td>)}</tr>)}</tbody></table></div></>}
  </section>;
}
