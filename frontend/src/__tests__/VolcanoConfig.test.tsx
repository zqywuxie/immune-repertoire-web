import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VolcanoConfig } from "../features/scripthub/modules/VolcanoConfig";
import { configurationIssue } from "../features/scripthub/configurationValidation";
import { submitLegacyScriptHubJob } from "../shared/api/scriptHub";
const source = { projectId: "synthetic", assetSetId: "Set2", profilePath: "/data/profile.csv", transcriptomePath: "/data/expression.csv", pepPaths: [],
  sampleNames: [], chains: ["TRB"], profileFields: ["sample", "group"], groupFields: ["group"], pepColumns: [] };
const candidates = ["one", "two"].map(id => ({ id, artifact_id: id, path: `/results/${id}/1VJusage`, job_id: `source-${id}`, status: "available" }));
const inspected = { success: true, data_dir: candidates[0].path, file_count: 1, sample_count: 6,
  groups: ["01", "02"], samples_by_value: { "01": ["甲::001", "甲::002", "乙::001", "乙::002"], "02": ["甲::003", "乙::003"] },
  suggested_comparisons: [{ group1: "01", group2: "02" }] };
const reply = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
const initial = { input_mode: "usage", upstream_artifact_id: "one" };
function Harness({ value = initial, observe = vi.fn() }: { value?: Record<string, unknown>; observe?: (next: Record<string, unknown>) => void }) {
  const [current, setCurrent] = useState<Record<string, unknown>>(value);
  return <VolcanoConfig projectId="synthetic" module="volcano" groupSpecs={[]} loadingSpecs={false} sourceContext={source}
    value={current} onChange={next => { setCurrent(next); observe(next); }} />;
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function installFetch() {
  const fetchMock = vi.fn(async (url: unknown, init?: RequestInit) => reply(String(url).includes("pep-cache-candidates")
    ? { success: true, candidates } : String(url).endsWith("/inspect")
      ? JSON.parse(String(init?.body)).input_mode === "expression" ? { success: true, groups: ["A", "B"], suggested_comparisons: [{ group1: "A", group2: "B" }] } : inspected
      : { success: true, task_id: "synthetic-job" }));
  vi.stubGlobal("fetch", fetchMock); return fetchMock;
}
describe("V/J 差异分析的真实输入交互", () => {
  it("uses actual batch samples, preserves explicit empty comparisons and submits artifact identity", async () => {
    const fetchMock = installFetch(), observe = vi.fn(); render(<Harness observe={observe} />);
    for (const name of ["01 / 甲 / 001", "01 / 甲 / 002", "02 / 甲 / 003"]) fireEvent.click(await screen.findByRole("button", { name }));
    expect(observe.mock.calls.at(-1)?.[0].selected_samples).toEqual(["乙::001", "乙::002", "乙::003"]);
    expect(screen.getByText(/按原始 P 值判定显著性/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "01 与 02" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "01 与 02" }));
    expect(observe.mock.calls.at(-1)?.[0].comparisons).toEqual([]);
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "样本差异" } });
    expect(screen.getByRole("button", { name: "01 与 02" })).toHaveAttribute("aria-pressed", "false");
    await submitLegacyScriptHubJob({ module: "volcano", projectId: "synthetic", payload: { ...observe.mock.calls.at(-1)?.[0], asset_set: "Set2",
      selected_group_values: { group: ["A"] }, selected_samples_by_group: { group: { A: ["001"] } } } });
    const submitted = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(submitted).toMatchObject({ upstream_artifact_id: "one", selected_samples: ["乙::001", "乙::002", "乙::003"], comparisons: [] });
    expect(submitted.data_dir).toBeUndefined(); expect(submitted.selected_samples_by_group).toBeUndefined(); expect(submitted.selected_group_values).toBeUndefined();
    const inspections = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/inspect"));
    expect(inspections).toHaveLength(1);
    expect(JSON.parse(String(inspections[0][1]?.body))).toMatchObject({ input_mode: "usage", asset_set: "Set2", upstream_artifact_id: "one" });
  });
  it("swaps comparison direction without changing the selected cohort", async () => {
    installFetch(); const observe = vi.fn(); render(<Harness observe={observe} />);
    fireEvent.click(await screen.findByRole("button", { name: "交换 01 与 02 的比较方向" }));
    expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({ comparisons: [["02", "01"]], selected_samples: Object.values(inspected.samples_by_value).flat() });
    expect(screen.getByRole("button", { name: "02 与 01" })).toHaveAttribute("aria-pressed", "true");
  });
  it("preserves user edits and cleared comparisons during pending inspection", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: unknown) => String(url).endsWith("/inspect")
      ? new Promise<Response>(done => { resolve = done; }) : Promise.resolve(reply({ success: true, candidates }))));
    const observe = vi.fn(); render(<Harness observe={observe} value={{ ...initial, comparisons: [] }} />);
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "我的差异分析" } });
    await act(async () => resolve(reply(inspected)));
    expect(screen.getByLabelText("输出名称")).toHaveValue("我的差异分析");
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ output_name: "我的差异分析", comparisons: [] }));
  });
  it("clears previous choices when changing the upstream artifact", async () => {
    installFetch(); const observe = vi.fn(); render(<Harness observe={observe} value={{ ...initial, comparisons: [["02", "01"]], selected_categories: ["01"], selected_samples: ["乙::001"], output_name: "保留名称" }} />);
    const select = await screen.findByLabelText("选择前置分析结果");
    await waitFor(() => expect(select).toHaveValue("one"));
    fireEvent.change(select, { target: { value: "two" } });
    const changed = observe.mock.calls.at(-1)?.[0];
    expect(changed).toMatchObject({ upstream_artifact_id: "two", output_name: "保留名称" });
    expect(changed.comparisons).toBeUndefined(); expect(changed.selected_samples).toBeUndefined(); expect(changed.selected_categories).toBeUndefined();
  });
  it("checks expression mode only when active and permits zero fold-change cutoff", async () => {
    const fetchMock = installFetch(), observe = vi.fn(); render(<Harness observe={observe} />);
    await screen.findByRole("button", { name: "01 与 02" });
    fireEvent.change(screen.getByLabelText("输入模式"), { target: { value: "expression" } });
    await screen.findByRole("button", { name: "A_vs_B" });
    fireEvent.change(screen.getByLabelText("对数倍数变化阈值"), { target: { value: "0" } });
    expect(observe.mock.calls.at(-1)?.[0].logfc_cutoff).toBe(0);
    expect(fetchMock.mock.calls.filter(([url, init]) => String(url).endsWith("/inspect") && JSON.parse(String(init?.body)).input_mode === "expression")).toHaveLength(1);
  });
});


