import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter, useLocation } from "react-router-dom";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { ProjectGroupSpecs } from "../features/projects/ProjectGroupSpecs";
import { Sidebar } from "../shared/components/Sidebar";
import { WorkspaceProvider } from "../shared/context/WorkspaceContext";
import { ProjectInputSamples } from "../features/assets/ProjectInputSamples";
import { AssetTable } from "../features/assets/AssetTable";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
import type { ProjectAsset } from "../shared/types/domain";

vi.mock("../shared/context/AuthContext", () => ({ useAuth: () => ({user:{auth_mode:"internal"},logout:vi.fn()}) }));
const asset = {id:"a",project_id:"p",asset_type:"profile",original_name:"同名.csv",storage_path:"/synthetic/a.csv",size:1,metadata:{asset_set:"甲",content_version:"v-a"}} as ProjectAsset;
beforeEach(()=>{
  vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"研究项目",asset_counts:{},group_specs:[]} as never);
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[asset]});
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[]});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
function detailRouter(search:string){return createMemoryRouter([{path:"/management/projects/:projectId",element:<ProjectDetail/>},{path:"/analysis/center",element:<p>分析目标</p>}],{initialEntries:["/management/projects/p"+search]});}

it("设置页修改后切换标签需确认，保存成功清除保护",async()=>{
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,json:async()=>({})}));
  const router=detailRouter("?tab=settings&asset_set=甲");
  render(<RouterProvider router={router}/>);
  fireEvent.change(await screen.findByRole("textbox",{name:"项目名称（必填）"}),{target:{value:"修改项目"}});
  fireEvent.click(screen.getByRole("tab",{name:"概览"}));
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("textbox",{name:"项目名称（必填）"})).toHaveValue("修改项目");
  fireEvent.click(screen.getByRole("button",{name:"保存修改"}));
  await screen.findByRole("button",{name:"已保存"});
  fireEvent.click(screen.getByRole("tab",{name:"概览"}));
  await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("overview"));
  expect(screen.queryByRole("dialog",{name:"离开前确认未保存内容"})).not.toBeInTheDocument();
});

it("顶部项目编辑也纳入父页面路由保护",async()=>{
  const router=detailRouter("?tab=overview&asset_set=甲");
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("button",{name:"编辑项目"}));
  fireEvent.change(screen.getByRole("textbox",{name:"名称 *"}),{target:{value:"草稿项目"}});
  await router.navigate("/analysis/center?project=p&asset_set=甲");
  fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("textbox",{name:"名称 *"})).toHaveValue("草稿项目");
  expect(router.state.location.pathname).toBe("/management/projects/p");
});

function CurrentRoute(){const location=useLocation();return <output aria-label="地址">{location.pathname+location.search}</output>;}
it("项目详情切换分析工作台及工具后继续保留项目和数据集",()=>{
  render(<MemoryRouter initialEntries={["/management/projects/p?tab=assets&asset_set=甲"]}><WorkspaceProvider><Sidebar/><CurrentRoute/></WorkspaceProvider></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"分析工作台"}));
  expect(screen.getByLabelText("地址")).toHaveTextContent("/analysis/center?project=p&asset_set=%E7%94%B2");
  for(const name of ["分析中心","任务与结果"]){const path=new URL(screen.getByRole("link",{name}).getAttribute("href")!,"http://synthetic");expect(path.searchParams.get("project")).toBe("p");expect(path.searchParams.get("asset_set")).toBe("甲");}
  fireEvent.click(screen.getByRole("button",{name:"数据管理"}));
  expect(screen.getByLabelText("地址")).toHaveTextContent("/management/projects/p?tab=assets&asset_set=%E7%94%B2");
});

it("分组计数只请求摘要，自定义顺序切换字段可取消或确认",async()=>{
  const post=vi.spyOn(apiClient,"post").mockResolvedValue({columns:["sample","group","other"],sheets:[],selected_sheet:null,requires_sheet_selection:false});
  const get=vi.spyOn(apiClient,"get").mockResolvedValue({values:["A","B"],samples_by_value:{},sample_counts:{A:1000,B:2500},row_counts:{A:1001,B:2501},sample_column:"sample",asset_set:"甲",content_version:"v-a"});
  render(<MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectGroupSpecs projectId="p" loading={false} groupSpecs={[]} onChanged={vi.fn()}/></MemoryRouter>);
  fireEvent.change(screen.getByRole("textbox",{name:"方案名称"}),{target:{value:"真实顺序"}});
  await waitFor(()=>expect(screen.getByRole("button",{name:"方案来源指标表"})).toBeEnabled());
  fireEvent.click(screen.getByRole("button",{name:"方案来源指标表"}));
  fireEvent.click(await screen.findByRole("option",{name:/甲 · 同名.csv/}));
  fireEvent.click(await screen.findByRole("button",{name:"方案分组字段"}));
  fireEvent.click(screen.getByRole("option",{name:"group"}));
  expect(await screen.findByText("2500 个样本编号")).toBeVisible();
  expect(get).toHaveBeenCalledWith("/api/projects/p/assets/a/group-values",expect.objectContaining({include_samples:false}),{skipCache:true});
  fireEvent.click(screen.getByRole("button",{name:"上移 B"}));
  fireEvent.click(screen.getByRole("button",{name:"方案分组字段"}));
  fireEvent.click(screen.getByRole("option",{name:"other"}));
  fireEvent.click(screen.getByRole("button",{name:"继续编辑"}));
  expect(screen.getByRole("list",{name:"分组展示顺序"}).firstElementChild).toHaveTextContent("1. B");
  fireEvent.click(screen.getByRole("button",{name:"方案分组字段"}));
  fireEvent.click(screen.getByRole("option",{name:"other"}));
  fireEvent.click(screen.getByRole("button",{name:"放弃修改并继续"}));
  await waitFor(()=>expect(screen.getByRole("list",{name:"分组展示顺序"}).firstElementChild).toHaveTextContent("1. A"));
  fireEvent.click(screen.getByRole("button",{name:"保存"}));
  await waitFor(()=>expect(post).toHaveBeenCalledWith("/api/projects/p/group-specs",expect.objectContaining({spec_json:expect.objectContaining({group_field:"other",groups:["A","B"]})})));
});

