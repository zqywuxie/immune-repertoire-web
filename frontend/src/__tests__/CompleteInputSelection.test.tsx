import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { useState } from "react";
import { AnalysisDataProvider, useAnalysisData } from "../features/analysis/AnalysisDataContext";
import { AnalysisSelectionNotice } from "../features/analysis/AnalysisSelectionNotice";
import { ProjectDatasetSummary } from "../features/projects/ProjectDatasetSummary";
import { Stage1DataIntake } from "../features/scripthub/stages/Stage1DataIntake";
import * as projects from "../shared/api/projects";
import type { ProjectAsset } from "../shared/types/domain";
import { apiClient } from "../shared/api/client";

const asset=(id:string,type:string,history=false):ProjectAsset=>({id,project_id:"p",asset_type:type,original_name:`${id}.csv`,storage_path:`/source/${id}.csv`,size:10,metadata:{asset_set:"甲",superseded:history,validation:{status:"valid"}}});
const a=asset("a","pep"),b=asset("b","pep",true),old=asset("old","profile",true),current=asset("current","profile");
const saved={projectId:"p",assetSetName:"甲",inputs:{pep:["a","b"],profile:"old",transcriptome:"",deconvolution:""}};
const complete={projectId:"p",assetSetName:"甲",pepPaths:[a.storage_path!,b.storage_path!],profilePath:old.storage_path!,transcriptomePath:"",deconvolutionPath:"",inputAssets:[a,b,old],selectionExplicit:true};
beforeEach(()=>{
 sessionStorage.clear();
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{name:"甲",input_count:2,kinds:{}}]});
 vi.spyOn(projects,"getProjectInputSelection").mockResolvedValue({asset_set:"甲",assets:[a,current],totals:{pep:1,profile:1},truncated_kinds:[]});
 vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[a,current]});
 vi.spyOn(projects,"listProjects").mockResolvedValue({projects:[{id:"p",name:"项目"}] as any,pagination:{page:1,page_size:20,total:1,total_pages:1}});
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"项目"} as any);
 vi.spyOn(projects,"getProjectAsset").mockImplementation(async (_project,id)=>({asset:[a,b,old,current].find(asset=>asset.id===id)!}));
 vi.spyOn(projects,"resolveProjectInputSelection").mockImplementation(async(_project,scope,ids)=>({asset_set:scope,assets:ids.map(id=>[a,b,old,current].find(row=>row.id===id)!)}));
});
afterEach(()=>{cleanup();vi.restoreAllMocks();sessionStorage.clear();apiClient.invalidateCache();});
function Probe({showSummary=false,requested=b}:{showSummary?:boolean;requested?:ProjectAsset}){
 const [query]=useSearchParams();const requestedAsset=query.has("input_asset")?requested:undefined;
 const {data,setData,selectionState,selectionError}=useAnalysisData();
 const [view,setView]=useState("summary");
 return <><output aria-label="恢复状态">{selectionState}</output><output aria-label="恢复错误">{selectionError}</output><output aria-label="实际输入">{JSON.stringify(data)}</output>
 <button onClick={()=>setData(complete)}>选定全部历史输入</button><button onClick={()=>setData({...complete,pepPaths:[],profilePath:"",inputAssets:[]})}>清空全部选择</button>
 <button onClick={()=>setData({...complete,projectId:"new",assetSetName:"乙",pepPaths:[],profilePath:"",inputAssets:[]})}>切换项目</button>
 <AnalysisSelectionNotice projectId="p" dataset="甲" onClear={()=>setData({...complete,pepPaths:[],profilePath:"",inputAssets:[],selectionExplicit:false})}/>
 {showSummary && data && selectionState==="ready" && <><button onClick={()=>setView(view==="summary"?"intake":"summary")}>切换分析页面</button>{view==="summary"?<ProjectDatasetSummary projectId="p" revision={0} requestedAsset={requestedAsset}/>:<Stage1DataIntake {...data} requestedAsset={requestedAsset} onUpdate={setData}/>}</>}
 </>;
}
function show(options:{showSummary?:boolean;url?:string;storageKey?:string}={}){
 return render(<MemoryRouter initialEntries={[options.url||"/?project=p&asset_set=甲&input_asset=b&reuse_inputs=1"]}><AnalysisDataProvider storageKey={options.storageKey}><Probe showSummary={options.showSummary}/></AnalysisDataProvider></MemoryRouter>);
}
const data=()=>JSON.parse(screen.getByLabelText("实际输入").textContent!);
it("仅保存全部资产标识，刷新后通过实际资产元数据恢复多份克隆和旧指标表",async()=>{
 const first=show();fireEvent.click(screen.getByRole("button",{name:"选定全部历史输入"}));
 await waitFor(()=>expect(JSON.parse(sessionStorage.getItem("analysis-selection")!)).toEqual(saved));
 expect(sessionStorage.getItem("analysis-selection")).not.toContain("/source/");first.unmount();show();
 await waitFor(()=>expect(screen.getByLabelText("恢复状态")).toHaveTextContent("ready"));
 expect(data()).toMatchObject(complete);expect(projects.resolveProjectInputSelection).toHaveBeenCalledWith("p","甲",["a","b","old"]);expect(projects.getProjectAsset).not.toHaveBeenCalled();
});
it("恢复后在摘要和真实数据选择组件之间切换，继续保留两份克隆及历史指标",async()=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify(saved));show({showSummary:true});
 await screen.findByRole("heading",{name:"克隆序列表"});
 await waitFor(()=>expect(data()).toMatchObject(complete));
 expect(within(screen.getByRole("heading",{name:"克隆序列表"}).closest("article")!).getByText("2 个输入文件")).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"切换分析页面"}));await screen.findByText("选择或上传数据");
 await waitFor(()=>expect(data()).toMatchObject(complete));
 fireEvent.click(screen.getByRole("button",{name:"切换分析页面"}));await screen.findByRole("heading",{name:"克隆序列表"});
 await waitFor(()=>expect(data()).toMatchObject(complete));
});
it("新打开的文件入口仍以指定克隆为准，不继承续用页面的整组克隆",async()=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify(saved));show({showSummary:true,url:"/?project=p&asset_set=甲&input_asset=b"});
 await screen.findByRole("heading",{name:"克隆序列表"});await waitFor(()=>expect(data().pepPaths).toEqual([b.storage_path]));
});
it.each(["missing","foreign","wrong-kind","wrong-dataset"])("%s 输入使完整恢复失败，不自动换用当前版本，重试成功后恢复原选项",async failure=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify(saved));
 vi.mocked(projects.resolveProjectInputSelection).mockImplementation(async()=>{
  if(failure==="missing")throw new Error("文件已移除");
  return {asset_set:"甲",assets:[a,b,{...old,...(failure==="foreign"?{project_id:"other"}:failure==="wrong-kind"?{asset_type:"pep"}:{metadata:{asset_set:"乙"}})}]};
 });
 show();await screen.findByRole("button",{name:"重试恢复输入"});
 expect(data().pepPaths).toEqual([]);expect(data().profilePath).toBe("");expect(screen.getByLabelText("恢复状态")).toHaveTextContent("error");
 vi.mocked(projects.resolveProjectInputSelection).mockResolvedValue({asset_set:"甲",assets:[a,b,old]});
 fireEvent.click(screen.getByRole("button",{name:"重试恢复输入"}));await waitFor(()=>expect(data()).toMatchObject(complete));
});
it("迟到的旧项目恢复请求不能覆盖用户新选项目",async()=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify(saved));let resolve!:(value:projects.InputResolutionResponse)=>void;
 vi.mocked(projects.resolveProjectInputSelection).mockImplementation(()=>new Promise(done=>{resolve=done;}));
 show();await waitFor(()=>expect(projects.resolveProjectInputSelection).toHaveBeenCalledTimes(1));
 fireEvent.click(screen.getByRole("button",{name:"切换项目"}));resolve({asset_set:"甲",assets:[a,b,old]});
 await waitFor(()=>expect(data().projectId).toBe("new"));expect(data().profilePath).toBe("");expect(screen.getByLabelText("恢复状态")).toHaveTextContent("ready");
});
it("明确清空的选择刷新后保持为空，摘要不自动补入当前文件",async()=>{
 const first=show();fireEvent.click(screen.getByRole("button",{name:"清空全部选择"}));
 await waitFor(()=>expect(JSON.parse(sessionStorage.getItem("analysis-selection")!).inputs.pep).toEqual([]));first.unmount();
 show({showSummary:true,url:"/?project=p&asset_set=甲&reuse_inputs=1"});
 await screen.findByRole("heading",{name:"克隆序列表"});await waitFor(()=>expect(data().pepPaths).toEqual([]));expect(data().profilePath).toBe("");
});
it("兼容旧范围记录但不信任旧记录中的服务器路径",async()=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify({projectId:"p",assetSetName:"甲",pepPaths:["/obsolete.csv"],profilePath:"/unsafe.csv"}));show();
 expect(data()).toMatchObject({projectId:"p",assetSetName:"甲",pepPaths:[],profilePath:""});expect(projects.getProjectAsset).not.toHaveBeenCalled();
});
it("不同用户存储键相互隔离",async()=>{
 sessionStorage.setItem("analysis-selection:user-a",JSON.stringify(saved));show({storageKey:"analysis-selection:user-b"});
 expect(data()).toBeNull();expect(projects.getProjectAsset).not.toHaveBeenCalled();
});

