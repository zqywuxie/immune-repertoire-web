import { StrictMode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { apiClient } from "../shared/api/client";
import { resolveProjectInputSelection } from "../shared/api/projects";
import { AnalysisDataProvider, useAnalysisData } from "../features/analysis/AnalysisDataContext";
const row={id:"old",project_id:"p",asset_type:"profile",original_name:"历史.csv",storage_path:"/original/old.csv",size:1,metadata:{asset_set:"甲",superseded:true,content_version:"old",validation:{status:"valid"}}};
const result={asset_set:"甲",assets:[row]};
const response=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{"Content-Type":"application/json"}});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();apiClient.invalidateCache();sessionStorage.clear();});
it("相同只读批次合并进行中请求，完成后重新读取而不缓存旧资产状态",async()=>{
 let finish!:(value:Response)=>void;
 const fetch=vi.fn().mockImplementationOnce(()=>new Promise(done=>{finish=done;})).mockResolvedValue(response(result));vi.stubGlobal("fetch",fetch);
 const first=resolveProjectInputSelection("p","甲",["old"]),second=resolveProjectInputSelection("p","甲",["old"]);
 expect(fetch).toHaveBeenCalledTimes(1);expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({asset_set:"甲",asset_ids:["old"]});expect(fetch.mock.calls[0][1].method).toBe("POST");
 finish(response(result));expect(await first).toEqual(result);expect(await second).toEqual(result);
 await resolveProjectInputSelection("p","甲",["old"]);expect(fetch).toHaveBeenCalledTimes(2);
});
it("请求范围或标识不同不会合并，普通写入请求也不去重",async()=>{
 const fetch=vi.fn().mockImplementation(async()=>response(result));vi.stubGlobal("fetch",fetch);
 await Promise.all([resolveProjectInputSelection("p","甲",["old"]),resolveProjectInputSelection("p","乙",["old"]),resolveProjectInputSelection("p","甲",["other"]),apiClient.post("/api/projects",{name:"甲"}),apiClient.post("/api/projects",{name:"甲"})]);
 expect(fetch).toHaveBeenCalledTimes(5);
});
it("共享失败后释放请求，显式重试会向服务器重新读取",async()=>{
 const fetch=vi.fn().mockResolvedValueOnce(response({message:"读取失败"},503)).mockResolvedValue(response(result));vi.stubGlobal("fetch",fetch);
 const outcomes=await Promise.allSettled([resolveProjectInputSelection("p","甲",["old"]),resolveProjectInputSelection("p","甲",["old"])]);
 expect(outcomes.every(item=>item.status==="rejected")).toBe(true);expect(fetch).toHaveBeenCalledTimes(1);
 expect(await resolveProjectInputSelection("p","甲",["old"])).toEqual(result);expect(fetch).toHaveBeenCalledTimes(2);
});
it("账号缓存失效后不续用旧请求，旧请求完成也不清除新请求",async()=>{
 let finishOld!:(value:Response)=>void,finishNew!:(value:Response)=>void;
 const fetch=vi.fn().mockImplementationOnce(()=>new Promise(done=>{finishOld=done;})).mockImplementationOnce(()=>new Promise(done=>{finishNew=done;}));vi.stubGlobal("fetch",fetch);
 const old=resolveProjectInputSelection("p","甲",["old"]);apiClient.invalidateCache();const next=resolveProjectInputSelection("p","甲",["old"]);
 finishOld(response(result));await old;
 const sameNew=resolveProjectInputSelection("p","甲",["old"]);expect(fetch).toHaveBeenCalledTimes(2);
 const changed={asset_set:"甲",assets:[{...row,metadata:{...row.metadata,content_version:"new"}}]};finishNew(response(changed));expect(await next).toEqual(changed);expect(await sameNew).toEqual(changed);
});
it("开发模式重复恢复只请求一次，并按原历史身份应用完整选择",async()=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify({projectId:"p",assetSetName:"甲",inputs:{pep:[],profile:"old",transcriptome:"",deconvolution:""}}));
 let finish!:(value:Response)=>void;const fetch=vi.fn().mockImplementation(()=>new Promise(done=>{finish=done;}));vi.stubGlobal("fetch",fetch);
 function Probe(){const {data,selectionState}=useAnalysisData();return <><output aria-label="状态">{selectionState}</output><output aria-label="选择">{JSON.stringify(data)}</output></>;}
 render(<StrictMode><AnalysisDataProvider><Probe/></AnalysisDataProvider></StrictMode>);expect(fetch).toHaveBeenCalledTimes(1);
 await act(async()=>{finish(response(result));});await waitFor(()=>expect(screen.getByLabelText("状态")).toHaveTextContent("ready"));
 expect(JSON.parse(screen.getByLabelText("选择").textContent!)).toMatchObject({profilePath:row.storage_path,inputAssets:[row],selectionExplicit:true});
});
