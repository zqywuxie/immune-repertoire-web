import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { ProjectInputSamples } from "../features/assets/ProjectInputSamples";
import * as samples from "../shared/api/samples";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";

const record = { id: "r", project_id: "p", project_name: "研究项目", sample_id: "001", sample_name: "登记样本", extra_metadata: { asset_set: "甲" }, sequence_id: null, spices: null, institution: null, chain_flag: null, is_healthy: null, illness: null, is_pe: null, contain_method: null, iso_tag: null, created_at: null, updated_at: null } satisfies samples.SampleRecord;
const pagination = (page: number, totalPages = 1) => ({ page, page_size: 50, total: totalPages ? totalPages * 50 : 0, total_pages: totalPages });
const coverage = (page: number, totalPages = 1) => ({ samples: [], unresolved: [], input_scopes: {}, note: "输入样本", pagination: pagination(page, totalPages) });
function mount(element: React.ReactNode, url: string, path = "*") {
  const router = createMemoryRouter([{ path, element }], { initialEntries: [url] });
  render(<RouterProvider router={router} />);
  return router;
}
beforeEach(() => {
  vi.spyOn(samples, "listSamples").mockImplementation(async params => ({ samples: [record], pagination: pagination(params?.page || 1) }));
  vi.spyOn(samples, "getSampleFieldOptions").mockResolvedValue({ fields: {} });
  vi.spyOn(projects, "getProject").mockResolvedValue({ id: "p", name: "研究项目", asset_counts: {}, group_specs: [] } as never);
  vi.spyOn(projects, "listProjectDatasets").mockResolvedValue({ datasets: [] });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); apiClient.invalidateCache(); });

it("快速输入后导出仍使用当前已应用筛选，保留项目与数据集", async () => {
  const download = vi.spyOn(samples, "downloadSamples").mockRejectedValue(new Error("合成失败"));
  mount(<SampleRegistry />, "/management/samples?project_id=p&asset_set=甲&q=旧编号&illness=疾病甲");
  await screen.findByRole("row", { name: /001 登记样本/ });
  fireEvent.change(screen.getByRole("textbox", { name: /搜索/ }), { target: { value: "新编号" } });
  fireEvent.click(screen.getByRole("button", { name: "导出数据表" }));
  expect(screen.getByRole("region",{name:"本次导出范围"})).toHaveTextContent("旧编号");
  fireEvent.click(screen.getByRole("button",{name:"生成并下载"}));
  await screen.findByRole("alert");
  expect(download).toHaveBeenCalledWith(expect.objectContaining({q:"旧编号",project_id:"p",asset_set:"甲",illness:"疾病甲"}),"xlsx",false,expect.any(AbortSignal));
});

it("仅按名称筛选也可清空，保留项目数据集及返回入口", async () => {
  const router = mount(<SampleRegistry />, "/management/samples?project_id=p&asset_set=甲&sample_name=名称&return_to=%2Fmanagement%2Fprojects%2Fp%3Ftab%3Dsamples");
  fireEvent.click(await screen.findByRole("button", { name: "清空筛选" }));
  await waitFor(() => expect(new URLSearchParams(router.state.location.search).has("sample_name")).toBe(false));
  const query = new URLSearchParams(router.state.location.search);
  expect(query.get("project_id")).toBe("p");
  expect(query.get("asset_set")).toBe("甲");
  expect(query.get("return_to")).toBe("/management/projects/p?tab=samples");
});

it("登记列表超界页回到末页，保留筛选且不增加无效历史记录", async () => {
  vi.mocked(samples.listSamples).mockImplementation(async params => ({ samples: [], pagination: pagination(params?.page || 1, 2) }));
  const router = mount(<SampleRegistry />, "/management/samples?project_id=p&asset_set=甲&institution=机构&page=9");
  await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("page")).toBe("2"));
  await waitFor(() => expect(samples.listSamples).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2, institution: "机构", asset_set: "甲" })));
  await router.navigate(-1);
  expect(new URLSearchParams(router.state.location.search).get("page")).toBe("2");
});

