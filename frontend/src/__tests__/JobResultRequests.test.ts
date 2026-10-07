import { afterEach, expect, it, vi } from "vitest";
import { getJob, getJobResults } from "../shared/api/jobs";
import { apiClient } from "../shared/api/client";
afterEach(()=>{apiClient.invalidateCache();vi.unstubAllGlobals()});
it("终态结果读取独立请求，正常并发读取仍共享请求",async()=>{
 let finishOld!: (response:Response)=>void;
 const fetch=vi.fn().mockImplementationOnce(()=>new Promise<Response>(resolve=>{finishOld=resolve}));
 fetch.mockResolvedValueOnce(new Response(JSON.stringify({status:"completed",outputs:[{label:"指标表"}]}),{headers:{"Content-Type":"application/json"}}));
 vi.stubGlobal("fetch",fetch);
 const first=getJobResults("deferred-result"),shared=getJobResults("deferred-result");
 const fresh=await getJobResults("deferred-result",{forceFresh:true});
 expect(fetch).toHaveBeenCalledTimes(2);expect(fresh.status).toBe("completed");expect(fresh.outputs[0].label).toBe("指标表");
 finishOld(new Response(JSON.stringify({status:"running",outputs:[]}),{headers:{"Content-Type":"application/json"}}));
 expect((await first).status).toBe("running");expect(await shared).toEqual(await first);
});

it("终态子任务状态强制新请求，普通并发状态读取仍共享请求",async()=>{
 let finishOld!: (response:Response)=>void;
 const fetch=vi.fn().mockImplementationOnce(()=>new Promise<Response>(resolve=>{finishOld=resolve}));
 fetch.mockResolvedValueOnce(new Response(JSON.stringify({success:true,job:{id:"deferred-child",status:"completed",progress:100}}),{headers:{"Content-Type":"application/json"}}));
 vi.stubGlobal("fetch",fetch);
 const first=getJob("deferred-child"),shared=getJob("deferred-child");
 const fresh=await getJob("deferred-child",{forceFresh:true});
 expect(fetch).toHaveBeenCalledTimes(2);expect(fresh.job.status).toBe("completed");expect(fresh.job.progress).toBe(100);
 finishOld(new Response(JSON.stringify({success:true,job:{id:"deferred-child",status:"running",progress:35}}),{headers:{"Content-Type":"application/json"}}));
 expect((await first).job.progress).toBe(35);expect(await shared).toEqual(await first);
});
