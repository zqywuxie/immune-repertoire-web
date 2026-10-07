import { useState } from "react";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Stage4Execution } from "../features/scripthub/stages/Stage4Execution";
import * as jobs from "../shared/api/jobs";
import * as scripts from "../shared/api/scriptHub";

beforeEach(() => {
  vi.useFakeTimers();
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

const task = (status = "running", progress = 35) => ({
  success: true, job_id: "task-one", task_id: "task-one", module: "umapin",
  status, progress, stage: "正在核对选中样本",
});
const result = () => ({
  success: true, job: {id: "task-one", module: "diversity", status: "completed"},
  status: "completed", outputs: [{kind: "csv", label: "原始指标", url: "/results/data.csv"}],
  assets: [], result: {},
} as unknown as jobs.JobResultsResponse);

function setup(mode: "legacy" | "modern", read?: () => Promise<unknown>) {
  const complete = vi.fn(), running = vi.fn(), created = vi.fn();
  const submit = mode === "legacy"
    ? vi.spyOn(scripts, "submitLegacyScriptHubJob").mockResolvedValue({success: true, job_id: "task-one", task_id: "task-one", status: "queued"})
    : vi.spyOn(jobs, "submitJob").mockResolvedValue({success: true, job_id: "task-one", status: "queued"});
  const poll = mode === "legacy"
    ? vi.spyOn(scripts, "getLegacyScriptHubTask")
    : vi.spyOn(jobs, "getJob");
  if (read) poll.mockImplementation(read as never);
  vi.spyOn(jobs, "getJobResults").mockResolvedValue(result());
  function Run() {
    const [ids, setIds] = useState<string[]>([]);
    return <Stage4Execution projectId="project-one" modules={[mode === "legacy" ? "umapin" : "diversity"]}
      baseConfig={{asset_set: "Set2"}} moduleConfigs={{umapin: {category_col: "Category", upstream_artifact_id: "source-one"}}}
      jobIds={ids} onJobsCreated={ids => {created(ids); setIds(ids);}} onComplete={complete} onRunningChange={running} />;
  }
  return {...render(<Run/>), complete, running, created, submit, poll};
}
async function start() {
  await act(async () => { fireEvent.click(screen.getByRole("button", {name: "开始分析"})); });
}
async function tick() {
  await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
}

it.each(["legacy", "modern"] as const)("%s 暂时断开后恢复同一任务，保留进度且仅提交一次", async mode => {
  const view = setup(mode);
  const snapshot = (status = "running") => mode === "legacy" ? task(status) : {success: true, job: {...task(status), id: "task-one"}};
  view.poll.mockResolvedValueOnce(snapshot() as never)
    .mockRejectedValueOnce(new Error("合成网络断开"))
    .mockRejectedValueOnce(new Error("合成网络断开"))
    .mockResolvedValue(snapshot("completed") as never);
  await start();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "35");
  await tick();
  expect(screen.getByRole("status", {name: "任务状态连接"})).toHaveTextContent("正在重新读取");
  expect(screen.getByRole("status", {name: "任务状态连接"})).toHaveTextContent("最后读取时间");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "35");
  expect(screen.getByText("正在核对选中样本")).toBeInTheDocument();
  expect(view.running).toHaveBeenLastCalledWith(true);
  expect(view.complete).not.toHaveBeenCalled();
  await tick();
  expect(screen.getByText(/执行日志（最近/).closest("details")!.querySelector("pre")!.textContent!.split("状态连接中断，等待重连。")).toHaveLength(2);
  await tick();
  expect(view.complete).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("status", {name: "任务状态连接"})).toBeNull();
  expect(view.submit).toHaveBeenCalledTimes(1);
  expect(view.running).toHaveBeenLastCalledWith(false);
  const calls = view.poll.mock.calls.length;
  await tick();
  expect(view.poll).toHaveBeenCalledTimes(calls);
});

