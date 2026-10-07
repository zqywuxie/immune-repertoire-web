import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router-dom";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { ProjectLibrary } from "../pages/management/ProjectLibrary";
import { ManagementDashboard } from "../pages/management/ManagementDashboard";
import { ProjectPicker } from "../features/projects/ProjectPicker";
import * as projects from "../shared/api/projects";
import * as jobs from "../shared/api/jobs";
import { apiClient } from "../shared/api/client";

const statistics = {project_count:301,status_counts:{active:220,archived:81},file_count:912,result_count:120,input_sample_count:608,registered_sample_count:100,dataset_count:8,group_spec_count:3};
const project=(id:string,name=id)=>({id,name,status:"active",asset_counts:{profile:1},input_sample_count:1,result_count:0});
const page=(rows:ReturnType<typeof project>[],number=1,total=60,size=24)=>({projects:rows,pagination:{page:number,page_size:size,total,total_pages:Math.ceil(total/size)}});
beforeEach(()=>{vi.spyOn(projects,"getProjectStatistics").mockResolvedValue(statistics);vi.spyOn(projects,"getProject").mockImplementation(async id=>({...project(id,"已选历史项目"),assets:[]}));});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
function routerAt(query="") {return createMemoryRouter([{path:"/management/projects",element:<ProjectLibrary/>},{path:"/management/projects/:projectId",element:<p>项目详情</p>}],{initialEntries:["/management/projects"+query]});}

it("项目分页和返回保留服务器筛选排序与视图，全局统计不随当前页变化",async()=>{
  const list=vi.spyOn(projects,"listProjects").mockImplementation(async params=>page([project(`p${params?.page}`,`第${params?.page}页研究`)],params?.page));
  const router=routerAt("?q=免疫&status=active&sort=name_asc&page=2&layout=list");render(<RouterProvider router={router}/>);
  expect(await screen.findByRole("link",{name:"第2页研究"})).toBeVisible();expect(list).toHaveBeenCalledWith(expect.objectContaining({page:2,search:"免疫",status:"active",sort:"name_asc"}));
  expect(screen.getByText("301")).toBeVisible();expect(screen.getByText(/匹配 60 个项目/)).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));await screen.findByRole("link",{name:"第3页研究"});
  expect(screen.getByText("301")).toBeVisible();expect(projects.getProjectStatistics).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("link",{name:"第3页研究"}));await screen.findByText("项目详情");
  await act(async()=>{await router.navigate(-1);});await screen.findByRole("link",{name:"第3页研究"});
  const query=new URLSearchParams(router.state.location.search);expect(Object.fromEntries(query)).toMatchObject({page:"3",q:"免疫",status:"active",sort:"name_asc",layout:"list"});
});

it("搜索访问未加载的项目且重置页码，排序状态继续保留",async()=>{
  const list=vi.spyOn(projects,"listProjects").mockImplementation(async params=>page([project("remote",params?.search?"远端条件匹配项目":"旧页项目")],params?.page,60));
  const router=routerAt("?page=2&status=archived&sort=updated_desc&layout=list");render(<RouterProvider router={router}/>);await screen.findByRole("link",{name:"旧页项目"});
  fireEvent.change(screen.getByPlaceholderText("搜索项目名称或机构…"),{target:{value:"远端"}});
  await screen.findByRole("link",{name:"远端条件匹配项目"});expect(list).toHaveBeenLastCalledWith(expect.objectContaining({search:"远端",page:1,status:"archived",sort:"updated_desc"}));
  expect(new URLSearchParams(router.state.location.search).has("page")).toBe(false);
  fireEvent.click(screen.getByRole("button",{name:"项目排序"}));fireEvent.click(screen.getByRole("option",{name:"名称降序"}));
  await waitFor(()=>expect(list).toHaveBeenLastCalledWith(expect.objectContaining({sort:"name_desc",search:"远端",status:"archived"})));
});

it("全局统计读取失败显示重试，不将第一页统计充当全部统计",async()=>{
  vi.mocked(projects.getProjectStatistics).mockRejectedValueOnce(new Error("统计服务暂不可用"));
  vi.spyOn(projects,"listProjects").mockResolvedValue(page([project("p1","列表仍可使用")],1,1));
  render(<MemoryRouter><ProjectLibrary/></MemoryRouter>);expect(await screen.findByText(/统计服务暂不可用/)).toBeVisible();expect(screen.queryByText("项目总数")).toBeNull();
  expect(await screen.findByText("列表仍可使用")).toBeVisible();fireEvent.click(screen.getByRole("button",{name:"重新读取统计"}));await screen.findByText("301");
});

