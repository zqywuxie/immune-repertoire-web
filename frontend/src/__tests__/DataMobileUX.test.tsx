import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, afterEach, expect, it, vi } from "vitest";
import { MemoryRouter, RouterProvider, createMemoryRouter } from "react-router-dom";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { ProjectInputSamples } from "../features/assets/ProjectInputSamples";
import { AssetTable } from "../features/assets/AssetTable";
import * as sampleApi from "../shared/api/samples";
import * as projectApi from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
import type { SampleRecord } from "../shared/api/samples";
import type { ProjectAsset } from "../shared/types/domain";

const sample={id:"r",project_id:"p",project_name:"研究项目",sample_id:"001",sample_name:"登记名称",spices:"人",institution:null,sequence_id:null,chain_flag:"TRA",is_healthy:null,illness:"疾病甲",is_pe:null,contain_method:null,iso_tag:null,created_at:null,updated_at:null,extra_metadata:{asset_set:"甲",registration_kind:"manual"}} as SampleRecord;
const asset={id:"a",project_id:"p",asset_type:"profile",original_name:"指标.csv",storage_path:"/synthetic/a.csv",size:1,metadata:{asset_set:"甲",validation:{status:"valid"}}} as ProjectAsset;
function viewport(initial:number){
  let width=initial;const listeners=new Set<()=>void>();
  vi.stubGlobal("matchMedia",vi.fn().mockImplementation(query=>({media:query,get matches(){return width<=768;},
    addEventListener:(_event:string,listener:()=>void)=>listeners.add(listener),removeEventListener:(_event:string,listener:()=>void)=>listeners.delete(listener)})));
  return (next:number)=>act(()=>{width=next;listeners.forEach(listener=>listener());});
}
beforeEach(()=>{
  viewport(390);
  vi.spyOn(sampleApi,"listSamples").mockResolvedValue({samples:[sample],pagination:{page:1,page_size:50,total:1,total_pages:1}});
  vi.spyOn(sampleApi,"getSampleFieldOptions").mockResolvedValue({fields:{spices:["人","小鼠"],illness:["疾病甲","疾病乙"]}});
  vi.spyOn(projectApi,"getProject").mockResolvedValue({id:"p",name:"研究项目",asset_counts:{},asset_status:{},group_specs:[]} as never);
  vi.spyOn(projectApi,"listProjectAssets").mockResolvedValue({assets:[asset]});
  vi.spyOn(projectApi,"listProjectDatasets").mockResolvedValue({datasets:[]});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});

it("手机筛选修改和Esc不触发查询，应用时一次更新并保留项目、数据集与搜索",async()=>{
  const router=createMemoryRouter([{path:"*",element:<SampleRegistry/>}],{initialEntries:["/?project_id=p&asset_set=甲&illness=疾病甲&q=检索&page=3"]});
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"筛选条件（1）"}));
  const reads=vi.mocked(sampleApi.listSamples).mock.calls.length;
  fireEvent.change(screen.getByRole("combobox",{name:/链类型/}),{target:{value:"TRB"}});
  expect(vi.mocked(sampleApi.listSamples).mock.calls.length).toBe(reads);
  fireEvent.keyDown(document,{key:"Escape"});
  expect(screen.queryByRole("dialog",{name:"样本筛选"})).not.toBeInTheDocument();
  expect(new URLSearchParams(router.state.location.search).get("chain_flag")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"筛选条件（1）"}));
  expect(screen.getByRole("combobox",{name:/链类型/})).toHaveValue("");
  fireEvent.change(screen.getByRole("combobox",{name:/链类型/}),{target:{value:"TRB"}});
  fireEvent.click(screen.getByRole("button",{name:"应用筛选"}));
  await waitFor(()=>expect(sampleApi.listSamples).toHaveBeenLastCalledWith(expect.objectContaining({project_id:"p",asset_set:"甲",q:"检索",chain_flag:"TRB",illness:"疾病甲",page:1})));
  expect(screen.queryByRole("dialog",{name:"样本筛选"})).not.toBeInTheDocument();
});

it("手机重置条件只修改待应用内容，保留范围和文本搜索",async()=>{
  const router=createMemoryRouter([{path:"*",element:<SampleRegistry/>}],{initialEntries:["/?project_id=p&asset_set=甲&spices=human&illness=疾病甲&q=001"]});
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"筛选条件（2）"}));
  fireEvent.click(screen.getByRole("button",{name:"重置条件"}));
  expect(new URLSearchParams(router.state.location.search).get("spices")).toBe("human");
  fireEvent.click(screen.getByRole("button",{name:"应用筛选"}));
  await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("spices")).toBeNull());
  const query=new URLSearchParams(router.state.location.search);
  expect(query.get("illness")).toBeNull();expect(query.get("project_id")).toBe("p");expect(query.get("asset_set")).toBe("甲");expect(query.get("q")).toBe("001");
});

