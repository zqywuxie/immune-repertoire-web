import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { InputValidationStatus } from "../features/assets/InputValidationStatus";
import { useAnalysisInputSelection } from "../features/analysis/useAnalysisInputSelection";
import { Stage1DataIntake } from "../features/scripthub/stages/Stage1DataIntake";
import { ProjectDatasetSummary } from "../features/projects/ProjectDatasetSummary";
import { AnalysisDataProvider, useAnalysisData, type AnalysisData } from "../features/analysis/AnalysisDataContext";
import * as projects from "../shared/api/projects";
import type { ProjectAsset } from "../shared/types/domain";
import { apiClient } from "../shared/api/client";
const asset=(id:string,kind="pep",scope="甲"):ProjectAsset=>({id,project_id:"p",asset_type:kind,original_name:`${id}.csv`,storage_path:`/inputs/${id}.csv`,size:10,metadata:{asset_set:scope,validation:{status:"valid"}}});
const empty:AnalysisData={projectId:"p",assetSetName:"",pepPaths:[],profilePath:"",transcriptomePath:"",deconvolutionPath:""};
const response=(scope:string,assets:ProjectAsset[],totals:Record<string,number>={pep:assets.length},truncated_kinds:projects.InputSelectionResponse["truncated_kinds"]=[]):projects.InputSelectionResponse=>({asset_set:scope,assets,totals,truncated_kinds});
beforeEach(()=>{
 sessionStorage.clear();
 vi.spyOn(projects,"listProjects").mockResolvedValue({projects:[{id:"p",name:"项目"}] as any,pagination:{page:1,page_size:20,total:1,total_pages:1}});
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"项目"} as any);
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:["甲","乙"].map(name=>({name,input_count:251,kinds:{pep:{count:251,statuses:{valid:251},sample_min:null,sample_max:null}}}))});
 vi.spyOn(projects,"getProjectInputSelection").mockImplementation(async(_project,scope)=>response(scope,[asset(`${scope}-克隆`,"pep",scope)]));
 vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();sessionStorage.clear();apiClient.invalidateCache();});
function Intake({initial=empty}:{initial?:AnalysisData}){const [data,setData]=useState(initial);return <><Stage1DataIntake {...data} onUpdate={setData}/><output aria-label="实际选择">{JSON.stringify(data)}</output></>;}
const selected=()=>JSON.parse(screen.getByLabelText("实际选择").textContent!);
it("只读取数据集摘要，选择范围前不读取文件；所选数据集的 251 份克隆全部保留",async()=>{
 const clones=Array.from({length:251},(_,n)=>asset(`clone-${n}`));
 vi.mocked(projects.getProjectInputSelection).mockResolvedValue(response("甲",clones));
 render(<MemoryRouter><Intake/></MemoryRouter>);
 const button=await screen.findByRole("button",{name:/^甲 克隆序列表/});expect(projects.getProjectInputSelection).not.toHaveBeenCalled();expect(projects.listProjectAssets).not.toHaveBeenCalled();
 fireEvent.click(button);await waitFor(()=>expect(selected().pepPaths).toHaveLength(251));
 expect(projects.getProjectInputSelection).toHaveBeenCalledWith("p","甲");expect(projects.listProjectAssets).not.toHaveBeenCalled();
 expect(selected().inputAssets).toHaveLength(251);
 expect(screen.getAllByRole("button",{name:/^移除 clone-/})).toHaveLength(10);
 fireEvent.click(screen.getByRole("button",{name:"展开全部 251 个已选克隆文件"}));expect(screen.getAllByRole("button",{name:/^移除 clone-/})).toHaveLength(251);
});
it("加载中可切换数据集，迟到的旧范围不能覆盖新选择",async()=>{
 let resolve!:(value:projects.InputSelectionResponse)=>void;
 vi.mocked(projects.getProjectInputSelection).mockImplementation((_project,scope)=>scope==="甲"?new Promise(done=>{resolve=done;}):Promise.resolve(response("乙",[asset("乙-克隆","pep","乙")])));
 render(<MemoryRouter><Intake/></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:/^甲 克隆序列表/}));await waitFor(()=>expect(projects.getProjectInputSelection).toHaveBeenCalledWith("p","甲"));
 fireEvent.click(screen.getByRole("button",{name:/^乙 克隆序列表/}));await waitFor(()=>expect(selected().pepPaths).toEqual(["/inputs/乙-克隆.csv"]));
 resolve(response("甲",[asset("甲-克隆")]));await waitFor(()=>expect(selected().assetSetName).toBe("乙"));expect(selected().pepPaths).toEqual(["/inputs/乙-克隆.csv"]);
});
it("范围读取失败提供原位重试，不把其他数据集填入当前选择",async()=>{
 vi.mocked(projects.getProjectInputSelection).mockRejectedValueOnce(new Error("读取失败")).mockResolvedValue(response("甲",[asset("克隆")]));
 render(<MemoryRouter><Intake initial={{...empty,assetSetName:"甲"}}/></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:"重新读取输入"}));await waitFor(()=>expect(selected().pepPaths).toEqual(["/inputs/克隆.csv"]));
 expect(vi.mocked(projects.getProjectInputSelection).mock.calls.every(call=>call[1]==="甲")).toBe(true);
});
function Summary(){const {data}=useAnalysisData();return <><ProjectDatasetSummary projectId="p" revision={0}/><output aria-label="实际选择">{JSON.stringify(data)}</output></>;}
it("摘要的第 51 份指标通过类型分页选择，保存实际资产身份",async()=>{
 const first=Array.from({length:50},(_,n)=>asset(`指标-${n}`,"profile")),extra=asset("第51份指标","profile");
 vi.mocked(projects.getProjectInputSelection).mockResolvedValue(response("甲",first,{pep:0,profile:55},["profile"]));
 vi.mocked(projects.listProjectAssets).mockImplementation(async(_project,options={})=>({assets:options.page===2?[extra]:first,pagination:{page:options.page||1,page_size:50,total:55,total_pages:2}}));
 render(<MemoryRouter initialEntries={["/?project=p&asset_set=甲"]}><AnalysisDataProvider><Summary/></AnalysisDataProvider></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:"搜索更多版本"}));fireEvent.click(await screen.findByRole("button",{name:"下一页"}));
 fireEvent.click(await screen.findByRole("button",{name:/第51份指标.csv · 当前文件/}));
 await waitFor(()=>expect(selected().profilePath).toBe(extra.storage_path));
 expect(selected().inputAssets.map((asset:ProjectAsset)=>asset.id)).toEqual([extra.id]);
 expect(projects.listProjectAssets).toHaveBeenLastCalledWith("p",expect.objectContaining({assetSet:"甲",assetType:"profile",page:2,pageSize:50}));
 expect(vi.mocked(projects.listProjectAssets).mock.calls.every(call=>!call[1]?.allPages)).toBe(true);
});
it("不存在的明确数据集不会回退到其他数据集",async()=>{
 vi.mocked(projects.getProjectInputSelection).mockResolvedValue(response("缺失",[]));
 render(<MemoryRouter><Intake initial={{...empty,assetSetName:"缺失"}}/></MemoryRouter>);
 await screen.findByText(/指定数据集不存在或已移除/);expect(selected().pepPaths).toEqual([]);
 expect(projects.getProjectInputSelection).toHaveBeenCalledWith("p","缺失");
});

