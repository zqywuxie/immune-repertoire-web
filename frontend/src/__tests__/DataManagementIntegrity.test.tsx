import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AssetUpload } from "../features/assets/AssetUpload";
import { AssetTable } from "../features/assets/AssetTable";
import { ProjectFileUpload } from "../features/assets/ProjectFileUpload";
import { ProjectGroupSpecs } from "../features/projects/ProjectGroupSpecs";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
import type { ProjectAsset } from "../shared/types/domain";

beforeEach(() => { vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[]}); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); apiClient.invalidateCache(); });
const profile = {id:"a",project_id:"p",asset_type:"profile",original_name:"指标.csv",storage_path:"/synthetic/profile.csv",size:1,metadata:{asset_set:"甲",content_version:"version-a"}} as ProjectAsset;

it("切换输入类型后完整提交清单仍可见，移除隐藏文件不会上传", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
  const upload = vi.spyOn(projects,"uploadProjectAssets").mockResolvedValue({assets:[profile]});
  render(<AssetUpload projectId="p" onSuccess={vi.fn()} />);
  const file = new File(["sample,group\n001,A"],"指标.csv");
  const expression = new File(["gene,001\nTP53,1"],"表达.csv");
  fireEvent.change(screen.getByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）",{selector:"input"}),{target:{files:[file]}});
  fireEvent.change(screen.getByLabelText("将表达矩阵拖到此处（可选）",{selector:"input"}),{target:{files:[expression]}});
  fireEvent.click(screen.getByRole("button",{name:"准备上传的输入类型"}));
  fireEvent.click(screen.getByRole("option",{name:"转录组"}));
  const queue = screen.getByRole("region",{name:"本次提交清单"});
  expect(within(queue).getByText("指标.csv")).toBeVisible();
  expect(within(queue).getByText("表达.csv")).toBeVisible();
  await waitFor(()=>expect(screen.getByRole("button",{name:"保存数据（2 项）"})).toBeEnabled());
  fireEvent.click(within(queue).getByRole("button",{name:"从提交清单移除 指标.csv"}));
  fireEvent.click(screen.getByRole("button",{name:"保存数据（1 项）"}));
  await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
  expect(upload.mock.calls[0][1]).toMatchObject({assetType:"transcriptome",files:[expression]});
});

it("同名附件明确提示并保留先前选择", async () => {
  const upload=vi.spyOn(projects,"uploadProjectAssets").mockResolvedValue({assets:[profile]});
  render(<ProjectFileUpload projectId="p" onSuccess={vi.fn()} />);
  const first=new File(["first"],"记录.txt"), second=new File(["second"],"记录.txt");
  const input=screen.getByLabelText("将项目文档、笔记、表格或附件拖到此处",{selector:"input"});
  fireEvent.change(input,{target:{files:[first]}});
  fireEvent.change(input,{target:{files:[second]}});
  expect(screen.getByRole("alert")).toHaveTextContent("同名文件未添加");
  fireEvent.click(screen.getByRole("button",{name:"上传 1 个附件"}));
  await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
  expect(upload.mock.calls[0][1].files[0]).toBe(first);
});

it("文件说明只提交实际改变的说明，不改数据集或版本", async () => {
  const request=vi.fn().mockResolvedValue({ok:true,json:async()=>({success:true})});
  vi.stubGlobal("fetch",request);
  render(<AssetTable projectId="p" assets={[profile]} loading={false} />);
  fireEvent.click(screen.getByRole("button",{name:"更多操作：指标.csv"}));
 fireEvent.click(screen.getByRole("button",{name:"修改 指标.csv 的数据集归属"}));
  fireEvent.change(screen.getByRole("textbox",{name:"文件说明"}),{target:{value:"新的文件用途"}});
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(() => expect(request).toHaveBeenCalledTimes(1));
  expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({metadata_json:{description:"新的文件用途"}});
});

it("方案编辑保留组属性和其他配置，取消不保存，删除先确认", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
  const post=vi.spyOn(apiClient,"post").mockResolvedValue({});
  const remove=vi.spyOn(apiClient,"delete").mockResolvedValue({});
  const spec={id:"s",name:"原方案",spec_json:{group_field:"group",description:"保留说明",groups:[{name:"A",color:"blue"},{name:"B",color:"red"}]}};
  render(<MemoryRouter><ProjectGroupSpecs projectId="p" loading={false} groupSpecs={[spec]} onChanged={vi.fn()} /></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"编辑"}));
  fireEvent.click(screen.getByRole("button",{name:"取消编辑"}));
  expect(post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"编辑"}));
  fireEvent.change(screen.getByRole("textbox",{name:"方案名称"}),{target:{value:"重命名"}});
  fireEvent.change(screen.getByRole("textbox",{name:"分组名称（按顺序，用逗号或顿号分隔）"}),{target:{value:"B、A"}});
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[0][1]).toEqual({id:"s",expected_revision:undefined,name:"重命名",spec_json:{...spec.spec_json,groups:[spec.spec_json.groups[1],spec.spec_json.groups[0]]}});
  fireEvent.click(screen.getByRole("button",{name:"更多操作：原方案"}));
  fireEvent.click(screen.getByRole("button",{name:"删除"}));
  expect(remove).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"确认删除"}));
  await waitFor(() => expect(remove).toHaveBeenCalledWith("/api/projects/p/group-specs/s"));
});

