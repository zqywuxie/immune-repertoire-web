import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { JobDetailPanel } from "../features/jobs/JobDetailPanel";
import type { JobSummary } from "../shared/types/domain";
afterEach(cleanup);
it("取消中的进度详情保留实际进度和完整说明，历史阶段与时间使用中文",()=>{
  const detail="已请求取消，等待当前计算在检查点停止。停止之前请保留项目输入和任务目录。";
  const job={id:"cancel-detail",job_type:"script_hub",module:"umapin",status:"running",cancel_requested:true,progress:40,stage:"正在取消",detail,
    created_at:"2026-10-03T08:18:29Z",completed_at:null,payload:{history:[{progress:25,stage:"Running",detail:"Task started",timestamp:"08:18:29"}]}} as JobSummary;
  const view=render(<JobDetailPanel job={job} result={null} onClose={()=>{}}/>);
  expect(screen.getByText(detail)).toBeVisible();
  expect(screen.getByText("40%")).toBeVisible();
  expect(screen.getByText("结束时间")).toBeVisible();
  expect(screen.getByText("任务已开始执行。")).not.toBeVisible();
  fireEvent.click(screen.getByText("进度记录（最近 1 条变化）"));
  expect(screen.getByText("任务已开始执行。")).toBeVisible();
  expect(view.container.textContent).not.toMatch(/\b(?:AM|PM|Running|Task started)\b/);
  expect(screen.queryByText("100%")).toBeNull();
});
