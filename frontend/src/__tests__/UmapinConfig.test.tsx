import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UmapinConfig } from "../features/scripthub/modules/UmapinConfig";
import { configurationIssue } from "../features/scripthub/configurationValidation";
import { submitLegacyScriptHubJob } from "../shared/api/scriptHub";
const source = { projectId: "synthetic", assetSetId: "Set2", profilePath: "/data/profile.csv", pepPaths: [],
  sampleNames: [], chains: ["TRB"], profileFields: ["sample", "group"], groupFields: ["group"], pepColumns: [] };
const candidates = ["one", "two"].map(id => ({ id, artifact_id: id, path: `/results/${id}/df_VJ_all.csv`, job_id: `source-${id}`, status: "available" }));
const inspected = { success: true, data_path: candidates[0].path, category_col: "Category", sample_column: "sample",
  columns: ["sample", "Category", "V1", "V2"], feature_columns: ["V1", "V2"], suggested_param_begin: "V1", suggested_param_over: "V2",
  pvalue_columns: [], sample_count: 6, samples_by_value: { "01": ["甲::001", "甲::002", "乙::001", "乙::002"], "02": ["甲::003", "乙::003"] } };
const reply = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
const initial = { upstream_artifact_id: "one", category_col: "Category", sample_column: "sample" };
function Harness({ value = initial, observe = vi.fn() }: { value?: Record<string, unknown>; observe?: (next: Record<string, unknown>) => void }) {
  const [current, setCurrent] = useState<Record<string, unknown>>(value);
  return <UmapinConfig projectId="synthetic" module="umapin" groupSpecs={[]} loadingSpecs={false} sourceContext={source}
    value={current} onChange={next => { setCurrent(next); observe(next); }} />;
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function installFetch() {
  const fetchMock = vi.fn(async (url: unknown, _init?: RequestInit) => reply(String(url).includes("pep-cache-candidates")
    ? { success: true, candidates } : String(url).endsWith("/inspect") ? inspected : { success: true, task_id: "synthetic-job" }));
  vi.stubGlobal("fetch", fetchMock); return fetchMock;
}
describe("特征降维的真实输入交互", () => {
  it("selects only one batch using actual upstream row identities and submits its artifact", async () => {
    const fetchMock = installFetch(), observe = vi.fn(); render(<Harness observe={observe} />);
    for (const name of ["01 / 甲 / 001", "01 / 甲 / 002", "02 / 甲 / 003"]) fireEvent.click(await screen.findByRole("button", { name }));
    const payload = observe.mock.calls.at(-1)?.[0];
    expect(payload.selected_samples).toEqual(["乙::001", "乙::002", "乙::003"]);
    expect(screen.queryByLabelText("p 值阈值")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("假发现率校正")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("最小距离"), { target: { value: "0" } });
    await submitLegacyScriptHubJob({ module: "umapin", projectId: "synthetic", payload: { ...observe.mock.calls.at(-1)?.[0], asset_set: "Set2", selected_group_values: { group: ["A"] }, selected_samples_by_group: { group: { A: ["001"] } } } });
    const submitted = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(submitted).toMatchObject({ upstream_artifact_id: "one", selected_samples: ["乙::001", "乙::002", "乙::003"], min_dist: 0 });
    expect(submitted.data_path).toBeUndefined();
    expect(submitted.selected_samples_by_group).toBeUndefined();
    expect(submitted.selected_group_values).toBeUndefined();
    const inspection = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/inspect"));
    expect(JSON.parse(String(inspection?.[1]?.body))).toMatchObject({ asset_set: "Set2", upstream_artifact_id: "one" });
  });
  it("preserves output edits while inspection is pending", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: unknown) => String(url).endsWith("/inspect")
      ? new Promise<Response>(done => { resolve = done; }) : Promise.resolve(reply({ success: true, candidates }))));
    const observe = vi.fn(); render(<Harness observe={observe} />);
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "我的投影" } });
    fireEvent.change(screen.getByLabelText("最小距离"), { target: { value: "0" } });
    await act(async () => resolve(reply(inspected)));
    expect(screen.getByLabelText("输出名称")).toHaveValue("我的投影");
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ output_name: "我的投影", min_dist: 0, param_begin: "V1" }));
  });
  it("clears prior sample and feature choices when changing the upstream artifact", async () => {
    installFetch(); const observe = vi.fn(); render(<Harness observe={observe} value={{ ...initial, param_begin: "V2", selected_categories: ["01"], selected_samples: ["乙::001"], output_name: "保留名称" }} />);
    const select = await screen.findByLabelText("选择前置分析结果");
    await waitFor(() => expect(select).toHaveValue("one"));
    fireEvent.change(select, { target: { value: "two" } });
    const changed = observe.mock.calls.at(-1)?.[0];
    expect(changed).toMatchObject({ upstream_artifact_id: "two", output_name: "保留名称" });
    expect(changed.param_begin).toBeUndefined(); expect(changed.selected_samples).toBeUndefined(); expect(changed.selected_categories).toBeUndefined();
  });
});


