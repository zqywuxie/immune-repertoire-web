import * as jobsApi from "../shared/api/jobs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { Stage4Execution } from "../features/scripthub/stages/Stage4Execution";
import { Stage5Results } from "../features/scripthub/stages/Stage5Results";
import { BatchStatus } from "../features/jobs/BatchStatus";
import * as api from "../shared/api/scriptHub";
import type { JobResultsResponse } from "../shared/api/jobs";
vi.mock("../features/results/ContinueAnalysis", () => ({ContinueAnalysis: () => null}));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe("批次和执行进度", () => {
  it("多个模块只提交一次服务端计划，并读取全部子结果", async () => {
    const submit = vi.spyOn(api,"submitAnalysisBatch").mockResolvedValue({success:true,job_id:"batch",status:"queued"});
    const oldSubmit = vi.spyOn(api,"submitLegacyScriptHubJob");
    const items = [{job_id:"child1",module:"umapin",status:"completed"},{job_id:"child2",module:"volcano",status:"completed"}];
    vi.spyOn(jobsApi,"getJob").mockResolvedValue({success:true,job:{id:"batch",status:"completed",payload:{items}}} as unknown as Awaited<ReturnType<typeof jobsApi.getJob>>);
    vi.spyOn(jobsApi,"getJobResults").mockImplementation(async id => ({success:true,job:{id},status:"completed",outputs:[],assets:[],result:{}} as unknown as JobResultsResponse));
    const complete = vi.fn(); const batchCreated=vi.fn();
    render(<Stage4Execution projectId="project" modules={["umapin","volcano"]} baseConfig={{asset_set:"Set2"}} moduleConfigs={{umapin:{category_col:"Category",upstream_artifact_id:"one"},volcano:{input_mode:"usage",upstream_artifact_id:"two"}}} jobIds={[]} onJobsCreated={vi.fn()} onComplete={complete} onBatchCreated={batchCreated}/>);
    fireEvent.click(screen.getByRole("button",{name:"运行所选模块"}));
    await waitFor(() => expect(complete).toHaveBeenCalled());
    expect(submit).toHaveBeenCalledTimes(1);
    expect(submit.mock.calls[0][3].map(item=>item.module)).toEqual(["umapin","volcano"]);
    expect(oldSubmit).not.toHaveBeenCalled();
    expect(batchCreated).toHaveBeenCalledWith("batch");
    expect(Object.keys(complete.mock.calls[0][0])).toEqual(["child1","child2"]);
  });

  it("只有部分结果返回时不宣称整批完成", () => {
    const result = {job: {id: "one", module: "profile"},status: "completed",outputs: [],result: {},assets: [],success: true} as unknown as JobResultsResponse;
    render(<Stage5Results jobIds={["one"]} expectedCount={3} resultsByJobId={{one: result}} onReset={vi.fn()} />);
    expect(screen.getByRole("status", {name: "批次进度"})).toHaveTextContent("分析进行中");
    expect(screen.getByRole("status", {name: "批次进度"})).toHaveTextContent("已完成 1/3 个任务");
    expect(screen.queryByText("分析完成")).not.toBeInTheDocument();
  });
  it("部分成功与取消、中断分别展示", () => {
    render(<BatchStatus statuses={["completed", "interrupted", "cancelled", "failed"]} expectedCount={4} />);
    expect(screen.getByRole("status")).toHaveTextContent("部分分析完成");
    expect(screen.getByRole("status")).toHaveTextContent("失败 1 项 · 已取消 1 项 · 已中断 1 项");
    expect(screen.queryByText("分析进行中")).not.toBeInTheDocument();
  });
  it("允许只提交产物标识，遇到中断立即结束轮询", async () => {
    const submit = vi.spyOn(api, "submitLegacyScriptHubJob").mockResolvedValue({success: true,job_id: "task",task_id: "task",status: "queued"});
    const poll = vi.spyOn(api, "getLegacyScriptHubTask").mockResolvedValue({success: true,job_id: "task",task_id: "task",module: "umapin",status: "interrupted"});
    const complete = vi.fn();
    render(<Stage4Execution projectId="project" modules={["umapin"]} baseConfig={{asset_set:"Set2"}} moduleConfigs={{umapin:{category_col:"Category",upstream_artifact_id:"source:table:1"}}} jobIds={[]} onJobsCreated={vi.fn()} onComplete={complete} />);
    fireEvent.click(screen.getByRole("button",{name:"开始分析"}));
    await waitFor(() => expect(complete).toHaveBeenCalledTimes(1));
    expect(complete.mock.calls[0][0].task.status).toBe("interrupted");
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({payload:expect.objectContaining({upstream_artifact_id:"source:table:1"})}));
    expect(poll).toHaveBeenCalledTimes(1);
  });
  it("重复状态只记录一次，日志默认折叠", async () => {
    vi.useFakeTimers();
    vi.spyOn(api, "submitLegacyScriptHubJob").mockResolvedValue({success:true,job_id:"task",task_id:"task",status:"queued"});
    const waiting: api.ScriptHubTaskStatusResponse = {success:true,job_id:"task",task_id:"task",module:"umapin",status:"queued",progress:0,stage:"等待计算"};
    vi.spyOn(api,"getLegacyScriptHubTask").mockResolvedValueOnce(waiting).mockResolvedValueOnce(waiting).mockResolvedValue({...waiting,status:"interrupted"});
    function Run() {
      const [ids,setIds] = useState<string[]>([]);
      return <Stage4Execution projectId="project" modules={["umapin"]} baseConfig={{}} moduleConfigs={{umapin:{category_col:"Category",upstream_artifact_id:"source"}}} jobIds={ids} onJobsCreated={setIds} onComplete={vi.fn()} />;
    }
    render(<Run/>);
    await act(async () => { fireEvent.click(screen.getByRole("button",{name:"开始分析"})); });
    await act(async () => { await vi.advanceTimersByTimeAsync(3100); });
    const details = screen.getByText(/执行日志（最近/).closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(details.querySelector("pre")!.textContent!.split("等待中 0% 等待计算")).toHaveLength(2);
  });
});