it("具体资产链接可读取列表页外的历史版本，关闭后保留筛选和页码",async()=>{
  vi.spyOn(projects,"getProjectAsset").mockResolvedValue({asset:{...asset,id:"old",metadata:{asset_set:"甲",superseded:true,content_version:"old-v"}}});
  vi.spyOn(apiClient,"get").mockResolvedValue({columns:[],rows:[],directory:false,files:[],pagination:{page:1,page_size:20,total:0,total_pages:0}});
  const router=detailRouter("?tab=assets&asset_set=甲&file_q=同名&file_page=2&asset=old");
  render(<RouterProvider router={router}/>);
  const dialog=await screen.findByRole("dialog",{name:"文件详情与校验"});
  expect(await within(dialog).findByText("old-v")).toBeVisible();
  expect(within(dialog).getByText(/这是保留的历史版本/)).toBeVisible();
  fireEvent.click(within(dialog).getByRole("button",{name:"关闭"}));
  await waitFor(()=>expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  const query=new URLSearchParams(router.state.location.search);
  expect(query.get("file_page")).toBe("2");expect(query.get("file_q")).toBe("同名");expect(query.has("asset")).toBe(false);
});

it("具体文件暂时无法读取时能重试或返回列表",async()=>{
  const load=vi.spyOn(projects,"getProjectAsset").mockRejectedValueOnce(new Error("temporary")).mockResolvedValueOnce({asset});
  const close=vi.fn();
  vi.spyOn(apiClient,"get").mockResolvedValue({columns:[],rows:[],directory:false,files:[],pagination:{page:1,page_size:20,total:0,total_pages:0}});
  render(<AssetTable projectId="p" focusedAssetId="a" assets={[]} loading={false} onCloseDetail={close}/>);
  fireEvent.click(await screen.findByRole("button",{name:"重新读取文件"}));
  expect(await screen.findByText("v-a")).toBeVisible();
  expect(load).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button",{name:"关闭"}));
  expect(close).toHaveBeenCalledTimes(1);
});

it("同名未识别文件和样本来源链接保留各自资产及数据集身份",async()=>{
  vi.spyOn(apiClient,"get").mockResolvedValue({samples:[{sample_id:"001",asset_set:"甲",coverage:{profile:[{asset_id:"a",name:"同名.csv",status:"valid"}]},needs_version_selection:false}],
    unresolved:[{asset_id:"b",name:"同名.csv",asset_set:"乙",kind:"profile",status:"needs_mapping"}],note:"范围明确",pagination:{page:1,page_size:50,total:1,total_pages:1}});
  render(<MemoryRouter><ProjectInputSamples projectId="p" revision={0}/></MemoryRouter>);
  const links=await screen.findAllByRole("link",{name:"同名.csv",hidden:true});
  const paths=links.map(link=>new URL(link.getAttribute("href")!,"http://synthetic"));
  expect(paths.map(path=>[path.searchParams.get("asset"),path.searchParams.get("asset_set")]).sort()).toEqual([["a","甲"],["b","乙"]]);
});


it.each(["settings", "overview"])("%s 编辑保存后丢弃旧缓存，概览立即显示服务端新名称", async tab=>{
  vi.mocked(projects.getProject).mockRestore();
  let saved={id:"p",name:"保存前项目",status:"active",asset_counts:{},group_specs:[]};
  let summaryReads=0;
  vi.stubGlobal("fetch",vi.fn().mockImplementation(async (_url,init)=>{
    if(init?.method==="PATCH") saved={...saved,...JSON.parse(init.body)};
    else summaryReads++;
    return {ok:true,headers:new Headers({"Content-Type":"application/json"}),json:async()=>({...saved})};
  }));
  render(<RouterProvider router={detailRouter(`?tab=${tab}&asset_set=甲`)}/>);
  if(tab==="overview") fireEvent.click(await screen.findByRole("button",{name:"编辑项目"}));
  fireEvent.change(await screen.findByRole("textbox",{name:tab==="settings"?"项目名称（必填）":"名称 *"}),{target:{value:"保存后项目"}});
  fireEvent.click(screen.getByRole("button",{name:tab==="settings"?"保存修改":"保存"}));
  await screen.findByRole("heading",{name:"保存后项目"});
  expect(summaryReads).toBe(2);
  if(tab==="settings") fireEvent.click(screen.getByRole("tab",{name:"概览"}));
  expect(screen.getAllByText("保存后项目").length).toBeGreaterThanOrEqual(2);
});