it("读取来源时撤销旧检查，成功后才恢复配置就绪且保留编辑", async () => {
  let resolve!:(response:Response)=>void;
  vi.stubGlobal("fetch",vi.fn((url:unknown)=>String(url).endsWith("/inspect")
    ?new Promise<Response>(done=>{resolve=done;}):Promise.resolve(reply({success:true,candidates}))));
  const observe=vi.fn();
  render(<Harness observe={observe} value={{...initial,usage_inspect_ok:true}}/>);
  await waitFor(()=>expect(observe.mock.calls.at(-1)?.[0].usage_inspect_ok).toBe(false));
  expect(configurationIssue("volcano",observe.mock.calls.at(-1)![0])).toMatch(/完成.*检查/);
  fireEvent.change(screen.getByLabelText("输出名称"),{target:{value:"保留检查期间编辑"}});
  await act(async()=>resolve(reply(inspected)));
  await waitFor(()=>expect(observe.mock.calls.at(-1)?.[0].usage_inspect_ok).toBe(true));
  expect(observe.mock.calls.at(-1)?.[0].output_name).toBe("保留检查期间编辑");
  expect(configurationIssue("volcano",observe.mock.calls.at(-1)![0])).toBe("");
});

it("来源检查失败后不沿用旧就绪状态，配置摘要提示重新检查", async () => {
  vi.stubGlobal("fetch",vi.fn(async(url:unknown)=>String(url).endsWith("/inspect")
    ?new Response(JSON.stringify({message:"该来源没有分组表",error:"该来源没有分组表"}),{status:400,headers:{"content-type":"application/json"}})
    :reply({success:true,candidates})));
  const observe=vi.fn();
  render(<Harness observe={observe} value={{...initial,usage_inspect_ok:true,comparisons:[["01","02"]],selected_samples:["甲::001"]}}/>);
  await screen.findByText("该来源没有分组表");
  expect(observe.mock.calls.at(-1)?.[0].usage_inspect_ok).toBe(false);
  expect(configurationIssue("volcano",observe.mock.calls.at(-1)![0])).toMatch(/完成.*检查/);
  expect(configurationIssue("volcano",{...initial,usage_inspect_ok:false},true)).toBe("");
  expect(configurationIssue("volcano",{input_mode:"expression",comparisons:[["01","02"]],usage_inspect_ok:false})).toBe("");
});