it.each([["pep-analysis", "umapin"], ["umapin", "pep-analysis"]])("选择顺序 %s、%s 自动调整依赖且无需缓存路径", async (first, second) => {
  const submit = vi.spyOn(api, "submitAnalysisBatch").mockRejectedValue(new Error("测试停止提交"));
  render(<Stage4Execution projectId="project" modules={[first, second]}
    baseConfig={{asset_set: "Set2"}}
    moduleConfigs={{"pep-analysis": {group_fields: ["group"], selected_group_values: {group: ["A", "B"]}, selected_samples_by_group: {group: {A: ["A1"], B: ["B1"]}}}, umapin: {category_col: "Category"}}}
    jobIds={[]} onJobsCreated={vi.fn()} onComplete={vi.fn()} />);
  fireEvent.change(screen.getByRole("combobox"), {target: {value: "batch"}});
  expect(screen.getByText(/链和分组须与前序设置一致/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "运行所选模块"}));
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
  expect(submit.mock.calls[0][3].map(item => item.module)).toEqual(["pep-analysis", "umapin"]);
  expect(submit.mock.calls[0][3][1]).toMatchObject({module: "umapin", upstream_from: 0, depends_on: [0]});
  expect(submit.mock.calls[0][3][1].payload.upstream_artifact_id).toBeUndefined();
});

it.each([["volcano", "go-kegg-enrichment"], ["go-kegg-enrichment", "volcano"]])("差异与富集选择顺序 %s、%s 正确绑定本批次来源", async (first, second) => {
  const submit = vi.spyOn(api, "submitAnalysisBatch").mockRejectedValue(new Error("测试停止提交"));
  render(<Stage4Execution projectId="project" modules={[first, second]} baseConfig={{asset_set: "Set2"}}
    moduleConfigs={{volcano: {input_mode: "expression"}, "go-kegg-enrichment": {input_mode: "deg", upstream_artifact_id: "old:deg", expression_path: "/old.csv"}}}
    jobIds={[]} onJobsCreated={vi.fn()} onComplete={vi.fn()} />);
  fireEvent.change(screen.getByRole("combobox"), {target: {value: "batch"}});
  expect(screen.getByText(/不重复计算差异/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name: "运行所选模块"}));
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
  const items = submit.mock.calls[0][3];
  expect(items.map(item => item.module)).toEqual(["volcano", "go-kegg-enrichment"]);
  expect(items[1]).toMatchObject({upstream_from: 0, depends_on: [0], payload: {input_mode: "deg"}});
  expect(items[1].payload.upstream_artifact_id).toBeUndefined();
  expect(items[1].payload.expression_path).toBeUndefined();
});

it("V/J 使用差异不能作为基因富集的批次来源", () => {
  render(<Stage4Execution projectId="project" modules={["volcano", "go-kegg-enrichment"]} baseConfig={{}}
    moduleConfigs={{volcano: {input_mode: "usage"}}} jobIds={[]} onJobsCreated={vi.fn()} onComplete={vi.fn()} />);
  expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
});
