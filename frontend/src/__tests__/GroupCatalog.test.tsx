import { StrictMode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter, useLocation } from "react-router-dom";
import { ProjectGroupSpecs } from "../features/projects/ProjectGroupSpecs";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { apiClient } from "../shared/api/client";
import * as projects from "../shared/api/projects";
const groups=Array.from({length:1500},(_,index)=>({name:`组${String(index+1).padStart(4,"0")}`,color:index%2?"blue":"red",note:`原属性${index}`}));
const rows=Array.from({length:23},(_,index)=>({id:`s${index+1}`,project_id:"p",name:`方案${String(index+1).padStart(2,"0")}`,revision:"summary-version",group_count:1500,
  group_preview:groups.slice(0,6).map(group=>group.name),group_field:"",asset_set:"甲",project_wide:false,source:{asset_id:null,name:"",asset_set:"甲",available:true,reason:""}}));
const full=(id:string)=>({id,project_id:"p",name:rows.find(row=>row.id===id)?.name || "页外方案",revision:"full-version",source:{asset_id:null,name:"",asset_set:id==="other"?"乙":"甲",available:true,reason:""},
  spec_json:{groups,asset_set:id==="other"?"乙":"甲",description:"完整属性",plot:{palette:"原配色"}}});
let failure="", mismatch=false;
beforeEach(()=>{
 failure="";mismatch=false;
 vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[],pagination:{page:1,page_size:20,total:0,total_pages:0}});
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:["甲","乙"].map(name=>({name,input_count:1,kinds:{profile:{count:1,statuses:{valid:1},sample_min:1,sample_max:1}}}))});
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"合成项目",asset_counts:{},group_specs:[]} as never);
 vi.spyOn(apiClient,"get").mockImplementation(async (url,params)=>{
  if(url.endsWith("/group-specs")){
   const page=Number(params?.page || 1),q=String(params?.q || "");
   const items=rows.filter(row=>row.name.includes(q));
   return {items:items.slice((page-1)*20,page*20),pagination:{page,page_size:20,total:items.length,total_pages:Math.ceil(items.length/20)}} as never;
  }
  if(url.includes("/group-specs/")){
   if(failure)throw new Error(failure);
   const id=url.split("/").pop()!;return {group_spec:{...full(id),...(mismatch?{id:"unexpected"}:{})}} as never;
  }
  return {} as never;
 });
 vi.spyOn(apiClient,"post").mockResolvedValue({});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});