it("项目选择器支持分页搜索并固定页外已选项目，不因翻页自动换项目",async()=>{
  const list=vi.spyOn(projects,"listProjects").mockImplementation(async params=>page([project(params?.search?"target":`page${params?.page}`,params?.search?"搜索到的项目":`候选第${params?.page}页`)],params?.page,45,20));
  const change=vi.fn();render(<MemoryRouter><ProjectPicker value="saved" onChange={change}/></MemoryRouter>);
  await screen.findByText("已选历史项目");fireEvent.click(screen.getByRole("button",{name:"项目下一页"}));
  await waitFor(()=>expect(list).toHaveBeenLastCalledWith(expect.objectContaining({view:"selector",page:2,pageSize:20})));
  expect(change).not.toHaveBeenCalled();expect(screen.getByText("已选历史项目")).toBeVisible();
  fireEvent.change(screen.getByRole("textbox",{name:"搜索项目"}),{target:{value:"搜索到"}});
  await waitFor(()=>expect(list).toHaveBeenLastCalledWith(expect.objectContaining({search:"搜索到",page:1})));
  fireEvent.click(screen.getByRole("button",{name:"项目"}));fireEvent.click(screen.getByRole("option",{name:"搜索到的项目"}));expect(change).toHaveBeenCalledWith("target");
});

it("搜索零结果保留已选项目，不误报账号没有项目",async()=>{
  vi.spyOn(projects,"listProjects").mockImplementation(async params=>params?.search?page([],1,0,20):page([project("saved","当前研究")],1,1,20));
  const availability=vi.fn(),change=vi.fn();render(<MemoryRouter><ProjectPicker value="saved" onChange={change} onAvailability={availability}/></MemoryRouter>);
  await screen.findByText("当前研究");fireEvent.change(screen.getByRole("textbox",{name:"搜索项目"}),{target:{value:"不存在"}});
  await screen.findByText(/没有符合条件的项目/);expect(availability).toHaveBeenLastCalledWith(true);expect(change).not.toHaveBeenCalled();await waitFor(() => expect(screen.getByRole("button",{name:"项目"})).toHaveTextContent("已选历史项目"));
});

it("页外项目名称读取失败保留选择并可重试",async()=>{
  vi.spyOn(projects,"listProjects").mockResolvedValue(page([],1,0,20));vi.mocked(projects.getProject).mockRejectedValueOnce(new Error("项目详情断连"));const change=vi.fn();
  render(<MemoryRouter><ProjectPicker value="saved" onChange={change}/></MemoryRouter>);await screen.findByText(/项目详情断连/);
  expect(screen.getByRole("button",{name:"项目"})).toHaveTextContent("当前项目（名称读取失败）");expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"重新读取当前项目"}));await screen.findByText("已选历史项目");
});

it("概览只读取最近四个项目但显示全局项目和结果数量",async()=>{
  const list=vi.spyOn(projects,"listProjects").mockResolvedValue(page([project("recent","最近研究")],1,301,4));vi.spyOn(jobs,"listJobs").mockResolvedValue({jobs:[],counts:{running:2,queued:3}} as never);
  render(<MemoryRouter><ManagementDashboard/></MemoryRouter>);await screen.findByText("最近研究");expect(screen.getByText("301")).toBeVisible();expect(screen.getByText("120")).toBeVisible();
  expect(list).toHaveBeenCalledWith({pageSize:4,sort:"updated_desc"});expect(screen.getByText("5")).toBeVisible();
});

it("详情中的项目管理返回按钮也保留原页码筛选和列表视图",async()=>{
  vi.spyOn(projects,"listProjects").mockResolvedValue(page([project("p2","第二页研究")],2,60));
  const router=createMemoryRouter([{path:"/management/projects",element:<ProjectLibrary/>},{path:"/management/projects/:projectId",element:<ProjectDetail/>}],{initialEntries:["/management/projects?q=研究&sort=name_asc&page=2&layout=list"]});
  render(<RouterProvider router={router}/>);fireEvent.click(await screen.findByRole("link",{name:"第二页研究"}));
  await screen.findByRole("heading",{name:"已选历史项目",level:1});fireEvent.click(screen.getByRole("button",{name:"项目管理"}));await screen.findByRole("link",{name:"第二页研究"});
  expect(Object.fromEntries(new URLSearchParams(router.state.location.search))).toMatchObject({q:"研究",sort:"name_asc",page:"2",layout:"list"});
});

it("筛选中创建项目后可直接打开新项目并保留返回范围", async () => {
  vi.spyOn(projects,"listProjects").mockResolvedValue(page([], 1, 0));
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ok:true,json:async()=>({id:"new-project",name:"新研究"})}));
  const router = routerAt("?q=旧研究&status=archived&sort=name_asc&layout=list");
  render(<RouterProvider router={router}/>);
  fireEvent.click(screen.getByRole("button", {name:"新建项目"}));
  fireEvent.change(screen.getByPlaceholderText("项目名称"), {target:{value:"新研究"}});
  fireEvent.click(screen.getByRole("button", {name:"保存"}));
  fireEvent.click(await screen.findByRole("link", {name:"打开新项目"}));
  await screen.findByText("项目详情");
  expect(router.state.location.pathname).toBe("/management/projects/new-project");
  expect(router.state.location.state.projectCatalogReturn).toContain("q=旧研究");
  expect(router.state.location.state.projectCatalogReturn).toContain("status=archived");
});