it("同时恢复克隆、指标、转录组和浸润输入，保留明确的历史版本与兼容类型别名",async()=>{
 const rna=asset("rna","expression",true),immune=asset("immune","cibersort",true);
 sessionStorage.setItem("analysis-selection",JSON.stringify({...saved,inputs:{...saved.inputs,transcriptome:rna.id,deconvolution:immune.id}}));
 vi.mocked(projects.resolveProjectInputSelection).mockImplementation(async(_project,scope,ids)=>({asset_set:scope,assets:ids.map(id=>[a,b,old,rna,immune].find(row=>row.id===id)!)}));
 show();await waitFor(()=>expect(screen.getByLabelText("恢复状态")).toHaveTextContent("ready"));
 expect(data()).toMatchObject({...complete,transcriptomePath:rna.storage_path,deconvolutionPath:immune.storage_path,inputAssets:[a,b,old,rna,immune]});
 expect(data().inputAssets.map((asset:ProjectAsset)=>asset.id)).toEqual([a.id,b.id,old.id,rna.id,immune.id]);
 expect(JSON.parse(sessionStorage.getItem("analysis-selection")!).inputs).toEqual({...saved.inputs,transcriptome:rna.id,deconvolution:immune.id});
});

it("同一资产的新状态替换旧元数据，仍保留未重传的其他历史输入身份",async()=>{
 function UpdateProbe(){const {data,setData}=useAnalysisData();return <><output aria-label="实际输入">{JSON.stringify(data)}</output><button onClick={()=>setData(complete)}>建立选择</button><button onClick={()=>setData({...complete,inputAssets:[{...a,metadata:{asset_set:"甲",content_version:"新版本",validation:{status:"pending"}}}]})}>刷新所选状态</button></>;}
 render(<AnalysisDataProvider><UpdateProbe/></AnalysisDataProvider>);
 fireEvent.click(screen.getByRole("button",{name:"建立选择"}));fireEvent.click(screen.getByRole("button",{name:"刷新所选状态"}));
 await waitFor(()=>expect(data().inputAssets.find((row:ProjectAsset)=>row.id===a.id).metadata).toEqual({asset_set:"甲",content_version:"新版本",validation:{status:"pending"}}));
 expect(data().inputAssets.map((row:ProjectAsset)=>row.id)).toEqual([a.id,b.id,old.id]);expect(data().pepPaths).toEqual(complete.pepPaths);expect(data().profilePath).toBe(old.storage_path);
});
it("恢复身份与候选状态不同时，摘要采用新状态而不持续写回旧状态",async()=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify(saved));
 const full={...a,metadata:{...a.metadata,validation:{status:"pending"}}};
 vi.mocked(projects.resolveProjectInputSelection).mockImplementation(async(_project,scope,ids)=>({asset_set:scope,assets:ids.map(id=>[full,b,old].find(row=>row.id===id)!)}));
 show({showSummary:true});await screen.findByRole("heading",{name:"克隆序列表"});
 await waitFor(()=>expect(data().inputAssets.find((row:ProjectAsset)=>row.id===a.id).metadata).toEqual(a.metadata));
 expect(data().pepPaths).toEqual(complete.pepPaths);expect(data().profilePath).toBe(old.storage_path);
});