it("实际指标表取值可排序，保存绑定具体来源版本与字段", async () => {
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[profile]});
  const post=vi.spyOn(apiClient,"post").mockResolvedValue({columns:["sample","group"],sheets:[],selected_sheet:null,requires_sheet_selection:false});
  vi.spyOn(apiClient,"get").mockResolvedValue({values:["A","B"],samples_by_value:{A:["001"],B:["002"]},row_counts:{A:1,B:1},sample_column:"sample",asset_set:"甲",content_version:"version-a"});
  render(<MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectGroupSpecs projectId="p" loading={false} groupSpecs={[]} onChanged={vi.fn()} /></MemoryRouter>);
  fireEvent.change(screen.getByRole("textbox",{name:"方案名称"}),{target:{value:"B优先"}});
  await waitFor(() => expect(projects.listProjectAssets).toHaveBeenCalled());
  fireEvent.click(screen.getByRole("button",{name:"方案来源指标表"}));
  fireEvent.click(await screen.findByRole("option",{name:/甲 · 指标.csv/}));
  fireEvent.click(await screen.findByRole("button",{name:"方案分组字段"}));
  fireEvent.click(screen.getByRole("option",{name:"group"}));
  fireEvent.click(await screen.findByRole("button",{name:"上移 B"}));
  expect(screen.getByRole("list",{name:"分组展示顺序"}).firstElementChild).toHaveTextContent("1. B");
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(() => expect(post).toHaveBeenCalledWith("/api/projects/p/group-specs",{name:"B优先",spec_json:{groups:["B","A"],group_field:"group",source_asset_id:"a",source_content_version:"version-a",source_sheet:null,asset_set:"甲"}}));
});

it("输入页签不读取结果和附件，结果页只读取统一列表并显示总数", async () => {
  vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"合成项目",asset_counts:{},result_count:23} as never);
  const assets=vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[]});
  const results=vi.spyOn(projects,"listProjectResults").mockResolvedValue({success:true,results:[profile],pagination:{page:1,page_size:10,total:23,total_pages:3}});
  render(<MemoryRouter initialEntries={["/management/projects/p?tab=assets"]}><Routes><Route path="/management/projects/:projectId" element={<ProjectDetail />} /></Routes></MemoryRouter>);
  await screen.findByText("项目数据集");
  expect(results).not.toHaveBeenCalled();
  expect(assets.mock.calls.some(call => call[1]?.assetType === "project_file" || call[1]?.assetType === "processed_result")).toBe(false);
  fireEvent.click(screen.getByRole("tab",{name:"分析结果"}));
  expect(await screen.findByText("分析结果（23）")).toBeInTheDocument();
  expect(results).toHaveBeenCalledTimes(1);
  expect(assets.mock.calls.some(call => call[1]?.assetType === "processed_result")).toBe(false);
});


it("已有数据集部分成功刷新来源后，失败项仍留在提交清单", async () => {
  let active = profile;
  vi.spyOn(projects,"listProjectDatasets").mockImplementation(async()=>({datasets:[{name:"甲",input_count:active.id==="a"?1:2,kinds:{profile:{count:active.id==="a"?1:2,statuses:{valid:active.id==="a"?1:2},sample_min:1,sample_max:1}}}]}));
  const fullAssets=vi.spyOn(projects,"listProjectAssets");
  vi.spyOn(projects,"uploadProjectAssets").mockImplementation(async (_id, options) => {
    if (options.assetType === "transcriptome") throw new Error("表达上传失败");
    active={...profile,id:"new",storage_path:"/synthetic/new.csv",metadata:{...profile.metadata,content_version:"new-version"}};
    return {assets:[active]};
  });
  render(<AssetUpload projectId="p" initialAssetSet="甲" onSuccess={vi.fn()} />);
  await screen.findByText("已登记 1 个样本指标表文件");
  fireEvent.change(screen.getByLabelText("选择新的样本指标表",{selector:"input"}),{target:{files:[new File(["sample,value\n001,1"],"新版.csv")]}});
  fireEvent.change(screen.getByLabelText("将表达矩阵拖到此处（可选）",{selector:"input"}),{target:{files:[new File(["gene,001\nTP53,1"],"失败表达.csv")]}});
  fireEvent.click(screen.getByRole("button",{name:/保存数据/}));
  await screen.findByText("已登记 2 个样本指标表文件");
  expect(fullAssets).not.toHaveBeenCalled();
  expect(screen.getByRole("button",{name:"从提交清单移除 失败表达.csv"})).toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"从提交清单移除 新版.csv"})).not.toBeInTheDocument();
});
