import { useEffect, useRef, useState, type DependencyList } from 'react';
export function usePolling<T>(fetcher:()=>Promise<T>, intervalMs:number|null=3000, dependencies:DependencyList=[]) {
  const fetcherRef=useRef(fetcher);fetcherRef.current=fetcher;
  const [data,setData]=useState<T|null>(null),[error,setError]=useState<string|null>(null),[loading,setLoading]=useState(true);
  useEffect(()=>{
    let disposed=false;
    let timer:ReturnType<typeof setTimeout>;
    setData(null);setLoading(true);setError(null);
    async function poll(){
      try{const value=await fetcherRef.current();if(!disposed){setData(value);setError(null);}}
      catch(reason){if(!disposed)setError(reason instanceof Error?reason.message:'状态读取失败');}
      finally{if(!disposed){setLoading(false);if(intervalMs!==null)timer=setTimeout(poll,intervalMs);}}
    }
    void poll();
    return()=>{disposed=true;clearTimeout(timer);};
  },[intervalMs,...dependencies]);
  return {data,error,loading};
}