function Address(){return <output aria-label="当前地址">{useLocation().search}</output>;}
function open(search="?asset_set=甲") {
 return render(<StrictMode><MemoryRouter initialEntries={["/"+search]}><ProjectGroupSpecs projectId="p" loading={false} managed onChanged={vi.fn()}/><Address/></MemoryRouter></StrictMode>);
}
it("分组目录仅请求一页摘要，查询和翻页保留数据集，空搜索不会自动创建",async()=>{
 open();await screen.findByText("方案20");expect(screen.queryByText("方案21")).not.toBeInTheDocument();
 expect(screen.queryByRole("textbox",{name:"方案名称"})).not.toBeInTheDocument();
 expect(apiClient.get).toHaveBeenCalledWith("/api/projects/p/group-specs",expect.objectContaining({view:"summary",asset_set:"甲",page:1,page_size:20}),{skipCache:true});
 expect(vi.mocked(apiClient.get).mock.calls.some(([url])=>url.includes("/group-specs/"))).toBe(false);
 fireEvent.click(within(screen.getByRole("navigation",{name:"分组方案分页"})).getByRole("button",{name:"下一页"}));
 await screen.findByText("方案23");expect(screen.queryByText("方案01")).not.toBeInTheDocument();
 fireEvent.change(screen.getByRole("textbox",{name:"搜索分组方案名称"}),{target:{value:"方案01"}});fireEvent.click(screen.getByRole("button",{name:"查询方案"}));
 await screen.findByText("方案01");expect(screen.getByLabelText("当前地址").textContent).not.toContain("group_page=");
 expect(apiClient.get).toHaveBeenLastCalledWith("/api/projects/p/group-specs",expect.objectContaining({q:"方案01",asset_set:"甲",page:1}),{skipCache:true});
});
it("编辑先按ID取完整定义，保存1500组反序时保留对象属性和最新版本",async()=>{
 open();fireEvent.click(await screen.findByRole("button",{name:"编辑方案：方案01"}));
 const input=await screen.findByRole("textbox",{name:"分组名称（按顺序，用逗号或顿号分隔）"});
 expect(input).toHaveValue(groups.map(group=>group.name).join("、"));
 fireEvent.change(input,{target:{value:[...groups].reverse().map(group=>group.name).join("、")}});
 fireEvent.click(screen.getByRole("button",{name:"保存"}));
 await waitFor(()=>expect(apiClient.post).toHaveBeenCalledWith("/api/projects/p/group-specs?view=detail",{id:"s1",expected_revision:"full-version",name:"方案01",spec_json:{...full("s1").spec_json,groups:[...groups].reverse()}}));
});
it("详情读取失败或身份不匹配时不覆盖正在编辑的草稿",async()=>{
 open();await screen.findByText("方案01");fireEvent.click(screen.getByRole("button",{name:"新建分组方案"}));
 fireEvent.change(screen.getByRole("textbox",{name:"方案名称"}),{target:{value:"未保存草稿"}});
 failure="详情断连";fireEvent.click(screen.getByRole("button",{name:"编辑方案：方案01"}));await screen.findByText("详情断连");
 expect(screen.getByRole("textbox",{name:"方案名称"})).toHaveValue("未保存草稿");
 failure="";mismatch=true;fireEvent.click(screen.getByRole("button",{name:"编辑方案：方案01"}));await screen.findByText(/返回的完整分组定义不匹配/);
 expect(screen.getByRole("textbox",{name:"方案名称"})).toHaveValue("未保存草稿");expect(apiClient.post).not.toHaveBeenCalled();
});
it("页外深链读取准确方案，并对跨数据集方案给出所属范围入口",async()=>{
 open("?asset_set=甲&group_spec=other&group_page=2");
 const section=await screen.findByRole("region",{name:"链接指定分组方案"});await within(section).findByText("页外方案");
 expect(within(section).getByRole("link",{name:"切换到所属数据集查看"})).toHaveAttribute("href",expect.stringContaining("asset_set=%E4%B9%99"));
 expect(within(section).queryByRole("button",{name:/编辑方案/})).not.toBeInTheDocument();
 expect(apiClient.get).toHaveBeenCalledWith("/api/projects/p/group-specs/other",undefined,{skipCache:true,deduplicate:false});
});
it("复制手工方案时读取完整定义且保留全部组和其他属性",async()=>{
 open();fireEvent.click(await screen.findByRole("button",{name:"更多操作：方案01"}));
 fireEvent.click(screen.getByRole("button",{name:"复制手工方案"}));
 await screen.findByRole("textbox",{name:"分组名称（按顺序，用逗号或顿号分隔）"});
 await waitFor(()=>expect(screen.getByRole("button",{name:"保存"})).toBeEnabled());
 fireEvent.click(screen.getByRole("button",{name:"保存"}));
 await waitFor(()=>expect(apiClient.post).toHaveBeenCalledWith("/api/projects/p/group-specs?view=detail",{name:"方案01（新版本）",spec_json:full("s1").spec_json}));
});
it("项目页面概况不附全集，取消范围切换保留草稿，确认放弃后编辑器清空",async()=>{
 const router=createMemoryRouter([{path:"/management/projects/:projectId",element:<ProjectDetail/>}],{initialEntries:["/management/projects/p?tab=group-specs&asset_set=甲"]});
 render(<RouterProvider router={router}/>);await screen.findByText("方案01");
 expect(projects.getProject).toHaveBeenCalledWith("p",{summaryOnly:true,includeGroupSpecs:false});
 fireEvent.click(screen.getByRole("button",{name:"编辑方案：方案01"}));
 fireEvent.change(await screen.findByRole("textbox",{name:"方案名称"}),{target:{value:"甲的未保存编辑"}});
 async function switchScope(){fireEvent.click(screen.getByRole("button",{name:"切换当前数据集"}));fireEvent.click(await screen.findByRole("option",{name:"乙"}));}
 await switchScope();fireEvent.click(await screen.findByRole("button",{name:"继续编辑"}));
 expect(screen.getByRole("textbox",{name:"方案名称"})).toHaveValue("甲的未保存编辑");expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("甲");
 await switchScope();fireEvent.click(await screen.findByRole("button",{name:"放弃并离开"}));
 await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("乙"));
 expect(screen.queryByRole("textbox",{name:"方案名称"})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"新建分组方案"}));expect(screen.getByRole("textbox",{name:"方案名称"})).toHaveValue("");
});
