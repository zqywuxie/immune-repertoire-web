import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { JobDetailPanel } from "../features/jobs/JobDetailPanel";
import type { JobSummary } from "../shared/types/domain";
const job = (extra: Partial<JobSummary> = {}) => ({id:"progress-job", job_type:"api_request", module:"statistical.analyze", status:"running", progress:35,
 stage:"计算分组比较", started_at:"2026-10-03T00:00:00Z", created_at:"2026-10-03T00:00:00Z", ...extra}) as JobSummary;
afterEach(()=>{cleanup();vi.useRealTimers();});
it("已耗时按实际开始时间更新，终态按结束时间冻结，不生成剩余时间",()=>{
 vi.useFakeTimers();vi.setSystemTime(new Date("2026-10-03T00:00:03Z"));
 const view=render(<JobDetailPanel job={job()} result={null} onClose={()=>{}}/>);
 expect(screen.getByText("3秒")).toBeVisible();
 act(()=>vi.advanceTimersByTime(2000));expect(screen.getByText("5秒")).toBeVisible();
 view.rerender(<JobDetailPanel job={job({status:"failed",completed_at:"2026-10-03T00:00:05Z",error:"输入缺少分组"})} result={null} onClose={()=>{}}/>);
 act(()=>vi.advanceTimersByTime(5000));expect(screen.getByText("5秒")).toBeVisible();
 expect(screen.queryByText("10秒")).toBeNull();expect(screen.getByText("最后记录进度：35%")).toBeVisible();
});
it("技术错误默认折叠，原始错误与失败前阶段仍可查看",()=>{
 const raw="Traceback (most recent call last):\n  File /app/analysis.py\nValueError: synthetic input";
 render(<JobDetailPanel job={job({status:"failed",error:"缺少对照组",detail:raw,payload:{history:[{stage:"核对样本",progress:35,detail:"有效样本 3",timestamp:"2026-10-03T00:00:02Z"}]}})} result={null} onClose={()=>{}}/>);
 expect(screen.getByRole("alert")).toHaveTextContent("按原参数重试会创建新任务");
 expect(screen.getByRole("link",{name:"进入分析中心"})).toHaveAttribute("href","/analysis/center");
 expect(screen.getByText(/ValueError: synthetic input/)).not.toBeVisible();
 expect(screen.getByText("核对样本")).not.toBeVisible();
 fireEvent.click(screen.getByText("错误与技术详情"));expect(screen.getByText(/ValueError: synthetic input/)).toBeVisible();
 fireEvent.click(screen.getByText("进度记录（最近 1 条变化）"));expect(screen.getByText("核对样本")).toBeVisible();
});
it("历史记录只显示最近20次变化，连续同内容保留最新时间，展开状态不被轮询重置",()=>{
 const history=Array.from({length:25},(_,index)=>({stage:"阶段"+index,progress:index,detail:"内容"+index,timestamp:"2026-10-03T00:00:01Z"}));
 history.push({...history.at(-1)!,timestamp:"2026-10-03T00:00:02Z"});
 const snapshot=job({payload:{history}});
 const view=render(<JobDetailPanel job={snapshot} result={null} onClose={()=>{}}/>);
 expect(screen.getByText("进度记录（最近 20 条变化）")).toBeVisible();expect(screen.queryByText("阶段4")).toBeNull();
 expect(screen.getByText("阶段24")).not.toBeVisible();fireEvent.click(screen.getByText("进度记录（最近 20 条变化）"));
 expect(screen.getAllByText("阶段24")).toHaveLength(1);expect(screen.getByText("阶段24")).toBeVisible();
 view.rerender(<JobDetailPanel job={{...snapshot,progress:40}} result={null} onClose={()=>{}}/>);expect(screen.getByText("阶段24")).toBeVisible();
 view.rerender(<JobDetailPanel job={{...snapshot,id:"different-job"}} result={null} onClose={()=>{}}/>);expect(screen.getByText("阶段24")).not.toBeVisible();
});
it("排队或缺失时间记录不会制造运行时长，异常百分比不输出NaN",()=>{
 const view=render(<JobDetailPanel job={job({status:"queued",started_at:null})} result={null} onClose={()=>{}}/>);expect(screen.getByText("尚未开始")).toBeVisible();
 view.rerender(<JobDetailPanel job={job({status:"failed",completed_at:null,progress:Number.NaN})} result={null} onClose={()=>{}}/>);
 expect(screen.getByText("未记录结束时间")).toBeVisible();expect(screen.getByText("尚未记录百分比，请以实际阶段为准。")).toBeVisible();
 expect(screen.queryByRole("progressbar")).toBeNull();
});