it("手机样本编辑直接可见，缩放到桌面仍保留未保存表单",async()=>{
  const resize=viewport(390);
  render(<MemoryRouter><SampleRegistry/></MemoryRouter>);
  const card=await screen.findByRole("article",{name:"样本 001 · 甲"});
  expect(within(card).getByText(/数据集：甲/)).toBeVisible();
  fireEvent.click(within(card).getByRole("button",{name:"编辑样本 001（甲）"}));
  fireEvent.change(screen.getByRole("textbox",{name:"疾病"}),{target:{value:"手机草稿"}});
  resize(1440);
  expect(screen.getByRole("textbox",{name:"疾病"})).toHaveValue("手机草稿");
  expect(await screen.findByRole("row",{name:/001 登记名称/})).toBeVisible();
  fireEvent.keyDown(document,{key:"Escape"});
  expect(screen.getByRole("dialog",{name:"放弃未保存的样本信息"})).toBeVisible();
});

it("手机文件可直接查看或从操作面板编辑，选择状态与放弃保护保留",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({})}));
  vi.spyOn(apiClient,"get").mockResolvedValue({columns:["sample"],rows:[["001"]]});
  render(<MemoryRouter><AssetTable projectId="p" assets={[asset]} loading={false} showGroup/></MemoryRouter>);
  fireEvent.click(screen.getByRole("checkbox",{name:"选择 指标.csv"}));
  fireEvent.click(screen.getByRole("button",{name:"查看 指标.csv"}));
  expect(await screen.findByRole("dialog",{name:"文件详情与校验"})).toBeVisible();
  fireEvent.click(within(screen.getByRole("dialog",{name:"文件详情与校验"})).getByRole("button",{name:"关闭"}));
  fireEvent.click(screen.getByRole("button",{name:"更多操作：指标.csv"}));
  fireEvent.click(screen.getByRole("button",{name:"修改文件信息"}));
  fireEvent.change(screen.getByRole("textbox",{name:"文件说明"}),{target:{value:"移动端维护"}});
  fireEvent.keyDown(document,{key:"Escape"});
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("textbox",{name:"文件说明"})).toHaveValue("移动端维护");
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await screen.findByText("文件信息已更新。");
  expect(screen.getByRole("checkbox",{name:"选择 指标.csv"})).toBeChecked();
});

it("手机输入样本按需展开真实来源，只有当前行忙，晚到的旧登记请求不会覆盖新选择",async()=>{
  let finishOld!: (value:unknown)=>void;
  const previous=new Promise(resolve=>{finishOld=resolve;});
  const rows=["001","002"].map(sample_id=>({sample_id,asset_set:"甲",needs_version_selection:false,coverage:{profile:[{asset_id:"a",name:"指标.csv",status:"valid"}]}}));
  vi.spyOn(apiClient,"get").mockImplementation(async (url,params)=>{
    if(String(url).endsWith("/registration")) return params?.sample_id==="001" ? previous : {sample:null,project_name:"研究项目"};
    return {samples:rows,unresolved:[],input_scopes:{甲:{profile:{asset_count:1,unresolved_count:0}}},note:"保留原编号",pagination:{page:1,page_size:50,total:2,total_pages:1}};
  });
  render(<MemoryRouter><ProjectInputSamples projectId="p" revision={0}/></MemoryRouter>);
  const first=await screen.findByRole("article",{name:"输入样本 001 · 甲"});
  fireEvent.click(within(first).getByText("查看输入来源 · 1 类"));
  const link=new URL(within(first).getByRole("link",{name:"指标.csv"}).getAttribute("href")!,"http://fixture");
  expect(link.searchParams.get("asset")).toBe("a");expect(link.searchParams.get("asset_set")).toBe("甲");
  fireEvent.click(screen.getByRole("button",{name:"补充样本 001 的登记信息"}));
  expect(screen.getByRole("button",{name:"补充样本 002 的登记信息"})).toBeEnabled();
  fireEvent.click(screen.getByRole("button",{name:"补充样本 002 的登记信息"}));
  await screen.findByRole("dialog",{name:"补充样本信息"});
  await act(async()=>{finishOld({sample:null,project_name:"研究项目"});await previous;});
  expect(within(screen.getByRole("dialog",{name:"补充样本信息"})).getByText("002", {exact:true})).toBeVisible();
  expect(screen.getByRole("textbox",{name:"样本名称"})).toHaveValue("002");
});

it("长项目名称可展开，手机概览明确全部数据集与项目总计",async()=>{
  const name="这是一个用于验证中文研究项目完整名称不会挤压手机操作入口的很长项目名称";
  vi.mocked(projectApi.getProject).mockResolvedValue({id:"p",name,asset_counts:{},group_specs:[],input_sample_count:2} as never);
  render(<RouterProvider router={createMemoryRouter([{path:"/management/projects/:projectId",element:<ProjectDetail/>}],{initialEntries:["/management/projects/p?tab=overview&asset_set=甲"]})}/>);
  const toggle=await screen.findByRole("button",{name:"展开完整项目名称"});
  fireEvent.click(toggle);expect(screen.getByRole("button",{name:"收起项目名称"})).toHaveAttribute("aria-expanded","true");
  expect(screen.getByRole("heading",{name})).toBeVisible();expect(screen.getByText("项目概览 · 全部数据集")).toBeVisible();expect(screen.getByText(/项目总计 · 2 个输入样本条目/)).toBeVisible();
});
