import { useEffect } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router-dom";
import { ScriptHubWizard } from "../pages/analysis/ScriptHubWizard";
import type { AnalysisTool } from "../features/analysis/tools";

const mocks = vi.hoisted(() => ({inspect:vi.fn(),preview:vi.fn(),share:vi.fn()}));
vi.mock("../shared/api/scriptHub", () => ({
  inspectScriptHubDataSelection:mocks.inspect,readScriptHubTablePreview:mocks.preview,
  listScriptHubModules:async () => ({modules:[{key:"profile",label:"样本指标分析",status:"available"},{key:"go-kegg-enrichment",label:"功能富集",status:"available"},{key:"volcano",label:"差异分析",status:"available"},{key:"charts",label:"组合图表",status:"available"},{key:"topclone",label:"优势克隆",status:"available"}]}),
}));
vi.mock("../shared/api/projects", () => ({getProject:async (id:string)=>({id,name:"当前科研项目"})}));
vi.mock("../features/analysis/AnalysisDataContext", () => ({useAnalysisData:()=>({
  data:{projectId:"project-1",assetSetName:"Set1",pepPaths:["/uploads/unrelated-invalid-pep.csv"],profilePath:"/uploads/original.csv",transcriptomePath:"/uploads/unrelated-expression.csv",deconvolutionPath:"/uploads/unrelated-infiltration.csv"},setData:mocks.share,
})}));
vi.mock("../features/scripthub/stages/Stage1DataIntake", () => ({Stage1DataIntake:({onUpdate}:any)=><section aria-label="数据选择"><button onClick={()=>onUpdate({projectId:"project-2",assetSetName:"Set2",pepPaths:[],profilePath:"/uploads/other.csv",transcriptomePath:"",deconvolutionPath:""})}>切换数据集</button></section>}));
vi.mock("../features/scripthub/stages/Stage2SourceInspection", () => ({Stage2SourceInspection:({inspection,inspectionError,onInspect}:any)=><section aria-label="数据检查">{inspectionError && <p role="alert">{inspectionError}</p>}<p>{inspection?.inputQuality?.inputs[0]?.status || "尚未核验"}</p><button onClick={()=>onInspect()}>重新检查</button></section>}));
function filledConfiguration(module:string):Record<string,unknown> {
  const grouped={grouptype_fields:["group"],group_field:"group",selected_group_values:{group:["A"]},selected_samples_by_group:{group:{A:["S1"]}}};
  if(module==="profile") return {...grouped,param_begin:"metric",param_over:"metric"};
  if(module==="topclone")return grouped;
  if(module==="charts")return {samples:["S1"],selected_chains:["TRB"]};
  return {};
}
vi.mock("../features/scripthub/stages/Stage3ModuleConfig", () => ({Stage3ModuleConfig:({fixedModule,sourceContext,selectedModules,moduleConfigs,configurationReview,onUpdate}:any)=>{
  useEffect(()=>{if(fixedModule==="profile"&&!Object.keys(moduleConfigs.profile||{}).length)onUpdate(["profile"],{profile:filledConfiguration("profile")});},[fixedModule,JSON.stringify(moduleConfigs)]);
  return <section aria-label="参数配置">{sourceContext?.projectId} / {sourceContext?.assetSetId} / {sourceContext?.profilePath}
    {configurationReview?.map((item:any)=><p key={item.module}>{item.issue}</p>)}
    {selectedModules?.includes("profile") && <><button onClick={()=>onUpdate(selectedModules,{...moduleConfigs,profile:{...moduleConfigs.profile,param_begin:""}})}>清空指标范围</button><button onClick={()=>onUpdate(selectedModules,{...moduleConfigs,profile:filledConfiguration("profile")})}>补全指标参数</button></>}
    {selectedModules?.includes("go-kegg-enrichment") && <button onClick={()=>onUpdate(["go-kegg-enrichment"],{"go-kegg-enrichment":{input_mode:"expression"}})}>改为表达矩阵计算</button>}
    {!fixedModule && <>{["profile","volcano","charts","topclone"].map(key=><button key={key} onClick={()=>onUpdate([...new Set([...selectedModules,key])],{...moduleConfigs,[key]:{...filledConfiguration(key),...(key==="volcano"?{input_mode:"expression"}:{}),...moduleConfigs[key]}})}>选择 {key}</button>)}{selectedModules.map((key:string)=><button key={key} onClick={()=>onUpdate(selectedModules.filter((value:string)=>value!==key),moduleConfigs)}>移除 {key}</button>)}</>}
  </section>;
}}));
vi.mock("../features/scripthub/stages/Stage4Execution", () => ({Stage4Execution:({onBatchCreated,onJobsCreated}:any)=><section aria-label="运行分析"><button onClick={()=>{onBatchCreated("parent-batch");onJobsCreated(["first-child","second-child"]);}}>生成组合任务</button></section>}));
vi.mock("../features/scripthub/stages/Stage5Results", () => ({Stage5Results:()=>null}));
vi.mock("../features/scripthub/stages/Stage6History", () => ({Stage6History:()=> <section aria-label="分析历史"/>}));

