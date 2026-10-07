import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError } from "../shared/api/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { JobMonitor } from "../pages/analysis/JobMonitor";
import { getJob, getJobResults, listJobs, listJobModules, retryJob } from "../shared/api/jobs";
import { listProjects, listProjectAssets, listProjectDatasets, getProject } from "../shared/api/projects";
import { useJobEvents } from "../shared/hooks/useJobEvents";
import { usePolling } from "../shared/hooks/usePolling";
import type { JobSummary } from "../shared/types/domain";
vi.mock("../shared/api/jobs",()=>({getJob:vi.fn(),getJobResults:vi.fn(),listJobs:vi.fn(),listJobModules:vi.fn(),cancelJob:vi.fn(),retryJob:vi.fn()}));
vi.mock("../shared/api/projects",()=>({listProjects:vi.fn(),listProjectAssets:vi.fn(),listProjectDatasets:vi.fn().mockResolvedValue({datasets:[]}),getProject:vi.fn()}));
vi.mock("../shared/hooks/useJobEvents",()=>({useJobEvents:vi.fn()}));
vi.mock("../shared/hooks/usePolling",()=>({usePolling:vi.fn()}));
vi.mock("../shared/hooks/useToast",()=>({useToast:()=>({addToast:vi.fn()})}));
const job=(status="running",progress=20,time="2026-10-03T00:18:00Z")=>({id:"job-1",job_type:"script_hub",module:"profile",status,progress,updated_at:time,stage:"阶段"+progress}) as JobSummary;
const result=(snapshot:JobSummary)=>({success:true,job:snapshot,status:snapshot.status,result:{},outputs:[],assets:[]});
const view=()=> <MemoryRouter initialEntries={["/analysis/script-hub/jobs?job=job-1"]}><JobMonitor/></MemoryRouter>;
function polling(snapshot:JobSummary){vi.mocked(usePolling).mockReturnValue({data:{success:true,jobs:[snapshot],counts:{queued:2,interrupted:1}},error:null,loading:false})}
function event(snapshot:JobSummary){vi.mocked(useJobEvents).mockReturnValue({event:{success:true,job:snapshot,status:snapshot.status},error:null,connected:true})}
beforeEach(()=>{
  vi.mocked(listProjectDatasets).mockResolvedValue({datasets:[]});
  vi.mocked(getProject).mockImplementation(async id=>({id,name:"当前研究",status:"active",assets:[]}));
  vi.mocked(getJob).mockResolvedValue({success:true,job:job()});vi.mocked(getJobResults).mockResolvedValue(result(job()));
  vi.mocked(listJobModules).mockResolvedValue({success:true,modules:[]});vi.mocked(listProjects).mockResolvedValue({projects:[],pagination:{page:1,page_size:20,total:0,total_pages:0}});vi.mocked(listProjectAssets).mockResolvedValue({success:true,assets:[]} as never);
  vi.mocked(useJobEvents).mockReturnValue({event:null,error:null,connected:false});polling(job());
});
afterEach(()=>{cleanup();vi.resetAllMocks()});
it("实时进度到达后，旧轮询和迟到结果响应不能把进度倒退",async()=>{
  let resolve!: (value:ReturnType<typeof result>)=>void;
  vi.mocked(getJobResults).mockImplementationOnce(()=>new Promise(done=>{resolve=done}));
  const rendered=render(view());await waitFor(()=>expect(getJobResults).toHaveBeenCalledOnce());
  event(job("running",70,"2026-10-03T00:20:00Z"));rendered.rerender(view());await screen.findByText("70%");
  polling(job("running",30,"2026-10-03T00:19:00Z"));rendered.rerender(view());
  await act(async()=>resolve(result(job("running",25,"2026-10-03T00:18:30Z"))));
  expect(screen.getByText("70%")).toBeVisible();expect(screen.queryByText("25%")).toBeNull();expect(screen.queryByText("30%")).toBeNull();
  expect(screen.getAllByText("阶段70").length).toBeGreaterThan(1);expect(screen.queryByText("阶段30")).toBeNull();
});
it("中断实时终态立即读取结果，旧运行中快照不能恢复任务",async()=>{
  const rendered=render(view());await waitFor(()=>expect(getJobResults).toHaveBeenCalledOnce());
  const interrupted=job("interrupted",40,"2026-10-03T00:21:00Z");
  vi.mocked(getJobResults).mockResolvedValue(result(interrupted));event(interrupted);rendered.rerender(view());
  await waitFor(()=>expect(getJobResults).toHaveBeenCalledTimes(2));
  polling(job("running",80,"2026-10-03T00:22:00Z"));rendered.rerender(view());
  await screen.findByText("最后记录进度：40%");expect(screen.queryByText("80%")).toBeNull();expect(getJobResults).toHaveBeenCalledTimes(2);
  expect(screen.queryByText("阶段80")).toBeNull();expect(screen.getAllByRole("button",{name:"重试任务"})).toHaveLength(1);
});
it("任务统计包含等待中和已中断数量",async()=>{
  render(view());await waitFor(()=>expect(getJobResults).toHaveBeenCalled());
  expect(screen.getByText("等待中").parentElement?.textContent).toContain("2");
  expect(screen.getByText("已中断").parentElement?.textContent).toContain("1");
});

