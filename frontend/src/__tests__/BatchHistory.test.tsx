import {afterEach, describe, expect, it, vi} from "vitest";
import {act, cleanup, render, renderHook, screen} from "@testing-library/react";
import {BatchResultPanel} from "../features/jobs/BatchResultPanel";
import {Stage5Results} from "../features/scripthub/stages/Stage5Results";
import {useJobResult} from "../shared/hooks/useJobResult";
import * as jobs from "../shared/api/jobs";
import type {JobResultsResponse} from "../shared/api/jobs";
const snapshot=(status:string)=>({success:true,job:{id:"batch",module:"analysis-batch",status,payload:{items:[{module:"profile",status:"completed",job_id:"child"},{module:"umapin",status:"failed",error:"分组列缺失"},{module:"volcano",status:"cancelled"}]}},status,result:{},outputs:[],assets:[]}) as unknown as JobResultsResponse;
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.useRealTimers();});
describe("批次历史与恢复",()=>{
 it("失败批次保留成功子结果，并展示没有编号的失败项目",async()=>{
  vi.spyOn(jobs,"getJob").mockResolvedValue({success:true,job:{id:"child",module:"profile",status:"completed"}} as Awaited<ReturnType<typeof jobs.getJob>>);
  vi.spyOn(jobs,"getJobResults").mockResolvedValue({...snapshot("completed"),job:{...snapshot("completed").job,id:"child",module:"profile"}});
  render(<BatchResultPanel result={snapshot("failed")} renderResult={child=><p>已读取结果：{child.job.id}</p>}/>);
  expect(screen.getByText("部分分析完成")).toBeInTheDocument();
  expect(screen.getByText("分组列缺失")).toBeInTheDocument();
  expect(await screen.findByText("已读取结果：child")).toBeInTheDocument();
 });
 it("无子结果编号的全部失败也显示结束而非无限等待",()=>{
  render(<Stage5Results jobIds={[]} resultsByJobId={{}} expectedCount={2} batchStatuses={["failed","cancelled"]} onReset={vi.fn()}/>);
  expect(screen.getByRole("status",{name:"批次进度"})).toHaveTextContent("分析已结束");
  expect(screen.queryByText("等待分析结果…")).not.toBeInTheDocument();
 });
 it("断线保留批次快照，自动恢复并在终态停止查询",async()=>{
  vi.useFakeTimers();
  const get=vi.spyOn(jobs,"getJob").mockResolvedValueOnce({success:true,job:snapshot("running").job}).mockRejectedValueOnce(new Error("断线")).mockResolvedValue({success:true,job:snapshot("failed").job});
  const hook=renderHook(()=>useJobResult("batch"));
  await act(async()=>{});
  expect(hook.result.current.result?.status).toBe("running");
  await act(async()=>{await vi.advanceTimersByTimeAsync(1500);});
  expect(hook.result.current.error).toContain("正在重连");
  expect(hook.result.current.result?.status).toBe("running");
  await act(async()=>{await vi.advanceTimersByTimeAsync(3000);});
  expect(hook.result.current.result?.status).toBe("failed");
  expect(hook.result.current.error).toBe("");
  await act(async()=>{await vi.advanceTimersByTimeAsync(10000);});
  expect(get).toHaveBeenCalledTimes(3);
 });
});
