import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { ProjectLibrary } from "../pages/management/ProjectLibrary";
import { ProjectFileUpload } from "../features/assets/ProjectFileUpload";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
import { UploadResponseUnknownError } from "../shared/api/uploadOperations";

const project = { id:"p", name:"研究项目", status:"active", asset_counts:{}, group_specs:[], input_sample_count:2 };
beforeEach(() => {
  vi.spyOn(projects,"getProject").mockResolvedValue(project as never);
  vi.spyOn(projects,"getProjectStatistics").mockResolvedValue({project_count:1,status_counts:{active:1},file_count:0,result_count:0,input_sample_count:2,registered_sample_count:0,dataset_count:2,group_spec_count:0});
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[], pagination:{page:1,page_size:50,total:0,total_pages:1}});
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:["甲","乙"].map(name=>({name,input_count:1,kinds:{profile:{count:1,statuses:{valid:1},sample_min:1,sample_max:1}}}))});
  vi.spyOn(projects,"listProjectResults").mockResolvedValue({results:[]} as never);
});
afterEach(() => {cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
function routerFor(search="?tab=attachments&asset_set=甲") {
  return createMemoryRouter([{path:"/management/projects/:projectId",element:<ProjectDetail/>},{path:"/analysis/center",element:<p>分析页面</p>}],{initialEntries:["/management/projects/p"+search]});
}
function chooseFile(container:HTMLElement, name="说明.txt") {
  fireEvent.change(container.querySelector('input[type="file"]')!,{target:{files:[new File(["synthetic"],name,{type:"text/plain"})]}});
}

it("附件窗口关闭保留选择，切标签需确认；继续编辑保留，明确放弃才清除", async()=>{
  const router=routerFor();const {container}=render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"上传附件"}));chooseFile(container);
  fireEvent.click(within(screen.getByRole("dialog",{name:"上传项目附件"})).getByRole("button",{name:"关闭"}));
  expect(screen.getByText("已保留 1 个未保存附件。")).toBeVisible();
  await act(async()=>{await router.navigate("?tab=overview&asset_set=甲");});
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("attachments");
  fireEvent.click(screen.getByRole("button",{name:"继续上传附件"}));
  expect(screen.getByRole("button",{name:"上传 1 个附件"})).toBeEnabled();
  fireEvent.keyDown(document,{key:"Escape"});
  fireEvent.click(screen.getByRole("button",{name:"放弃附件选择"}));
  fireEvent.click(screen.getByRole("button",{name:"确认放弃附件选择"}));
  expect(screen.queryByText("已保留 1 个未保存附件。")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"上传附件"}));
  expect(screen.getByRole("button",{name:"上传 0 个附件"})).toBeDisabled();
});

it("附件上传期间不能Esc关闭，完成后释放草稿和离开保护",async()=>{
  let finish!:(value:unknown)=>void; const pending=new Promise(resolve=>{finish=resolve;});
  vi.spyOn(projects,"uploadProjectAssets").mockReturnValue(pending as never);
  const router=routerFor();const {container}=render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"上传附件"}));chooseFile(container);
  fireEvent.click(screen.getByRole("button",{name:"上传 1 个附件"}));
  fireEvent.keyDown(document,{key:"Escape"});expect(screen.getByRole("dialog",{name:"上传项目附件"})).toBeVisible();
  await act(async()=>{finish({assets:[]});await pending;});
  await screen.findByText("已保存 1 个附件。");fireEvent.keyDown(document,{key:"Escape"});
  await act(async()=>{await router.navigate("?tab=overview&asset_set=甲");});
  expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("overview");
  expect(screen.queryByRole("dialog",{name:"离开前确认未保存内容"})).not.toBeInTheDocument();
});

it("附件保存状态未知时重试相同操作，显式移除并重选才建立新操作",async()=>{
  const upload=vi.spyOn(projects,"uploadProjectAssets").mockRejectedValueOnce(new UploadResponseUnknownError()).mockResolvedValue({assets:[]});
  const success=vi.fn();const {container}=render(<ProjectFileUpload projectId="p" onSuccess={success}/>);
  chooseFile(container);fireEvent.click(screen.getByRole("button",{name:"上传 1 个附件"}));
  await screen.findByText(/剩余选择已保留，可重试/);
  fireEvent.click(screen.getByRole("button",{name:"上传 1 个附件"}));await waitFor(()=>expect(success).toHaveBeenCalledTimes(1));
  expect(upload.mock.calls[0][1].operationId).toMatch(/^[0-9a-f-]{36}$/);
  expect(upload.mock.calls[1][1].operationId).toBe(upload.mock.calls[0][1].operationId);
  expect(upload.mock.calls[1][1].retry).toBe(true);
  chooseFile(container);fireEvent.click(screen.getByRole("button",{name:"上传 1 个附件"}));await waitFor(()=>expect(success).toHaveBeenCalledTimes(2));
  expect(upload.mock.calls[2][1].operationId).not.toBe(upload.mock.calls[0][1].operationId);
});

