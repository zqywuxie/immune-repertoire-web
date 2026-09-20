import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { ScriptHubWizard } from "../pages/analysis/ScriptHubWizard";
import { AnalysisCenter } from "../pages/analysis/AnalysisCenter";
import { ProtectedRoute } from "../shared/components/ProtectedRoute";
import { analysisTools } from "../features/analysis/tools";
import { AnalysisDataProvider } from "../features/analysis/AnalysisDataContext";

vi.mock("../shared/context/AuthContext",()=>({useAuth:()=>({loading:false,isAuthenticated:false})}));
vi.mock("../shared/api/scriptHub",()=>({
 listScriptHubModules:vi.fn().mockResolvedValue({modules:[{key:"profile",label:"样本指标表"},{key:"charts",label:"图表"},{key:"volcano",label:"差异"},{key:"pgen-analysis",label:"生成概率",status:"unavailable"}]}),
 inspectScriptHubDataSelection:vi.fn().mockResolvedValue({sample_count:2,profile_columns:["sample","group"],profile_path:"/synthetic/profile.csv",chains:["TRB"]}),
 readScriptHubTablePreview:vi.fn().mockResolvedValue({columns:["sample","group"],rows:[],row_count:2})
}));
vi.mock("../shared/api/unified",()=>({listAnalysisSchemes:vi.fn().mockResolvedValue({schemes:[{id:"shm_analysis",name:"SHM"}]})}));
vi.mock("../features/scripthub/stages/Stage1DataIntake",()=>({Stage1DataIntake:({onUpdate,profilePath}:any)=><><span data-testid="selected-profile">{profilePath}</span><button onClick={()=>onUpdate({projectId:"p1",assetSetName:"demo",profilePath:"/synthetic/profile.csv",pepPaths:[],transcriptomePath:""})}>选择 样本指标表 数据</button><button onClick={()=>onUpdate({projectId:"p1",assetSetName:"pep",profilePath:"",pepPaths:["/synthetic/pep.csv"],transcriptomePath:""})}>选择 克隆序列表 数据</button></>}));
vi.mock("../features/scripthub/stages/Stage2SourceInspection",()=>({Stage2SourceInspection:({onInspect}:any)=><button onClick={() => onInspect()}>检查所选数据</button>}));
vi.mock("../features/scripthub/stages/Stage3ModuleConfig",()=>({Stage3ModuleConfig:({fixedModule,selectedModules,moduleConfigs,onUpdate}:any)=><><pre data-testid="config">{JSON.stringify(moduleConfigs)}</pre><span data-testid="fixed-module">{fixedModule}</span><span data-testid="selection">{selectedModules.join(",")}</span><button onClick={()=>onUpdate(["profile"],{...moduleConfigs,charts:{samples:["S1"],selected_modules:["chord"]}})}>配置并尝试切换模式</button></>}));
vi.mock("../features/scripthub/stages/Stage4Execution",()=>({Stage4Execution:({modules,moduleConfigs,onJobsCreated}:any)=><><pre data-testid="execution">{JSON.stringify({modules,moduleConfigs})}</pre><button onClick={()=>onJobsCreated(["job-1"])}>提交测试任务</button></>}));
vi.mock("../features/scripthub/stages/Stage6History",()=>({Stage6History:({initialJobId}:any)=><p>历史任务：{initialJobId}</p>}));
function Location(){const location=useLocation();return <output data-testid="location">{location.pathname}{location.search}</output>;}
afterEach(cleanup);
function wizard(id:string,entry="/analysis/tools/test"){
 return render(<MemoryRouter initialEntries={[entry]}><AnalysisDataProvider><ScriptHubWizard tool={analysisTools.find(tool=>tool.id===id)}/><Location/></AnalysisDataProvider></MemoryRouter>);
}
async function inspect(){fireEvent.click(screen.getByRole("button",{name:"下一步"}));fireEvent.click(screen.getByRole("button",{name:"检查所选数据"}));await waitFor(()=>expect(screen.getByRole("button",{name:"下一步"})).toBeEnabled());}
describe("独立分析工具",()=>{
 it("下游入口保留产物标识，切换数据集后清除",async()=>{
  wizard("vj-difference","/analysis/tools/vj-difference?project=p1&asset_set=pep&upstream_artifact=source-one");
  fireEvent.click(screen.getByText("选择 克隆序列表 数据"));await inspect();fireEvent.click(screen.getByText("下一步"));
  expect(JSON.parse(screen.getByTestId("config").textContent!).volcano).toEqual({upstream_artifact_id:"source-one",input_mode:"usage"});
  fireEvent.click(screen.getByText("上一步"));fireEvent.click(screen.getByText("上一步"));
  fireEvent.click(screen.getByText("选择 样本指标表 数据"));
  expect(screen.getByTestId("location").textContent).not.toContain("upstream_artifact");
 });

 it("更换输入后仍固定 Profile 工具，并保留项目地址",async()=>{
  wizard("profile");fireEvent.click(screen.getByText("选择 样本指标表 数据"));await inspect();fireEvent.click(screen.getByText("下一步"));
  expect(screen.getByTestId("selection")).toHaveTextContent("profile");
  fireEvent.click(screen.getByText("上一步"));fireEvent.click(screen.getByText("上一步"));fireEvent.click(screen.getByText("选择 样本指标表 数据"));await inspect();fireEvent.click(screen.getByText("下一步"));
  expect(screen.getByTestId("fixed-module")).toHaveTextContent("profile");expect(screen.getByTestId("location")).toHaveTextContent("project=p1");
 });
 it("图表独立页只能提交自己的模式，并保留可重开的任务地址",async()=>{
  wizard("similarity");fireEvent.click(screen.getByText("选择 克隆序列表 数据"));await inspect();fireEvent.click(screen.getByText("下一步"));fireEvent.click(screen.getByText("配置并尝试切换模式"));fireEvent.click(screen.getByText("下一步"));
  const payload=JSON.parse(screen.getByTestId("execution").textContent!);
  expect(payload).toEqual({modules:["charts"],moduleConfigs:{charts:{samples:["S1"],selected_modules:["heatmap"]}}});
  fireEvent.click(screen.getByText("提交测试任务"));expect(screen.getByTestId("location")).toHaveTextContent("job=job-1");
 });
 it("转录组专页不接受只有 PEP 的数据",async()=>{
  wizard("expression");fireEvent.click(screen.getByText("选择 克隆序列表 数据"));fireEvent.click(screen.getByText("下一步"));fireEvent.click(screen.getByText("检查所选数据"));
  await screen.findByText(/当前数据尚不满足/);expect(screen.getByRole("button",{name:"下一步"})).toBeDisabled();
 });
 it("刷新带任务地址时打开历史结果",()=>{wizard("profile","/analysis/tools/profile?project=p1&job=job-1");expect(screen.getByText("历史任务：job-1")).toBeInTheDocument();});
 it("分析中心支持搜索，并停用缺少环境的工具",async()=>{
  render(<MemoryRouter><AnalysisCenter/></MemoryRouter>);await screen.findAllByText("准备分析");
  const unavailable=screen.getByText("克隆生成概率").closest("article")!;expect(unavailable.querySelector("a")).toBeNull();expect(unavailable).toHaveTextContent("运行环境未启用");
  fireEvent.change(screen.getByRole("searchbox"),{target:{value:"SHM"}});expect(screen.getByRole("status")).toHaveTextContent("0 项");expect(screen.queryByRole("link",{name:"准备分析"})).not.toBeInTheDocument();
 });
 it("未登录时保留工具和任务地址，跳转登录",()=>{
  render(<MemoryRouter initialEntries={["/analysis/tools/profile?project=p1&job=job-1"]}><Routes><Route path="/analysis/tools/profile" element={<ProtectedRoute allowUnauthenticated={false}><p>内部分析</p></ProtectedRoute>}/><Route path="/login" element={<Location/>}/></Routes></MemoryRouter>);
  expect(screen.queryByText("内部分析")).not.toBeInTheDocument();expect(screen.getByTestId("location").textContent).toBe("/login?redirect=%2Fanalysis%2Ftools%2Fprofile%3Fproject%3Dp1%26job%3Djob-1");
 });
});