it("完成事件读取新结果，不复用尚未返回的运行中请求",async()=>{
  let resolve!: (value:ReturnType<typeof result>)=>void;
  vi.mocked(getJobResults).mockImplementationOnce(()=>new Promise(done=>{resolve=done}));
  const rendered=render(view());await waitFor(()=>expect(getJobResults).toHaveBeenCalledOnce());
  const completed=job("completed",100,"2026-10-03T00:23:00Z");
  vi.mocked(getJobResults).mockResolvedValue({...result(completed),outputs:[{kind:"file",label:"完成后指标表",url:"/results/metrics.csv"}]});
  event(completed);rendered.rerender(view());
  await waitFor(()=>expect(getJobResults).toHaveBeenCalledTimes(2));
  await screen.findByText("完成后指标表");
  await act(async()=>resolve(result(job("running",25,"2026-10-03T00:18:30Z"))));
  expect(screen.getByText("完成后指标表")).toBeVisible();expect(screen.queryByText("25%")).toBeNull();
});

it("重试只提交一次，并打开响应中的新任务，旧失败任务保持可见",async()=>{
 const original=job("failed",35),fresh={...job("queued",0),id:"job-retried"};
 polling(original);vi.mocked(getJob).mockImplementation(async id=>({success:true,job:id==="job-retried"?fresh:original}));
 vi.mocked(getJobResults).mockImplementation(async id=>result(id==="job-retried"?fresh:original));
 let resolve!: (value:{success:boolean;job_id:string})=>void;
 vi.mocked(retryJob).mockImplementation(()=>new Promise(done=>{resolve=done}));
 render(view());await screen.findByText("最后记录进度：35%");
 const button=screen.getByRole("button",{name:"重试任务"});fireEvent.click(button);fireEvent.click(button);
 expect(retryJob).toHaveBeenCalledOnce();expect(button).toBeDisabled();
 await act(async()=>resolve({success:true,job_id:"job-retried"}));
 await waitFor(()=>expect(getJob).toHaveBeenCalledWith("job-retried"));
 await screen.findByText("尚未开始");
 expect(useJobEvents).toHaveBeenCalledWith("job-retried");
 expect(screen.getByRole("link",{name:"查看重试任务"})).toHaveAttribute("href","/analysis/script-hub/jobs?job=job-retried");
 expect(screen.getByRole("button",{name:"重试任务"})).toBeVisible();
});
it("重试请求失败仍保留旧任务并显示实际错误",async()=>{
 const original=job("failed",35);polling(original);vi.mocked(getJob).mockResolvedValue({success:true,job:original});vi.mocked(getJobResults).mockResolvedValue(result(original));
 vi.mocked(retryJob).mockRejectedValue(new Error("历史任务未保存完整参数，请从分析向导重新提交"));
 render(view());await screen.findByText("最后记录进度：35%");
 fireEvent.click(screen.getByRole("button",{name:"重试任务"}));
 await screen.findByText("历史任务未保存完整参数，请从分析向导重新提交");
 expect(getJob).not.toHaveBeenCalledWith("job-retried");expect(screen.getByRole("button",{name:"重试任务"})).toBeEnabled();
});