it("校验摘要折叠时只读取汇总，展开才读取本数据集的 20 个文件",async()=>{
 render(<InputValidationStatus projectId="p" revision={0} assetSet="甲"/>);
 const summary=await screen.findByText("甲 · 251 个输入文件 · 查看校验状态");
 expect(projects.listProjectAssets).not.toHaveBeenCalled();
 fireEvent.click(summary);
 await waitFor(()=>expect(projects.listProjectAssets).toHaveBeenCalledWith("p",{inputsOnly:true,assetSet:"甲",pageSize:20,skipCache:true}));
 expect(screen.getByText("查看完整文件列表")).toBeInTheDocument();
});
it("等待校验时定时刷新当前范围，终态后停止，切换范围取消旧定时器",async()=>{
 vi.useFakeTimers();
 const pending={...asset("克隆"),metadata:{asset_set:"甲",validation:{status:"pending"}}};
 vi.mocked(projects.getProjectInputSelection).mockResolvedValueOnce(response("甲",[pending])).mockResolvedValue(response("甲",[asset("克隆")]));
 const {result,rerender}=renderHook(({scope})=>useAnalysisInputSelection("p",scope,[]),{initialProps:{scope:"甲"}});
 await act(async()=>{await Promise.resolve();await Promise.resolve();});
 expect(result.current.ready).toBe(true);expect(projects.getProjectInputSelection).toHaveBeenCalledTimes(1);
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});
 expect(projects.getProjectInputSelection).toHaveBeenCalledTimes(2);
 expect(result.current.currentAssets[0].metadata?.validation).toEqual({status:"valid"});
 await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});expect(projects.getProjectInputSelection).toHaveBeenCalledTimes(2);
 vi.mocked(projects.getProjectInputSelection).mockResolvedValueOnce(response("乙",[{...pending,metadata:{asset_set:"乙",validation:{status:"pending"}}}]));
 rerender({scope:"乙"});await act(async()=>{await Promise.resolve();await Promise.resolve();});
 rerender({scope:""});await act(async()=>{await Promise.resolve();await Promise.resolve();});
 const calls=vi.mocked(projects.getProjectInputSelection).mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});expect(projects.getProjectInputSelection).toHaveBeenCalledTimes(calls);
});

it("核对新指定文件时保留浏览器历史开关，核对结束仍可继续追加历史文件",async()=>{
 const props={projectId:"p",assetSetName:"甲",pepPaths:["/inputs/克隆.csv"],profilePath:"",transcriptomePath:"",inputAssets:[asset("克隆")],selectionExplicit:true,onUpdate:vi.fn()};
 vi.mocked(projects.listProjectAssets).mockResolvedValue({assets:[{...asset("历史指标","profile"),metadata:{asset_set:"甲",superseded:true}}]});
 const {rerender}=render(<MemoryRouter><Stage1DataIntake {...props} inputIntentPending={false}/></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:/浏览当前数据集文件/}));
 const history=await screen.findByLabelText("显示历史版本");fireEvent.click(history);
 await waitFor(()=>expect(projects.listProjectAssets).toHaveBeenCalledWith("p",expect.objectContaining({assetSet:"甲",includeSuperseded:true})));
 rerender(<MemoryRouter><Stage1DataIntake {...props} inputIntentPending/></MemoryRouter>);
 expect(history).toBeInTheDocument();expect(history).toBeChecked();expect(history.closest("[inert]")).toBeInTheDocument();
 expect(screen.getByText("正在核对所选文件，请稍候；筛选和已选版本会保留。")).toBeVisible();
 rerender(<MemoryRouter><Stage1DataIntake {...props} inputIntentPending={false}/></MemoryRouter>);
 expect(history).toBeChecked();expect(history.closest("[inert]")).toBeNull();
 fireEvent.click(await screen.findByRole("button",{name:/历史指标.csv · 历史版本/}));
 expect(props.onUpdate).toHaveBeenCalledWith(expect.objectContaining({profilePath:"/inputs/历史指标.csv",pepPaths:props.pepPaths}),expect.objectContaining({id:"历史指标"}));
});
