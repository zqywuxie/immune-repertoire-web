import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router-dom";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import { SampleEditSheet } from "../features/samples/SampleEditSheet";
import * as samples from "../shared/api/samples";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
import type { SampleRecord } from "../shared/api/samples";

const sample={id:"r",project_id:"p",project_name:"项目",sample_id:"001",sample_name:"名称",spices:"人",institution:null,sequence_id:null,chain_flag:null,is_healthy:null,illness:"疾病甲",is_pe:null,contain_method:null,iso_tag:null,created_at:null,updated_at:null,extra_metadata:{asset_set:"甲",source_asset_id:"a",manual_fields:["illness","institution"],registration_kind:"imported"}} as SampleRecord;
beforeEach(()=>{
  vi.spyOn(samples,"listSamples").mockResolvedValue({samples:[sample]});
  vi.spyOn(samples,"getSampleFieldOptions").mockResolvedValue({fields:{illness:["疾病甲","疾病乙"],spices:["人","小鼠"]}});
  vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"项目"} as never);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});

it("逐项移除多物种和疾病筛选保留其他条件与数据集",async()=>{
  render(<MemoryRouter initialEntries={["/?project_id=p&asset_set=甲&spices=human,mouse&illness=疾病甲,疾病乙&institution=机构"]}><SampleRegistry/></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button",{name:"移除物种筛选：人"}));
  await waitFor(()=>expect(samples.listSamples).toHaveBeenLastCalledWith(expect.objectContaining({project_id:"p",asset_set:"甲",spices:"mouse",illness:"疾病甲,疾病乙",institution:"机构"})));
  fireEvent.click(screen.getByRole("button",{name:"移除疾病筛选：疾病甲"}));
  await waitFor(()=>expect(samples.listSamples).toHaveBeenLastCalledWith(expect.objectContaining({spices:"mouse",illness:"疾病乙",institution:"机构"})));
  expect(screen.getByRole("button",{name:"移除疾病筛选：疾病乙"})).toBeVisible();
});

it("疾病候选多选与自定义条件写入URL，后退恢复选择",async()=>{
  const router=createMemoryRouter([{path:"*",element:<SampleRegistry/>}],{initialEntries:["/?project_id=p&asset_set=甲&illness=疾病甲"]});
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByText("疾病 · 疾病甲"));
  const group=screen.getByRole("group",{name:"疾病多选"});
  fireEvent.click(within(group).getByRole("checkbox",{name:"疾病乙"}));
  await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("illness")).toBe("疾病甲,疾病乙"));
  fireEvent.change(screen.getByRole("textbox",{name:"添加自定义疾病筛选"}),{target:{value:"自定义病种"}});
  fireEvent.click(screen.getByRole("button",{name:"添加条件"}));
  await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("illness")).toBe("疾病甲,疾病乙,自定义病种"));
  await router.navigate(-1);
  await waitFor(()=>expect(screen.getByText("疾病 · 疾病甲、疾病乙")).toBeVisible());
  expect(within(group).getByRole("checkbox",{name:"疾病甲"})).toBeChecked();
  expect(within(group).getByRole("checkbox",{name:"疾病乙"})).toBeChecked();
  expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("甲");
});

it("登记列表展示数据集与来源，人工字段展开中文说明",async()=>{
  render(<MemoryRouter><SampleRegistry/></MemoryRouter>);
  const row=await screen.findByRole("row",{name:/001 名称/});
  expect(within(row).getByRole("cell",{name:"甲"})).toBeVisible();
  expect(within(row).getByText("来源表导入")).toBeVisible();
  fireEvent.click(within(row).getByText("人工维护 2 项"));
  expect(within(row).getByText("疾病、所属机构")).toBeVisible();
});

it("登记编辑显示人工维护字段，只提交真正变化不会重写来源",async()=>{
  const save=vi.fn().mockResolvedValue(undefined);
  render(<SampleEditSheet sample={sample} open onSave={save} onClose={vi.fn()}/>);
  expect(screen.getByText("疾病、所属机构")).toBeVisible();
  expect(screen.getByText(/这些字段在来源表更新后仍保留/)).toBeVisible();
  fireEvent.change(screen.getByRole("textbox",{name:"疾病"}),{target:{value:""}});
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(()=>expect(save).toHaveBeenCalledWith({illness:"",expected_values:{illness:"疾病甲"}}));
});
