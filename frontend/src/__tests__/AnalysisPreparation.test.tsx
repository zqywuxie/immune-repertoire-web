import {afterEach,describe,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {MemoryRouter,useLocation,useSearchParams} from "react-router-dom";
import {AnalysisPreparation} from "../features/assets/AnalysisPreparation";
import {apiClient} from "../shared/api/client";
import * as upstream from "../shared/api/upstreamSources";
import {analysisTools} from "../features/analysis/tools";
import {getPreparationConfig,preparationInputs} from "../features/analysis/analysisPreparation";
import type {DatasetSummary} from "../shared/api/projects";

const profile={count:1,statuses:{valid:1},sample_min:3,sample_max:3};
const dataset:DatasetSummary={name:"数据甲",input_count:1,kinds:{profile}};
afterEach(()=>{cleanup();vi.restoreAllMocks();});
function Location(){const location=useLocation();return <output data-testid="location">{location.pathname}{location.search}</output>;}
function mount(tool="",mode="",data=dataset){
 const onImport=vi.fn(),onFiles=vi.fn();
 const entry="/management/projects/p1?tab=assets&asset_set="+encodeURIComponent(data.name)+"&file_q=保留筛选&file_page=3"+(tool?"&prepare_tool="+tool:"")+(mode?"&prepare_mode="+mode:"");
 render(<MemoryRouter initialEntries={[entry]}><AnalysisPreparation projectId="p1" dataset={data} revision={0} onImport={onImport} onFiles={onFiles}/><Location/></MemoryRouter>);
 return {onImport,onFiles,entry};
}
function choose(label:string,name:string){fireEvent.click(screen.getByRole("button",{name:label}));fireEvent.click(screen.getByRole("option",{name}));}
describe("按目标准备数据",()=>{
 it("未选目标不读取上游结果，也不要求上传全部输入",()=>{
  const get=vi.spyOn(apiClient,"get");mount();expect(get).not.toHaveBeenCalled();expect(screen.queryByText("尚未提供")).not.toBeInTheDocument();
  expect(screen.queryByRole("link",{name:"继续配置并检查"})).not.toBeInTheDocument();
 });
 it("指标分析只要求指标表，保留精确返回筛选和数据集",()=>{
  const {entry}=mount("profile");const region=within(screen.getByRole("region",{name:"按分析目标准备数据"}));
  expect(region.getByText("样本指标表")).toBeVisible();expect(region.queryByText("克隆序列表")).not.toBeInTheDocument();
  const url=new URL(region.getByRole("link",{name:"继续配置并检查"}).getAttribute("href")!,"http://localhost");
  expect(url.pathname).toBe("/analysis/tools/profile");expect(url.searchParams.get("asset_set")).toBe("数据甲");expect(url.searchParams.get("return_to")).toBe(entry);
  expect(region.queryByText(/^可以运行$/)).not.toBeInTheDocument();
 });
 it("缺失输入仅补充所需类型，待处理和多候选提供对应入口",()=>{
  const {onImport}=mount("sharing");fireEvent.click(screen.getByRole("button",{name:"补充克隆序列表"}));expect(onImport).toHaveBeenCalledWith("pep");
  cleanup();const {onFiles}=mount("profile","",{...dataset,kinds:{profile:{...profile,count:3,statuses:{needs_mapping:1,invalid:1,valid:1}}}});
  expect(screen.getByText(/存在多份候选/)).toBeVisible();expect(screen.getByText(/已有通过文件校验的候选/)).toBeVisible();expect(screen.getByText(/1 个待映射.*1 个需修正/)).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"查看待处理文件"}));expect(onFiles).toHaveBeenCalledWith("profile",true);
  expect(screen.getByRole("link",{name:"进入配置完成映射"})).toHaveAttribute("href",expect.stringContaining("/analysis/tools/profile?"));
 });
 it("当前范围先读取摘要，展开才读取来源目录",async()=>{
  const summary=vi.spyOn(upstream,"getUpstreamSummary").mockResolvedValue({success:true,summary:{total:2,available:1,unavailable:1,reasons:[{reason:"来源文件已丢失",count:1}]}});
  const catalog=vi.spyOn(upstream,"getUpstreamCatalog").mockResolvedValue({success:true,summary:{total:2,available:1,unavailable:1,reasons:[]},pagination:{page:1,page_size:20,total:2,total_pages:1},candidates:[
   {id:"one",job_id:"job-1",project_id:"p1",asset_set:"数据甲",status:"available",reason:"",source_task_name:"来源一"},
   {id:"two",job_id:"job-2",project_id:"p1",asset_set:"数据甲",status:"unavailable",reason:"来源文件已丢失",source_task_name:"来源二"},
  ]});mount("umapin");
  await screen.findByText(/1 项前置结果可用/);expect(summary).toHaveBeenCalledWith("p1","数据甲",expect.objectContaining({cacheType:"umapin"}));expect(catalog).not.toHaveBeenCalled();
  expect(screen.queryByText("克隆序列表")).not.toBeInTheDocument();
  const details=screen.getByText("查找来源任务与状态（2）").closest("details")!;details.open=true;fireEvent(details,new Event("toggle"));
  await screen.findByText("来源一");expect(catalog).toHaveBeenCalledWith("p1","数据甲",expect.anything(),{page:1,search:"",status:""});
  expect(screen.getByText("来源文件已丢失")).toBeVisible();
  const url=new URL(screen.getByRole("link",{name:"查看来源任务 job-1"}).getAttribute("href")!,"http://localhost");expect(url.searchParams.get("asset_set")).toBe("数据甲");
 });
 it("网络失败不显示零结果，刷新后重新核对",async()=>{
  const list=vi.spyOn(upstream,"getUpstreamSummary").mockRejectedValueOnce(new Error("连接中断")).mockResolvedValueOnce({success:true,summary:{total:0,available:0,unavailable:0,reasons:[]}});mount("vj-difference");
  expect(await screen.findByRole("alert")).toHaveTextContent("连接中断");expect(screen.queryByText("当前数据集尚无可用前置结果。")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"刷新前置结果"}));await screen.findByText("当前数据集尚无可用前置结果。");expect(list).toHaveBeenCalledTimes(2);
 });
 it("切换范围后忽略旧摘要完成",async()=>{
  let resolveOld!:(value:any)=>void;
  const list=vi.spyOn(upstream,"getUpstreamSummary").mockImplementationOnce(()=>new Promise(resolve=>{resolveOld=resolve;})).mockResolvedValueOnce({success:true,summary:{total:0,available:0,unavailable:0,reasons:[]}});
  function Fixture(){const [query,setQuery]=useSearchParams();const name=query.get("asset_set") || "数据甲";return <><button onClick={()=>setQuery({prepare_tool:"umapin",asset_set:"数据乙"})}>切换到乙</button><AnalysisPreparation projectId="p1" dataset={{...dataset,name}} revision={0} onImport={vi.fn()} onFiles={vi.fn()}/></>;}
  render(<MemoryRouter initialEntries={["/?prepare_tool=umapin&asset_set=数据甲"]}><Fixture/></MemoryRouter>);
  await waitFor(()=>expect(list).toHaveBeenCalledTimes(1));fireEvent.click(screen.getByText("切换到乙"));await screen.findByText("当前数据集尚无可用前置结果。");
  await act(async()=>resolveOld({success:true,summary:{total:1,available:1,unavailable:0,reasons:[]}}));
  expect(screen.queryByText(/1 项前置结果可用/)).not.toBeInTheDocument();expect(list.mock.calls[1][1]).toBe("数据乙");
 });
 it("富集复用模式只读当前范围摘要，并带入配置地址",async()=>{
  const get=vi.spyOn(apiClient,"get").mockResolvedValue({success:true,summary:{total:0,available:0,unavailable:0,reasons:[]}});mount("go-kegg");
  expect(screen.getByRole("button",{name:"补充转录组"})).toBeInTheDocument();expect(get).not.toHaveBeenCalled();
  choose("数据准备方式","复用已完成的差异表达结果");await screen.findByText("当前数据集尚无可用前置结果。");
  expect(screen.queryByRole("button",{name:"补充转录组"})).not.toBeInTheDocument();expect(get).toHaveBeenCalledWith("/api/script-hub/go-kegg-enrichment/sources",{project_id:"p1",asset_set:"数据甲",view:"summary"},expect.anything());
  const href=screen.getByRole("link",{name:"继续配置并检查"}).getAttribute("href")!;expect(new URL(href,"http://localhost").searchParams.get("prepare_mode")).toBe("deg");
 });
 it("通路摘要使用后端严格比较方向核对的状态",async()=>{
  vi.spyOn(upstream,"getUpstreamSummary").mockResolvedValue({success:true,summary:{total:1,available:0,unavailable:1,reasons:[{reason:"来源比较方向记录无效。",count:1}]}});mount("infiltration-pathway");
  await screen.findByText(/已有前置结果目前不可用/);expect(screen.queryByText(/1 项前置结果可用/)).not.toBeInTheDocument();expect(screen.getByText(/来源比较方向记录无效/)).toBeVisible();
 });
 it("机器学习复用特征仍需要标签表，入口拒绝未登记模式",()=>{
  const tool=analysisTools.find(item=>item.id==="ml")!;expect(preparationInputs(tool,"vj")).toEqual(["profile"]);
  expect(getPreparationConfig("ml","vj")).toEqual({mode:"vj"});expect(getPreparationConfig("profile","deg")).toEqual({});expect(getPreparationConfig("ml","arbitrary")).toEqual({});
 });
});