it("1101 份克隆和历史指标分为三批恢复，顺序与完整选择保持一致",async()=>{
 const clones=Array.from({length:1101},(_,n)=>asset(`clone-${String(n).padStart(4,"0")}`,"pep",n===0));
 const snapshot={...saved,inputs:{...saved.inputs,pep:clones.map(row=>row.id)}};
 sessionStorage.setItem("analysis-selection",JSON.stringify(snapshot));
 const rows=new Map([...clones,old].map(row=>[row.id,row]));
 vi.mocked(projects.resolveProjectInputSelection).mockImplementation(async(_project,scope,ids)=>({asset_set:scope,assets:ids.map(id=>rows.get(id)!)}));
 show();await waitFor(()=>expect(screen.getByLabelText("恢复状态")).toHaveTextContent("ready"));
 expect(data().pepPaths).toEqual(clones.map(row=>row.storage_path));expect(data().profilePath).toBe(old.storage_path);expect(data().inputAssets).toHaveLength(1102);
 expect(vi.mocked(projects.resolveProjectInputSelection).mock.calls.map(call=>call[2].length)).toEqual([500,500,102]);expect(projects.getProjectAsset).not.toHaveBeenCalled();
 expect(JSON.parse(sessionStorage.getItem("analysis-selection")!)).toEqual(snapshot);
});
it("第二批恢复失败不应用第一批，也不改保存的选择；重试后整组恢复",async()=>{
 const clones=Array.from({length:601},(_,n)=>asset(`clone-${n}`,"pep"));
 const snapshot={...saved,inputs:{...saved.inputs,pep:clones.map(row=>row.id)}};
 sessionStorage.setItem("analysis-selection",JSON.stringify(snapshot));
 const rows=new Map([...clones,old].map(row=>[row.id,row]));let attempts=0;
 vi.mocked(projects.resolveProjectInputSelection).mockImplementation(async(_project,scope,ids)=>{
  if(++attempts===2)throw new Error("第二批读取失败");
  return {asset_set:scope,assets:ids.map(id=>rows.get(id)!)};
 });
 show();await screen.findByRole("button",{name:"重试恢复输入"});
 expect(data().pepPaths).toEqual([]);expect(data().profilePath).toBe("");expect(JSON.parse(sessionStorage.getItem("analysis-selection")!)).toEqual(snapshot);
 fireEvent.click(screen.getByRole("button",{name:"重试恢复输入"}));await waitFor(()=>expect(data().pepPaths).toHaveLength(601));
 expect(data().profilePath).toBe(old.storage_path);expect(data().inputAssets).toHaveLength(602);expect(attempts).toBe(4);
});
it("只有存储 URI 的历史输入仍按原身份恢复，不填入当前文件路径",async()=>{
 sessionStorage.setItem("analysis-selection",JSON.stringify(saved));
 const uriOnly={...old,storage_path:"",storage_uri:"local:///original/old.csv"};
 vi.mocked(projects.resolveProjectInputSelection).mockResolvedValue({asset_set:"甲",assets:[a,b,uriOnly]});
 show();await waitFor(()=>expect(data().profilePath).toBe(uriOnly.storage_uri));
 expect(data().inputAssets.find((row:ProjectAsset)=>row.id===old.id).metadata.superseded).toBe(true);expect(projects.getProjectAsset).not.toHaveBeenCalled();
});