it("检查期间撤销旧就绪状态，完成后恢复且保留编辑",async()=>{
 let resolve!:(response:Response)=>void;
 vi.stubGlobal("fetch",vi.fn((url:unknown)=>String(url).endsWith("/inspect")
  ?new Promise<Response>(done=>{resolve=done;}):Promise.resolve(reply({success:true,candidates}))));
 const observe=vi.fn();
 render(<Harness observe={observe} value={{...initial,umapin_inspect_ok:true}}/>);
 await waitFor(()=>expect(observe.mock.calls.at(-1)?.[0].umapin_inspect_ok).toBe(false));
 expect(configurationIssue("umapin",observe.mock.calls.at(-1)![0])).toMatch(/完成.*检查/);
 fireEvent.change(screen.getByLabelText("输出名称"),{target:{value:"检查期间保留名称"}});
 fireEvent.change(screen.getByLabelText("最小距离"),{target:{value:"0"}});
 await act(async()=>resolve(reply(inspected)));
 await waitFor(()=>expect(observe.mock.calls.at(-1)?.[0].umapin_inspect_ok).toBe(true));
 expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({output_name:"检查期间保留名称",min_dist:0});
 expect(configurationIssue("umapin",observe.mock.calls.at(-1)![0])).toBe("");
});

it("失败后可检查同一来源，重试不更改产物、参数或提交计算",async()=>{
 let attempts=0;
 const fetchMock=vi.fn(async(url:unknown)=>String(url).endsWith("/inspect")
  ?++attempts===1?new Response(JSON.stringify({message:"合成来源检查中断"}),{status:400,headers:{"content-type":"application/json"}}):reply(inspected)
  :reply({success:true,candidates}));
 vi.stubGlobal("fetch",fetchMock);const observe=vi.fn();
 render(<Harness observe={observe} value={{...initial,umapin_inspect_ok:true,output_name:"保留我的配置",min_dist:0}}/>);
 expect(await screen.findByRole("alert")).toHaveTextContent("合成来源检查中断");
 expect(observe.mock.calls.at(-1)?.[0].umapin_inspect_ok).toBe(false);
 expect(configurationIssue("umapin",observe.mock.calls.at(-1)![0])).toMatch(/完成.*检查/);
 fireEvent.click(screen.getByRole("button",{name:"重新检查输入"}));
 await screen.findByRole("button",{name:"01 / 甲 / 001"});
 expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({umapin_inspect_ok:true,upstream_artifact_id:"one",output_name:"保留我的配置",min_dist:0});
 expect(attempts).toBe(2);
 expect(fetchMock.mock.calls.filter(([url])=>String(url).endsWith("/jobs"))).toHaveLength(0);
 expect(configurationIssue("umapin",{...initial,umapin_inspect_ok:false},true)).toBe("");
});

it("更换来源后忽略迟到的成功检查，不解除新来源的失败状态",async()=>{
 let resolveOld!:(response:Response)=>void;
 vi.stubGlobal("fetch",vi.fn((url:unknown,init?:RequestInit)=>{
  if(!String(url).endsWith("/inspect"))return Promise.resolve(reply({success:true,candidates}));
  const payload=JSON.parse(String(init?.body));
  if(payload.upstream_artifact_id==="one")return new Promise<Response>(done=>{resolveOld=done;});
  return Promise.resolve(new Response(JSON.stringify({message:"新来源检查失败"}),{status:400,headers:{"content-type":"application/json"}}));
 }));
 const observe=vi.fn();render(<Harness observe={observe}/>);
 const select=await screen.findByLabelText("选择前置分析结果");
 await waitFor(()=>expect(select).toHaveValue("one"));
 fireEvent.change(select,{target:{value:"two"}});
 expect(await screen.findByRole("alert")).toHaveTextContent("新来源检查失败");
 await act(async()=>resolveOld(reply(inspected)));
 expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({upstream_artifact_id:"two",umapin_inspect_ok:false});
 expect(screen.queryByRole("button",{name:"01 / 甲 / 001"})).not.toBeInTheDocument();
 expect(configurationIssue("umapin",observe.mock.calls.at(-1)![0])).toMatch(/完成.*检查/);
});