it("输入覆盖为空时纠正超界页，不清空已应用的编号和状态", async () => {
  const get = vi.spyOn(apiClient, "get").mockImplementation(async (_url, params) => coverage(Number(params?.page || 1), 0) as never);
  const router = mount(<ProjectInputSamples projectId="p" revision={0} />, "/management/projects/p?tab=samples&asset_set=甲&sample_q=001&sample_state=needs_attention&sample_page=9");
  await waitFor(() => expect(new URLSearchParams(router.state.location.search).has("sample_page")).toBe(false));
  await waitFor(() => expect(get).toHaveBeenLastCalledWith("/api/projects/p/input-samples", expect.objectContaining({ asset_set: "甲", q: "001", state: "needs_attention", page: 1 })));
  expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("samples");
});

it("输入搜索草稿明确未应用，提交后才改变列表范围，清除保留数据集", async () => {
  const get = vi.spyOn(apiClient, "get").mockImplementation(async (_url, params) => coverage(Number(params?.page || 1)) as never);
  const router = mount(<ProjectInputSamples projectId="p" revision={0} />, "/management/projects/p?tab=samples&asset_set=甲&sample_q=001&sample_state=multiple");
  await screen.findByText(/输入样本 各类输入/);
  fireEvent.change(screen.getByRole("textbox", { name: "搜索输入样本编号" }), { target: { value: "002" } });
  expect(screen.getByRole("status", { name: "" })).toHaveTextContent("搜索编号尚未应用");
  expect(new URLSearchParams(router.state.location.search).get("sample_q")).toBe("001");
  fireEvent.click(screen.getByRole("button", { name: "查询样本" }));
  await waitFor(() => expect(get).toHaveBeenLastCalledWith("/api/projects/p/input-samples", expect.objectContaining({ q: "002", asset_set: "甲" })));
  expect(screen.queryByText(/搜索编号尚未应用/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "清除样本筛选" }));
  await waitFor(() => expect(new URLSearchParams(router.state.location.search).has("sample_q")).toBe(false));
  expect(new URLSearchParams(router.state.location.search).has("sample_state")).toBe(false);
  expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("甲");
  expect(screen.getByRole("textbox", { name: "搜索输入样本编号" })).toHaveValue("");
});

it("结果超界页回到有效末页，保留当前项目标签和数据集", async () => {
  const list = vi.spyOn(projects, "listProjectResults").mockImplementation(async (_id, params) => ({ success: true, results: [], pagination: pagination(Number(params?.page || 1), 2) }));
  const router = mount(<ProjectDetail />, "/management/projects/p?tab=results&asset_set=甲&result_page=9", "/management/projects/:projectId");
  await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("result_page")).toBe("2"));
  await waitFor(() => expect(list).toHaveBeenLastCalledWith("p", expect.objectContaining({ page: 2 })));
  expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("results");
  expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("甲");
});

it("覆盖读取失败时保留原页码与范围，重试成功后才纠正页码", async () => {
  vi.spyOn(apiClient, "get").mockRejectedValueOnce(new Error("临时读取失败")).mockImplementation(async (_url, params) => coverage(Number(params?.page || 1)) as never);
  const router = mount(<ProjectInputSamples projectId="p" revision={0} />, "/management/projects/p?asset_set=甲&sample_page=9");
  expect(await screen.findByRole("alert")).toHaveTextContent("临时读取失败");
  expect(new URLSearchParams(router.state.location.search).get("sample_page")).toBe("9");
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  await waitFor(() => expect(new URLSearchParams(router.state.location.search).has("sample_page")).toBe(false));
  expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("甲");
});

it("结果来源读取失败不冒充未生成结果，重试保留原项目和页码",async()=>{
 const list=vi.spyOn(projects,"listProjectResults").mockRejectedValueOnce(new Error("分析结果暂时无法完整读取，请重试。"))
 .mockResolvedValue({success:true,results:[],pagination:pagination(2,2)});
 const router=mount(<ProjectDetail/>,"/management/projects/p?tab=results&result_page=2","/management/projects/:projectId");
 await screen.findByRole("alert");expect(screen.queryByText("尚未生成分析结果。")).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"重新读取结果"}));
 await waitFor(()=>expect(list).toHaveBeenCalledTimes(2));expect(new URLSearchParams(router.state.location.search).get("result_page")).toBe("2");
});
