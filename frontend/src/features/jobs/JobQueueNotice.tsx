import {useEffect,useState} from "react";
import {apiClient} from "../../shared/api/client";
import {usePageActivity} from "../../shared/hooks/usePageActivity";
import "./JobQueueNotice.css";

type QueueStatus={state:string;message:string;checked_at:string;position:number|null;online_workers?:number;busy_workers?:number;available?:boolean};
export function JobQueueNotice({jobId}: {jobId:string}) {
  const active=usePageActivity();
  const [snapshot,setSnapshot]=useState<{jobId:string;value:QueueStatus|null}>({jobId:"",value:null});
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    if(!active || !jobId)return;
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>;
    async function read(){
      setLoading(true);
      try{
        const response=await apiClient.get<{job:{status:string;queue_status?:QueueStatus}}>(`/api/jobs/${encodeURIComponent(jobId)}`,undefined,{skipCache:true,deduplicate:false});
        const value=response.job.queue_status || {state:response.job.status === "queued" ? "dispatching" : "not_queued",message:response.job.status === "queued" ? "当前任务尚无持久队列诊断记录，请以任务阶段为准。" : "此任务已不在等待状态，请以最新任务进度为准。",checked_at:new Date().toISOString(),position:null};
        if(!disposed){setSnapshot({jobId,value});setError("");}
      }catch{
        if(!disposed)setError("队列状态读取失败，已保留最近记录。请重新读取；不会再次提交任务。");
      }finally{
        if(!disposed){setLoading(false);timer=setTimeout(read,10000);}
      }
    }
    void read();
    return ()=>{disposed=true;clearTimeout(timer);};
  },[active,jobId,revision]);
  const value=snapshot.jobId===jobId?snapshot.value:null;
  const date=value?.checked_at ? new Date(value.checked_at) : null;
  const checked=date && !Number.isNaN(date.getTime()) ? date.toLocaleTimeString("zh-CN",{hour12:false}) : "";
  return <section className="job-queue-notice" aria-label="等待原因" aria-busy={loading}>
    <div className="job-queue-notice__heading"><strong>等待原因</strong><button type="button" className="btn btn-secondary" disabled={loading} onClick={()=>setRevision(value=>value+1)}>重新读取队列</button></div>
    {value ? <p>{value.message}</p> : <p role="status">{error || "正在读取实际队列状态…"}</p>}
    {!!error && value && <p role="status">{error}</p>}
    {value && <p className="job-queue-notice__facts">{typeof value.online_workers === "number" ? `已登记工作进程 ${value.online_workers} 个${typeof value.busy_workers === "number" ? `，忙碌 ${value.busy_workers} 个` : ""}。` : ""}{value.position!==null ? `等待队列第 ${value.position} 项。` : ""}{checked ? `读取于 ${checked}。` : ""}</p>}
    <small>队列位置会变化，不代表预计开始时间。此面板每 10 秒读取一次，隐藏页面时暂停。</small>
  </section>;
}