function LocationSnapshot() {
 const location=useLocation();
 return <output data-testid="monitor-url" aria-label="当前地址">{location.search + location.hash}</output>;
}
it("查看与返回保留过滤、页码和勾选，焦点恢复至查看按钮，关闭后旧结果不再更新详情",async()=>{
 let resolve!: (value:ReturnType<typeof result>)=>void;
 vi.mocked(getJobResults).mockImplementationOnce(()=>new Promise(done=>{resolve=done}));
 render(<MemoryRouter initialEntries={["/analysis/script-hub/jobs?status=running&q=病例&offset=50"]}><JobMonitor/><LocationSnapshot/></MemoryRouter>);
 const checkbox=screen.getByRole("checkbox",{name:"选择任务 job-1"});
 fireEvent.click(checkbox);
 const open=screen.getByRole("button",{name:"查看任务详情"});open.focus();fireEvent.click(open);
 await waitFor(()=>expect(getJobResults).toHaveBeenCalledOnce());
 expect(screen.getByRole("region",{name:"任务详情"})).toHaveFocus();
 expect(new URLSearchParams(screen.getByTestId("monitor-url").textContent||"").get("job")).toBe("job-1");
 fireEvent.click(screen.getByRole("button",{name:"返回任务列表"}));
 expect(open).toHaveFocus();expect(checkbox).toBeChecked();
 const query=new URLSearchParams(screen.getByTestId("monitor-url").textContent||"");
 expect(query.get("status")).toBe("running");expect(query.get("q")).toBe("病例");expect(query.get("offset")).toBe("50");expect(query.has("job")).toBe(false);
 await act(async()=>resolve(result(job("completed",100))));
 expect(screen.queryByRole("tab",{name:/^配置$/})).toBeNull();expect(useJobEvents).toHaveBeenLastCalledWith(null);
});
it("首次详情读取等待时可返回，迟到响应不能重新打开任务或继续读取结果",async()=>{
 let resolve!: (value:{success:boolean;job:JobSummary})=>void;
 vi.mocked(getJob).mockImplementationOnce(()=>new Promise(done=>{resolve=done}));
 vi.mocked(usePolling).mockReturnValue({data:{success:true,jobs:[],counts:{}},error:null,loading:false});
 render(view());
 await screen.findByText("正在读取任务详情…");
 fireEvent.click(screen.getByRole("button",{name:"返回任务列表"}));
 expect(screen.getByRole("region",{name:"任务列表"})).toHaveFocus();
 await act(async()=>resolve({success:true,job:job()}));
 expect(getJobResults).not.toHaveBeenCalled();expect(screen.queryByRole("tab",{name:/^配置$/})).toBeNull();
});
it("直接打开无效任务显示读取错误，重读有反馈，返回列表不依赖已加载详情",async()=>{
 vi.mocked(getJob).mockRejectedValueOnce(new Error("任务记录不存在"));
 render(view());
 await screen.findByText("任务记录不存在");
 const details=screen.getByRole("region",{name:"任务详情"});
 expect(within(details).getByRole("alert")).toHaveTextContent("任务信息读取失败");
 fireEvent.click(within(details).getByRole("button",{name:"重新读取任务"}));
 await screen.findByText("20%");expect(getJob).toHaveBeenCalledTimes(2);
 fireEvent.click(screen.getByRole("button",{name:"关闭任务详情"}));
 expect(screen.getByRole("region",{name:"任务列表"})).toHaveFocus();
});


it("真实任务缺失错误显示中文，停止未知任务事件，重新读取时恢复连接",async()=>{
 vi.mocked(getJob).mockRejectedValueOnce(new ApiError("Job not found",404,{error:"JOB_NOT_FOUND",message:"Job not found"}));
 render(view());
 await screen.findByText("无法找到该任务，请返回任务列表核对。");
 expect(screen.queryByText("Job not found")).toBeNull();
 expect(useJobEvents).toHaveBeenLastCalledWith(null);
 fireEvent.click(screen.getByRole("button",{name:"重新读取任务"}));
 await screen.findByText("20%");
 expect(useJobEvents).toHaveBeenLastCalledWith("job-1");expect(getJob).toHaveBeenCalledTimes(2);
});

it("带结果地址的中断任务打开结果分区，关闭详情保留列表条件并清除旧结果引用",async()=>{
 const snapshot=job("interrupted",35);
 vi.mocked(getJob).mockResolvedValue({success:true,job:snapshot});
 vi.mocked(getJobResults).mockResolvedValue({...result(snapshot),outputs:[{kind:"png",label:"已保存图表",url:"/saved.png"}]});
 polling(snapshot);
 const params=new URLSearchParams({job:"job-1",project:"project-a",q:"病例",offset:"50",result_job:"job-1",result_module:"profile",result_output:"profile:png:/saved.png:",result_section:"figures"});
 render(<MemoryRouter initialEntries={["/analysis/script-hub/jobs?"+params+"#results"]}><JobMonitor/><LocationSnapshot/></MemoryRouter>);
 expect(await screen.findByRole("img",{name:"已保存图表"})).toHaveAttribute("src","/saved.png");
 const before=new URL(screen.getByLabelText("当前地址").textContent!,"http://localhost");
 expect(before.hash).toBe("#results");
 expect(getJobResults).toHaveBeenCalledOnce();
 fireEvent.click(screen.getByRole("button",{name:"关闭任务详情"}));
 const after=new URL(screen.getByLabelText("当前地址").textContent!,"http://localhost");
 expect(after.searchParams.get("job")).toBeNull();
 expect(after.searchParams.get("result_job")).toBeNull();
 expect(after.searchParams.get("project")).toBe("project-a");
 expect(after.searchParams.get("q")).toBe("病例");
 expect(after.searchParams.get("offset")).toBe("50");
 expect(after.hash).toBe("#results");
});
