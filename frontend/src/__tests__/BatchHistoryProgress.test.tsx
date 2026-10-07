import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { JobDetailPanel } from "../features/jobs/JobDetailPanel";
import { BatchResultPanel } from "../features/jobs/BatchResultPanel";
import * as jobs from "../shared/api/jobs";
import type { JobResultsResponse } from "../shared/api/jobs";
type Detail = Awaited<ReturnType<typeof jobs.getJob>>;
const detail = (id:string,status:string,progress:number,stage="分析计算") =>
 ({success:true,job:{id,module:"profile",status,progress,stage,updated_at:"2026-10-03T01:00:00Z"}}) as Detail;
const batch = (id="batch",status="running",items=[
 {module:"profile",status:"running",job_id:"one"},
 {module:"volcano",status:"running",job_id:"two"}
])=>({success:true,job:{id,module:"analysis-batch",status,payload:{items}},status,result:{},outputs:[],assets:[]}) as unknown as JobResultsResponse;
const childResult = (id:string)=>({...batch(id,"completed"),job:detail(id,"completed",100).job});
const renderResult = (result:JobResultsResponse)=><p>已读取结果：{result.job.id}</p>;
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.useRealTimers();});
describe("历史批次子任务进度",()=>{
 it("刷新进入后显示全部子任务实际百分比与阶段，无需先选择结果",async()=>{
  vi.spyOn(jobs,"getJob").mockImplementation(async id=>id==="one"?detail(id,"running",35,"准备样本指标"):detail(id,"running",60,"计算差异表达"));
  render(<BatchResultPanel result={batch()} renderResult={renderResult}/>);
  const one=screen.getByRole("article",{name:"第 1 项 · 组库指标与分组比较"});
  const two=screen.getByRole("article",{name:"第 2 项 · 差异分析"});
  await act(async()=>{});
  expect(within(one).getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
  expect(within(two).getByRole("progressbar")).toHaveAttribute("aria-valuenow","60");
  expect(one).toHaveTextContent("准备样本指标");expect(two).toHaveTextContent("计算差异表达");
 });

 it("断线保留最后实际进度并恢复同一子任务，已终止子项不再轮询",async()=>{
  vi.useFakeTimers();let rounds=0;
  const get=vi.spyOn(jobs,"getJob").mockImplementation(async id=>{
   if(id==="one") return detail(id,"completed",100);
   rounds++;if(rounds===2)throw new Error("断线");
   return detail(id,rounds>=3?"failed":"running",35,"计算差异表达");
  });
  vi.spyOn(jobs,"getJobResults").mockResolvedValue(childResult("one"));
  render(<BatchResultPanel result={batch()} renderResult={renderResult}/>);
  await act(async()=>{});const two=screen.getByRole("article",{name:"第 2 项 · 差异分析"});
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
  expect(two).toHaveTextContent("此项进度暂时读取失败");
  expect(within(two).getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
  expect(two).toHaveTextContent("失败");expect(two).not.toHaveTextContent("暂时读取失败");
  expect(within(two).getByRole("progressbar")).toHaveAttribute("aria-valuenow","35");
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
  expect(get.mock.calls.filter(([id])=>id==="one")).toHaveLength(1);
  expect(get.mock.calls.filter(([id])=>id==="two")).toHaveLength(3);
 });
 it("终态批次读取全部子项一次，单项错误可手动重读且不影响成功结果",async()=>{
  vi.useFakeTimers();let fail=true;
  const get=vi.spyOn(jobs,"getJob").mockImplementation(async id=>{
   if(id==="two"&&fail)throw new Error("读取失败");
   return detail(id,"completed",100);
  });
  vi.spyOn(jobs,"getJobResults").mockResolvedValue(childResult("one"));
  const items=[{module:"profile",status:"completed",job_id:"one"},{module:"volcano",status:"completed",job_id:"two"}];
  render(<BatchResultPanel result={batch("batch","completed",items)} renderResult={renderResult}/>);
  await act(async()=>{});expect(screen.getByText("已读取结果：one")).toBeInTheDocument();
  const one=screen.getByRole("article",{name:"第 1 项 · 组库指标与分组比较"});
  expect(within(one).getByRole("progressbar")).toHaveAttribute("aria-valuenow","100");
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
  expect(get.mock.calls.filter(([id])=>id==="two")).toHaveLength(1);
  fail=false;await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"重新读取此项"}));});
  const two=screen.getByRole("article",{name:"第 2 项 · 差异分析"});
  expect(within(two).getByRole("progressbar")).toHaveAttribute("aria-valuenow","100");
  expect(two).not.toHaveTextContent("暂时读取失败");
  expect(screen.getByText("已读取结果：one")).toBeInTheDocument();
  expect(get.mock.calls.filter(([id])=>id==="two")).toHaveLength(2);
 });
 it("切换批次忽略旧响应，关闭页面后停止继续读取",async()=>{
  vi.useFakeTimers();let resolve!:(value:Detail)=>void;
  const get=vi.spyOn(jobs,"getJob").mockImplementation(async id=>{
   if(id==="one")return new Promise<Detail>(done=>{resolve=done;});
   return detail(id,"running",70,"新批次计算");
  });
  const view=render(<BatchResultPanel result={batch("old","running",[{module:"profile",status:"running",job_id:"one"}])} renderResult={renderResult}/>);
  await act(async()=>{});
  view.rerender(<BatchResultPanel result={batch("new","running",[{module:"profile",status:"running",job_id:"new-child"}])} renderResult={renderResult}/>);
  await act(async()=>{});
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","70");
  await act(async()=>{resolve(detail("one","running",10,"旧批次计算"));});
  expect(screen.queryByText("旧批次计算")).not.toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","70");
  view.unmount();const count=get.mock.calls.length;
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
  expect(get).toHaveBeenCalledTimes(count);
 });
 it("父任务结束时重新读取真实终态，不采用仍在传输的旧快照",async()=>{
  vi.useFakeTimers();let resolve!:(value:Detail)=>void;let calls=0;
  const get=vi.spyOn(jobs,"getJob").mockImplementation(async id=>{
   calls++;if(calls===1)return new Promise<Detail>(done=>{resolve=done;});
   return detail(id,"completed",100,"已完成");
  });
  const view=render(<BatchResultPanel result={batch("batch","running",[{module:"profile",status:"running",job_id:"one"}])} renderResult={renderResult}/>);
  await act(async()=>{});
  vi.spyOn(jobs,"getJobResults").mockResolvedValue(childResult("one"));
  view.rerender(<BatchResultPanel result={batch("batch","completed",[{module:"profile",status:"completed",job_id:"one"}])} renderResult={renderResult}/>);
  await act(async()=>{});
  expect(get).toHaveBeenCalledWith("one",{forceFresh:true});
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","100");
  await act(async()=>{resolve(detail("one","running",20,"旧进度"));});
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","100");
  expect(screen.queryByText("旧进度")).not.toBeInTheDocument();
 });
 it("手动重读结果优先于迟到失败，原有读数不会回退",async()=>{
  vi.useFakeTimers();let reject!:(reason:Error)=>void;let calls=0;
  vi.spyOn(jobs,"getJob").mockImplementation(async id=>{
   calls++;if(calls===1)return detail(id,"running",35);
   if(calls===2)throw new Error("断线");
   if(calls===3)return new Promise<Detail>((_,fail)=>{reject=fail;});
   return detail(id,"running",60,"恢复计算");
  });
  render(<BatchResultPanel result={batch("batch","running",[{module:"profile",status:"running",job_id:"one"}])} renderResult={renderResult}/>);
  await act(async()=>{});await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
  await act(async()=>{fireEvent.click(screen.getByRole("button",{name:"重新读取此项"}));});
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","60");
  await act(async()=>{reject(new Error("旧请求失败"));});
  expect(screen.queryByText(/此项进度暂时读取失败/)).not.toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow","60");
 });
 it("失败子任务直接展示实际错误，未提交依赖项不请求虚构编号",async()=>{
  vi.useFakeTimers();
  const get=vi.spyOn(jobs,"getJob").mockResolvedValue({success:true,job:{...detail("one","failed",35).job,error:"输入样本未匹配"}} as Detail);
  render(<BatchResultPanel result={batch("batch","failed",[{module:"profile",status:"failed",job_id:"one"},{module:"volcano",status:"failed",job_id:"",depends_on:[0],blocked_by:[0]}] as never)} renderResult={renderResult}/>);
  await act(async()=>{});
  expect(screen.getByText("输入样本未匹配")).toBeInTheDocument();
  expect(screen.getByText(/前置分析未成功完成，未执行此项/)).toBeInTheDocument();
  expect(get).toHaveBeenCalledTimes(1);
  expect(screen.getAllByRole("progressbar")).toHaveLength(1);
 });

 it("历史任务默认进度页签展示子项，切换结果页签保留快照且不重复轮询",async()=>{
  vi.useFakeTimers();
  const get=vi.spyOn(jobs,"getJob").mockImplementation(async id=>detail(id,"running",id==="one"?35:60));
  const parent=batch();
  render(<JobDetailPanel job={parent.job} result={parent} onClose={vi.fn()}/>);
  await act(async()=>{});
  expect(screen.getByRole("tab",{name:"进度"})).toHaveAttribute("aria-selected","true");
  const cards=screen.getByRole("region",{name:"逐项分析进度"});
  expect(within(cards).getAllByRole("progressbar").map(bar=>bar.getAttribute("aria-valuenow"))).toEqual(["35","60"]);
  expect(get).toHaveBeenCalledTimes(2);
  await act(async()=>{fireEvent.click(screen.getByRole("tab",{name:"结果"}));});
  expect(within(screen.getByRole("region",{name:"逐项分析进度"})).getAllByRole("progressbar").map(bar=>bar.getAttribute("aria-valuenow"))).toEqual(["35","60"]);
  expect(get).toHaveBeenCalledTimes(2);
 });

});
