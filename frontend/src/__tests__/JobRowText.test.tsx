import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { jobTextLabel } from "../shared/utils/analysisLabels";
import { JobRow } from "../features/jobs/JobRow";
import type { JobSummary } from "../shared/types/domain";
afterEach(cleanup);
it("历史组合任务的默认阶段显示中文，保留任务状态契约",()=>{
  const job={id:"batch-1",module:"analysis-batch",status:"completed",stage:"Completed",progress:100} as JobSummary;
  render(<JobRow job={job}/>);
  expect(screen.getByText("组合分析")).toBeTruthy();
  expect(screen.queryByText("Completed")).toBeNull();
  expect(screen.getAllByText("已完成")).toHaveLength(2);
});
it("历史等待提示显示中文，自定义分析阶段保留",()=>{
  const job={id:"job-1",module:"profile",status:"queued",stage:"Queued",detail:"Task created and waiting to start",progress:0} as JobSummary;
  const first=render(<JobRow job={job}/>);
  expect(screen.getByText("任务已创建，等待开始。")).toBeTruthy();
  expect(screen.queryByText("Queued")).toBeNull();first.unmount();
  render(<JobRow job={{...job,status:"running",stage:"正在计算 CDR3 特征"}}/>);
  expect(screen.getByText("正在计算 CDR3 特征")).toBeTruthy();
});

it("运行中取消请求保留进度，禁止重复取消、重试和删除",()=>{
  const job={id:"job-cancel",module:"umapin",status:"running",cancel_requested:true,stage:"正在取消",progress:25} as JobSummary;
  render(<JobRow job={job} onDelete={()=>{}}/>);
  expect(screen.getByRole("button",{name:"正在取消…"})).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("等待计算停止后可重试或删除任务。");
  expect(screen.queryByRole("button",{name:"重试任务"})).toBeNull();
  expect(screen.queryByRole("button",{name:"删除任务"})).toBeNull();
});

it("历史指标进度提示显示中文，保留字段名与自定义阶段",()=>{
  expect(jobTextLabel("BoxPlot analysis")).toBe("分组箱线图分析");
  expect(jobTextLabel("Processing group / TRB_Shannon")).toBe("正在分析：group / TRB_Shannon");
  expect(jobTextLabel("Generated 2 plot(s) — 1 comparison(s) skipped (groups need ≥2 data points)")).toBe("已生成 2 张图。已跳过 1 项比较：每组至少需要 2 个有效数据点。");
  expect(jobTextLabel("Profile generated 2 plots")).toBe("指标分析已完成，生成 2 张图。");
  expect(jobTextLabel("Starting with 3 columns")).toBe("已读取 3 列，开始核对分组与指标。");
  expect(jobTextLabel("读取 CDR3 与 V/J 特征")).toBe("读取 CDR3 与 V/J 特征");
});


it("列表显示保存的任务名称，并保留模块和任务编号用于区分同类分析",()=>{
 const job={id:"job-named-001",job_type:"api_request",module:"profile",status:"queued",payload:{_task_name:"治疗前 / 001 分组比较"},progress:0} as JobSummary;
 const original=JSON.stringify(job.payload);
 render(<JobRow job={job}/>);
 expect(screen.getByText("治疗前 / 001 分组比较",{selector:"strong"})).toBeVisible();
 expect(screen.getByText(/job-named-001/)).toHaveTextContent("组库指标与分组比较");
 expect(JSON.stringify(job.payload)).toBe(original);
});