it("附件批量部分失败只重试剩余项，已保存项不会重传",async()=>{
  const upload=vi.spyOn(projects,"uploadProjectAssets").mockResolvedValueOnce({assets:[]}).mockRejectedValueOnce(new Error("失败附件")).mockResolvedValue({assets:[]});
  const {container}=render(<ProjectFileUpload projectId="p" onSuccess={vi.fn()}/>);
  fireEvent.change(container.querySelector('input[type="file"]')!,{target:{files:[new File(["a"],"甲.txt"),new File(["b"],"乙.txt")]}});
  fireEvent.click(screen.getByRole("button",{name:"上传 2 个附件"}));await screen.findByText(/剩余选择已保留，可重试/);
  fireEvent.click(screen.getByRole("button",{name:"上传 1 个附件"}));await waitFor(()=>expect(upload).toHaveBeenCalledTimes(3));
  expect(upload.mock.calls[2][1].files[0].name).toBe("乙.txt");
  expect(upload.mock.calls[2][1].operationId).toBe(upload.mock.calls[1][1].operationId);
});

it("项目读取失败不显示暂无项目；重试后成功空列表显示正确空态",async()=>{
  vi.spyOn(projects,"listProjects").mockRejectedValueOnce(new Error("读取项目失败")).mockResolvedValue({projects:[],pagination:{page:1,page_size:24,total:0,total_pages:0}});
  render(<MemoryRouter><ProjectLibrary/></MemoryRouter>);
  expect(await screen.findByText("读取项目失败")).toBeVisible();
  expect(screen.queryByText("暂无项目")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"重新读取项目"}));
  expect(await screen.findByText("暂无项目")).toBeVisible();
  expect(screen.queryByRole("button",{name:"重新读取项目"})).not.toBeInTheDocument();
});

it("附件和结果说明项目级范围，分析范围在切标签后保持",async()=>{
  const router=routerFor();render(<RouterProvider router={router}/>);
  expect(await screen.findByText("当前内容：项目全部附件")).toBeVisible();
  fireEvent.click(screen.getByRole("tab",{name:"分析结果"}));
  expect(await screen.findByText("当前内容：项目全部分析结果")).toBeVisible();
  expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("甲");
  fireEvent.click(screen.getByRole("tab",{name:"概览"}));expect(await screen.findByText("项目概览 · 全部数据集")).toBeVisible();
});

it("覆盖矩阵默认收起，快捷切集清除旧样本页码并定位对应输入类型",async()=>{
  const router=routerFor("?tab=assets&asset_set=&sample_page=3&file_page=2");render(<RouterProvider router={router}/>);
  const summary=await screen.findByText("各数据集输入覆盖 · 2 个数据集");
  expect(summary.closest("details")).not.toHaveAttribute("open");
  fireEvent.click(summary);fireEvent.click(screen.getByRole("button",{name:"查看 乙 的样本指标表：1 项通过"}));
  await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("乙"));
  const query=new URLSearchParams(router.state.location.search);expect(query.has("sample_page")).toBe(false);expect(query.has("file_page")).toBe(false);expect(query.get("file_type")).toBe("profile");
});

it("手机输入概况默认收起，文件列表优先展示且展开后原输入操作可达",async()=>{
  vi.stubGlobal("matchMedia",vi.fn().mockImplementation(query=>({media:query,matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()})));
  const router=routerFor("?tab=assets&asset_set=甲");render(<RouterProvider router={router}/>);
  const summary=await screen.findByText("输入概况 · 1 个文件");
  expect(summary.closest("details")).not.toHaveAttribute("open");
  expect(screen.getByLabelText("搜索输入文件")).toBeVisible();
  fireEvent.click(summary);expect(summary.closest("details")).toHaveAttribute("open");
  expect(screen.getByRole("button",{name:"查看文件"})).toBeVisible();
  expect(screen.getAllByRole("button",{name:"添加输入"}).length).toBe(3);
});

it("手机文件筛选先编辑草稿，关闭不应用，应用重置文件页码并保留项目数据集和搜索",async()=>{
  vi.stubGlobal("matchMedia",vi.fn().mockImplementation(query=>({media:query,matches:true,addEventListener:vi.fn(),removeEventListener:vi.fn()})));
  const router=routerFor("?tab=assets&asset_set=甲&file_q=指标&file_page=3");render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"文件筛选（0）"}));
  fireEvent.click(screen.getByRole("checkbox",{name:"显示历史版本"}));
  expect(new URLSearchParams(router.state.location.search).get("history")).toBeNull();
  fireEvent.keyDown(document,{key:"Escape"});
  fireEvent.click(screen.getByRole("button",{name:"文件筛选（0）"}));
  expect(screen.getByRole("checkbox",{name:"显示历史版本"})).not.toBeChecked();
  fireEvent.click(screen.getByRole("checkbox",{name:"显示历史版本"}));fireEvent.click(screen.getByRole("button",{name:"应用文件筛选"}));
  await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("history")).toBe("1"));
  let query=new URLSearchParams(router.state.location.search);expect(query.get("asset_set")).toBe("甲");expect(query.get("file_q")).toBe("指标");expect(query.has("file_page")).toBe(false);
  fireEvent.click(screen.getByRole("button",{name:"文件筛选（1）"}));fireEvent.click(screen.getByRole("button",{name:"重置文件条件"}));
  expect(new URLSearchParams(router.state.location.search).get("history")).toBe("1");
  fireEvent.click(screen.getByRole("button",{name:"应用文件筛选"}));await waitFor(()=>expect(new URLSearchParams(router.state.location.search).has("history")).toBe(false));
  query=new URLSearchParams(router.state.location.search);expect(query.get("asset_set")).toBe("甲");expect(query.get("file_q")).toBe("指标");
});
