import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { RouterProvider, createMemoryRouter, useNavigate } from "react-router-dom";
import { SampleEditSheet } from "../features/samples/SampleEditSheet";
import { AssetTable } from "../features/assets/AssetTable";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import * as projects from "../shared/api/projects";
import * as samples from "../shared/api/samples";
import { apiClient } from "../shared/api/client";
import type { SampleRecord } from "../shared/api/samples";
import type { ProjectAsset } from "../shared/types/domain";

const sample = { id:"r", project_id:"p", project_name:"研究项目", sample_id:"001", sample_name:"原名称", institution:"原机构", spices:"人", sequence_id:null, chain_flag:null, is_healthy:null, illness:null, is_pe:null, contain_method:null, iso_tag:null, created_at:null, updated_at:null, extra_metadata:{asset_set:"甲"} } as SampleRecord;
const asset = { id:"a", project_id:"p", asset_type:"profile", original_name:"指标.csv", storage_path:"/synthetic/a.csv", size:10, metadata:{asset_set:"甲",description:"原说明"} } as ProjectAsset;
beforeEach(() => {
  vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"研究项目",asset_counts:{},group_specs:[]} as never);
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[asset]});
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:["甲","乙"].map(name=>({name,input_count:1,kinds:{profile:{count:1,statuses:{valid:1},sample_min:1,sample_max:1}}}))});
  vi.spyOn(samples,"listSamples").mockResolvedValue({samples:[sample]});
  vi.spyOn(samples,"getSampleFieldOptions").mockResolvedValue({fields:{}});
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); apiClient.invalidateCache(); });

it("未修改样本直接关闭，修改后Esc需确认且继续编辑保留内容",()=>{
  const close=vi.fn();
  render(<SampleEditSheet sample={sample} open onClose={close} onSave={vi.fn()}/>);
  fireEvent.click(screen.getByRole("button",{name:"取消"}));
  expect(close).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByRole("textbox",{name:"疾病"}),{target:{value:"新疾病"}});
  fireEvent.keyDown(document,{key:"Escape"});
  expect(screen.getByRole("dialog",{name:"放弃未保存的样本信息"})).toBeVisible();
  expect(close).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("textbox",{name:"疾病"})).toHaveValue("新疾病");
  fireEvent.click(screen.getByRole("button",{name:"取消"}));
  fireEvent.click(screen.getByRole("button",{name:"放弃修改并关闭"}));
  expect(close).toHaveBeenCalledTimes(2);
});

it("样本保存失败保留修改，成功后只提交变更并清除页面草稿",async()=>{
  const save=vi.fn().mockRejectedValueOnce(new Error("临时失败")).mockResolvedValueOnce(undefined);
  const close=vi.fn(),dirty=vi.fn();
  const {unmount}=render(<SampleEditSheet sample={sample} open onClose={close} onSave={save} onDraftChange={dirty}/>);
  fireEvent.change(screen.getByRole("textbox",{name:"所属机构"}),{target:{value:"新机构"}});
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("临时失败");
  expect(screen.getByRole("textbox",{name:"所属机构"})).toHaveValue("新机构");
  expect(close).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(()=>expect(close).toHaveBeenCalledTimes(1));
  expect(save).toHaveBeenLastCalledWith({institution:"新机构",expected_values:{institution:"原机构"}});
  unmount(); expect(dirty).toHaveBeenLastCalledWith(false);
});

function RegistryPage(){const navigate=useNavigate();return <><button onClick={()=>navigate("/analysis/center")}>进入其他页面</button><SampleRegistry/></>;}
it("样本管理页面离开保护由父页面汇总，取消离开可继续保存",async()=>{
  const router=createMemoryRouter([{path:"/management/samples",element:<RegistryPage/>},{path:"/analysis/center",element:<p>分析目标</p>}],{initialEntries:["/management/samples"]});
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"编辑"}));
  fireEvent.change(screen.getByRole("textbox",{name:"疾病"}),{target:{value:"新疾病"}});
  fireEvent.click(screen.getByRole("button",{name:"进入其他页面"}));
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(router.state.location.pathname).toBe("/management/samples");
  expect(screen.getByRole("textbox",{name:"疾病"})).toHaveValue("新疾病");
  fireEvent.click(screen.getByRole("button",{name:"进入其他页面"}));
  fireEvent.click(await screen.findByRole("button",{name:"放弃并离开"}));
  expect(await screen.findByText("分析目标")).toBeVisible();
});

it("文件说明关闭确认保留修改，未修改的关闭无需确认",()=>{
  render(<AssetTable projectId="p" assets={[asset]} loading={false}/>);
  fireEvent.click(screen.getByRole("button",{name:"更多操作：指标.csv"}));
 fireEvent.click(screen.getByRole("button",{name:"修改 指标.csv 的数据集归属"}));
  fireEvent.click(within(screen.getByRole("dialog",{name:"修改文件信息"})).getByRole("button",{name:"关闭"}));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"更多操作：指标.csv"}));
 fireEvent.click(screen.getByRole("button",{name:"修改 指标.csv 的数据集归属"}));
  fireEvent.change(screen.getByRole("textbox",{name:"文件说明"}),{target:{value:"新说明"}});
  fireEvent.keyDown(document,{key:"Escape"});
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("textbox",{name:"文件说明"})).toHaveValue("新说明");
  fireEvent.keyDown(document,{key:"Escape"});
  fireEvent.click(screen.getByRole("button",{name:"放弃修改并关闭"}));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

function detailRouter(search:string){return createMemoryRouter([{path:"/management/projects/:projectId",element:<ProjectDetail/>},{path:"/analysis/center",element:<p>分析目标</p>}],{initialEntries:["/management/projects/p"+search]});}
it("项目文件筛选和页签切换不直接卸载未保存编辑",async()=>{
  const router=detailRouter("?tab=assets&asset_set=甲");
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"更多操作：指标.csv"}));
 fireEvent.click(await screen.findByRole("button",{name:"修改 指标.csv 的数据集归属"}));
  fireEvent.change(screen.getByRole("textbox",{name:"文件说明"}),{target:{value:"保留这项编辑"}});
  await router.navigate("?tab=assets&asset_set=甲&file_page=2");
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(new URLSearchParams(router.state.location.search).has("file_page")).toBe(false);
  expect(screen.getByRole("textbox",{name:"文件说明"})).toHaveValue("保留这项编辑");
  fireEvent.click(screen.getByRole("tab",{name:"样本"}));
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("assets");
  expect(screen.getByRole("textbox",{name:"文件说明"})).toHaveValue("保留这项编辑");
});

it("项目概览分析快捷卡保留显式数据集范围",async()=>{
  const router=detailRouter("?tab=overview&asset_set=乙");
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"开始分析"}));
  await screen.findByText("分析目标");
  expect(new URLSearchParams(router.state.location.search).get("project")).toBe("p");
  expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("乙");
});