it("通用任务已完成但结果读取暂时失败时只重读结果，不重新计算", async () => {
  const view = setup("modern");
  view.poll.mockResolvedValue({success: true, job: {...task("completed", 100), id: "task-one"}} as never);
  vi.mocked(jobs.getJobResults).mockRejectedValueOnce(new Error("结果服务暂不可用")).mockResolvedValue(result());
  await start();
  expect(view.complete).not.toHaveBeenCalled();
  expect(screen.getByRole("status", {name: "任务状态连接"})).toHaveTextContent("正在重新读取");
  await tick();
  expect(view.complete).toHaveBeenCalledTimes(1);
  expect(view.complete.mock.calls[0][0]["task-one"].outputs[0].url).toBe("/results/data.csv");
  expect(jobs.getJobResults).toHaveBeenCalledTimes(2);
  expect(view.poll).toHaveBeenCalledTimes(1);
  expect(view.submit).toHaveBeenCalledTimes(1);
});

it.each(["legacy", "modern"] as const)("%s 离页时忽略正在返回的状态并停止后续读取", async mode => {
  let resolve!: (value: unknown) => void;
  const pending = new Promise(done => {resolve = done;});
  const view = setup(mode, () => pending);
  await start();
  expect(view.poll).toHaveBeenCalledTimes(1);
  view.unmount();
  await act(async () => {resolve(mode === "legacy" ? task("completed") : {success: true, job: {...task("completed"), id: "task-one"}});});
  await tick();
  expect(view.poll).toHaveBeenCalledTimes(1);
  expect(view.complete).not.toHaveBeenCalled();
  expect(jobs.getJobResults).not.toHaveBeenCalled();
  expect(view.running).toHaveBeenCalledTimes(1);
});

it.each(["legacy", "modern"] as const)("%s 重连等待期间离页后不发出新的轮询", async mode => {
  const view = setup(mode);
  view.poll.mockRejectedValue(new Error("合成网络断开"));
  await start();
  expect(screen.getByRole("status", {name: "任务状态连接"})).toBeInTheDocument();
  view.unmount();
  await tick();
  expect(view.poll).toHaveBeenCalledTimes(1);
  expect(view.complete).not.toHaveBeenCalled();
  expect(view.submit).toHaveBeenCalledTimes(1);
});

it("已不存在的任务给出原始错误，不无限重连或重新提交", async () => {
  const view = setup("legacy");
  view.poll.mockRejectedValue(Object.assign(new Error("任务已不存在"), {status: 404}));
  await start();
  expect(screen.getByText("任务已不存在")).toBeInTheDocument();
  expect(screen.queryByRole("status", {name: "任务状态连接"})).toBeNull();
  await tick();
  expect(view.poll).toHaveBeenCalledTimes(1);
  expect(view.submit).toHaveBeenCalledTimes(1);
  expect(view.complete).not.toHaveBeenCalled();
});

it("断线后确认任务不存在时清除重连提示，保留原始错误", async () => {
  const view = setup("legacy");
  view.poll.mockRejectedValueOnce(new Error("合成断线"))
    .mockRejectedValue(Object.assign(new Error("任务已不存在"), {status: 404}));
  await start();
  expect(screen.getByRole("status", {name: "任务状态连接"})).toBeInTheDocument();
  await tick();
  expect(screen.queryByRole("status", {name: "任务状态连接"})).toBeNull();
  expect(screen.getByText("任务已不存在")).toBeInTheDocument();
  await tick();
  expect(view.poll).toHaveBeenCalledTimes(2);
  expect(view.submit).toHaveBeenCalledTimes(1);
});

it("旧默认阶段采用中文标签，任务地址保留完整编号", async () => {
  const view = setup("legacy");
  view.poll.mockResolvedValue({...task("queued", 0), stage: "Queued"} as never);
  await start();
  expect(screen.getByText("等待执行", {selector: "div"})).toBeInTheDocument();
  expect(screen.queryByText("Queued", {exact: true})).toBeNull();
  expect(screen.getByRole("link", {name: "查看任务"})).toHaveAttribute("href", "/analysis/script-hub/jobs?job=task-one");
  view.unmount();
  await tick();
  expect(view.poll).toHaveBeenCalledTimes(1);
});