const tool = {id:"profile",module:"profile",title:"样本指标分析",input:"样本指标表",description:"按分组比较样本指标"} as AnalysisTool;
function ready(status="checked") {
  return {sample_count:8,samples:["S1","S2"],profile_path:"/uploads/original.csv",profile_columns:["sample","group","metric"],group_fields:["group"],
    input_quality:{inputs:[{kind:"profile",status,sample_column:status==="needs_mapping"?"":"sample"}],alignments:[],errors:status==="pending"?["后台校验中"]:[],warnings:[]}};
}
function show(url="/analysis/tools/profile?project=project-1&asset_set=Set1", currentTool=tool) {
  return render(<MemoryRouter initialEntries={[url]}><ScriptHubWizard tool={currentTool}/></MemoryRouter>);
}
beforeEach(()=>{vi.clearAllMocks();sessionStorage.clear();mocks.preview.mockResolvedValue(null);mocks.inspect.mockResolvedValue(ready());});
afterEach(()=>{cleanup();vi.useRealTimers();});

describe("registered analysis data entry",()=>{
  it("checks and previews only the current analysis inputs while preserving the project selection",async()=>{
    show();
    await screen.findByRole("region",{name:"参数配置"});
    expect(mocks.inspect).toHaveBeenCalledWith(expect.objectContaining({input_types:["profile"],pep_paths:["/uploads/unrelated-invalid-pep.csv"],transcriptome_path:"/uploads/unrelated-expression.csv"}));
    expect(mocks.preview).toHaveBeenCalledTimes(1);
    expect(mocks.preview).toHaveBeenCalledWith("/uploads/original.csv");
    expect(screen.getByRole("region",{name:"本次分析数据"}).textContent).toContain("核验范围：样本指标表");
    expect(screen.getByRole("region",{name:"本次分析数据"}).textContent).not.toContain("转录组");
  });

  it("rechecks newly consumed originals when switching from an upstream result to expression input",async()=>{
    vi.useFakeTimers();
    const expression = (status:string)=>({sample_count:status==="checked"?8:0,transcriptome_path:"/uploads/unrelated-expression.csv",
      input_quality:{inputs:[{kind:"transcriptome",status,sample_column:"Gene"}],alignments:[],errors:status==="pending"?["后台校验中"]:[],warnings:[]}});
    mocks.inspect.mockResolvedValueOnce({sample_count:0,input_quality:{inputs:[],errors:[],warnings:[],alignments:[]}})
      .mockResolvedValueOnce(expression("pending")).mockResolvedValue(expression("checked"));
    show("/analysis/tools/go-kegg?project=project-1&asset_set=Set1&upstream_artifact=registered-deg",{...tool,id:"go-kegg",module:"go-kegg-enrichment"});
    await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
    expect(mocks.inspect).toHaveBeenLastCalledWith(expect.objectContaining({input_types:[]}));
    expect(screen.getByRole("region",{name:"本次分析数据"}).textContent).toContain("前置结果的来源");
    fireEvent.click(screen.getByRole("button",{name:"改为表达矩阵计算"}));
    await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
    expect(mocks.inspect).toHaveBeenLastCalledWith(expect.objectContaining({input_types:["transcriptome"]}));
    expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(true);
    await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
    expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false);
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it("inspects existing data and enters configuration without duplicate intake or computation",async()=>{
    show();
    await screen.findByRole("region",{name:"参数配置"});
    expect(mocks.inspect).toHaveBeenCalledTimes(1);
    expect(mocks.inspect).toHaveBeenCalledWith(expect.objectContaining({project_id:"project-1",asset_set:"Set1",profile_path:"/uploads/original.csv"}));
    expect(screen.queryByRole("region",{name:"运行分析"})).toBeNull();
    expect(screen.queryByRole("region",{name:"数据选择"})).toBeNull();
    fireEvent.click(screen.getByRole("button",{name:"更换或检查数据"}));
    await screen.findByRole("region",{name:"数据选择"});
    expect(screen.queryByRole("region",{name:"参数配置"})).toBeNull();
  });

  it("automatically refreshes pending checks and stops once data is ready",async()=>{
    vi.useFakeTimers();
    mocks.inspect.mockResolvedValueOnce(ready("pending")).mockResolvedValue(ready());
    show();
    await act(async()=>{await vi.advanceTimersByTimeAsync(0);});
    expect(screen.getByText("数据正在后台校验，完成后将自动更新。")).toBeTruthy();
    expect(screen.queryByRole("region",{name:"参数配置"})).toBeNull();
    await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
    expect(screen.getByRole("region",{name:"参数配置"})).toBeTruthy();
    await act(async()=>{await vi.advanceTimersByTimeAsync(9000);});
    expect(mocks.inspect).toHaveBeenCalledTimes(2);
  });

  it("keeps mapping errors and sample alignment confirmation in the checking step",async()=>{
    const result=ready("needs_mapping");mocks.inspect.mockResolvedValueOnce(result);
    const first=show();
    await screen.findByText("needs_mapping");
    expect(screen.queryByRole("region",{name:"参数配置"})).toBeNull();first.unmount();
    mocks.inspect.mockResolvedValue({...ready(),input_quality:{...ready().input_quality,alignments:[{missing_count:1,extra_count:0}]}});
    show();
    const confirm=await screen.findByRole("checkbox");
    expect(screen.queryByRole("region",{name:"参数配置"})).toBeNull();
    fireEvent.click(confirm);
    await screen.findByRole("region",{name:"参数配置"});
  });

  it("ignores a late check from the old dataset after the selection changes",async()=>{
    let finishOld:(result:unknown)=>void=()=>{};
    mocks.inspect.mockImplementationOnce(()=>new Promise(resolve=>{finishOld=resolve;}));
    mocks.inspect.mockResolvedValueOnce({...ready(),profile_path:"/uploads/other.csv"});
    show();
    await waitFor(()=>expect(mocks.inspect).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button",{name:"切换数据集"}));
    await screen.findByRole("region",{name:"参数配置"});
    await act(async()=>finishOld(ready()));
    expect(screen.getByRole("region",{name:"参数配置"}).textContent).toContain("project-2 / Set2 / /uploads/other.csv");
    expect(mocks.inspect).toHaveBeenLastCalledWith(expect.objectContaining({project_id:"project-2",asset_set:"Set2"}));
  });

  it("blocks stale successful inspection after a failed recheck",async()=>{
    show();
    await screen.findByRole("region",{name:"参数配置"});
    expect(screen.getByText(/当前项目：当前科研项目/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button",{name:"更换或检查数据"}));
    mocks.inspect.mockRejectedValueOnce(new Error("文件无法读取"));
    fireEvent.click(screen.getByRole("button",{name:"重新检查"}));
    await screen.findByText("文件无法读取");
    expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not poll after an inspection error or while viewing history",async()=>{
    mocks.inspect.mockRejectedValueOnce(new Error("读取失败"));
    const first=show();
    await waitFor(()=>expect(mocks.inspect).toHaveBeenCalledTimes(1));
    await act(async()=>{await Promise.resolve();});
    expect(screen.queryByRole("region",{name:"参数配置"})).toBeNull();first.unmount();
    mocks.inspect.mockClear();show("/analysis/tools/profile?project=project-1&asset_set=Set1&job=old-task");
    await screen.findByRole("region",{name:"分析历史"});
    expect(mocks.inspect).not.toHaveBeenCalled();
  });
});


function QueryState() { return <output aria-label="当前地址">{useLocation().search}</output>; }
function showCombination() {
  return render(<MemoryRouter initialEntries={["/analysis/script-hub?project=project-1&asset_set=Set1"]}><ScriptHubWizard/><QueryState/></MemoryRouter>);
}
describe("combined analysis input selection",()=>{
  it("selects analyses before checking data, and recovers when a failing unrelated analysis is removed",async()=>{
    mocks.inspect.mockImplementation(async(request:any)=>{
      if(request.input_types.includes("transcriptome"))throw new Error("表达输入失效");
      return ready();
    });
    showCombination();
    fireEvent.click(screen.getByRole("button",{name:"下一步"}));
    await screen.findByRole("region",{name:"参数配置"});
    expect(mocks.inspect).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button",{name:"选择 profile"}));
    await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
    expect(mocks.inspect).toHaveBeenLastCalledWith(expect.objectContaining({input_types:["profile"],alignment_groups:[]}));
    fireEvent.click(screen.getByRole("button",{name:"选择 volcano"}));
    await screen.findByText("表达输入失效");
    expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(true);
    expect(mocks.inspect).toHaveBeenLastCalledWith(expect.objectContaining({input_types:["profile","transcriptome"],alignment_groups:[]}));
    fireEvent.click(screen.getByRole("button",{name:"移除 volcano"}));
    await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
    expect(mocks.inspect).toHaveBeenLastCalledWith(expect.objectContaining({input_types:["profile"]}));
    expect(screen.queryByText("表达输入失效")).toBeNull();
  });

  it("supersedes an in-flight check after the selected modules change",async()=>{
    let finishOld:(value:unknown)=>void=()=>{};
    mocks.inspect.mockImplementationOnce(()=>new Promise(resolve=>{finishOld=resolve;})).mockResolvedValue(ready());
    showCombination();fireEvent.click(screen.getByRole("button",{name:"下一步"}));
    fireEvent.click(await screen.findByRole("button",{name:"选择 profile"}));
    await waitFor(()=>expect(mocks.inspect).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button",{name:"选择 volcano"}));
    await waitFor(()=>expect(mocks.inspect).toHaveBeenCalledTimes(2));
    await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
    await act(async()=>finishOld({...ready(),profile_path:"/uploads/obsolete.csv"}));
    expect(screen.getByRole("region",{name:"参数配置"}).textContent).toContain("/uploads/original.csv");
    expect(screen.getByRole("region",{name:"参数配置"}).textContent).not.toContain("obsolete.csv");
  });

  it("rechecks newly required joint matching even if the file-type union stays the same",async()=>{
    mocks.inspect.mockImplementation(async(request:any)=>({...ready(),input_quality:{...ready().input_quality,
      alignments:request.alignment_groups.length?[{kind:"pep",missing_count:1,extra_count:0}]:[]}}));
    showCombination();fireEvent.click(screen.getByRole("button",{name:"下一步"}));
    fireEvent.click(await screen.findByRole("button",{name:"选择 profile"}));
    fireEvent.click(screen.getByRole("button",{name:"选择 charts"}));
    await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
    const before=mocks.inspect.mock.calls.length;
    fireEvent.click(screen.getByRole("button",{name:"选择 topclone"}));
    const confirmation=await screen.findByRole("checkbox");
    expect(mocks.inspect.mock.calls.length).toBeGreaterThan(before);
    expect(mocks.inspect).toHaveBeenLastCalledWith(expect.objectContaining({input_types:["pep","profile"],alignment_groups:[["pep","profile"]]}));
    expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(confirmation);
    await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button",{name:"移除 topclone"}));
    await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
    expect(screen.queryByRole("checkbox")).toBeNull();
  });
});


it("keeps the parent batch address when child identifiers arrive before navigation rerenders",async()=>{
  showCombination();fireEvent.click(screen.getByRole("button",{name:"下一步"}));
  fireEvent.click(await screen.findByRole("button",{name:"选择 profile"}));
  fireEvent.click(screen.getByRole("button",{name:"选择 volcano"}));
  await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:"下一步"}));
  fireEvent.click(await screen.findByRole("button",{name:"生成组合任务"}));
  const query=new URLSearchParams(screen.getByLabelText("当前地址").textContent || "");
  expect(query.get("batch")).toBe("parent-batch");expect(query.get("job")).toBe("parent-batch");
  expect(query.get("project")).toBe("project-1");expect(query.get("asset_set")).toBe("Set1");
});


it("blocks leaving configuration until missing parameters are corrected, without repeating data checks",async()=>{
  show();await screen.findByRole("region",{name:"参数配置"});
  await waitFor(()=>expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false));
  const checks=mocks.inspect.mock.calls.length;
  fireEvent.click(screen.getByRole("button",{name:"清空指标范围"}));
  expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText("请选择要比较的指标范围。")).toBeTruthy();
  expect(screen.queryByRole("region",{name:"运行分析"})).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"补全指标参数"}));
  expect((screen.getByRole("button",{name:"下一步"}) as HTMLButtonElement).disabled).toBe(false);
  expect(mocks.inspect).toHaveBeenCalledTimes(checks);
});
