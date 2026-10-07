import { useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, RouterProvider, createMemoryRouter, useLocation } from "react-router-dom";
import { ProjectGroupSpecs } from "../features/projects/ProjectGroupSpecs";
import { ProjectDatasetManager } from "../features/assets/ProjectDatasetManager";
import { ProjectInputSamples } from "../features/assets/ProjectInputSamples";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import * as projects from "../shared/api/projects";
import * as samplesApi from "../shared/api/samples";
import { apiClient } from "../shared/api/client";

const file=(id:string,type="profile")=>({id,project_id:"p",asset_type:type,original_name:`${id}.csv`,storage_path:`/inputs/${id}.csv`,size:1,metadata:{asset_set:"甲",validation:{status:"valid"}}} as any);
const pages=(page:number,total:number)=>({page,page_size:50,total,total_pages:Math.ceil(total/50)});
beforeEach(()=>{
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"项目",asset_counts:{},group_specs:[]} as any);
 vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[]});
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{name:"甲",input_count:51,kinds:{profile:{count:51,statuses:{valid:51},sample_min:1,sample_max:1}}}]});
 vi.spyOn(samplesApi,"getSampleFieldOptions").mockResolvedValue({fields:{}});
});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
function Address(){return <output aria-label="当前地址">{useLocation().search}</output>;}

it("无分组方案时取消编辑回到空态，点击新建后再打开",async()=>{
 render(<MemoryRouter><ProjectGroupSpecs projectId="p" loading={false} groupSpecs={[]} onChanged={vi.fn()}/></MemoryRouter>);
 expect(screen.getByRole("textbox",{name:"方案名称"})).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"取消编辑"}));
 expect(screen.queryByRole("textbox",{name:"方案名称"})).not.toBeInTheDocument();
 expect(screen.getByText(/暂无分组方案/)).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"新建分组方案"}));
 expect(screen.getByRole("textbox",{name:"方案名称"})).toBeVisible();
});

it("删除输入文件末页最后一项回到有效页，保留范围和搜索",async()=>{
 let removed=false;
 vi.mocked(projects.listProjectAssets).mockImplementation(async(_p,options={})=>({assets:options.page===2?(removed?[]:[file("末页指标")]):[file("首页指标")],pagination:pages(options.page||1,removed?50:51)}));
 vi.stubGlobal("fetch",vi.fn().mockImplementation(async()=>{removed=true;return {ok:true,json:async()=>({})};}));
 function Manager(){const[revision,setRevision]=useState(0);return <ProjectDatasetManager projectId="p" revision={revision} onChange={()=>setRevision(value=>value+1)}/>;}
 render(<MemoryRouter initialEntries={["/?asset_set=甲&file_q=指标&file_page=2&history=1"]}><Manager/><Address/></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:"更多操作：末页指标.csv"}));
 fireEvent.click(await screen.findByRole("button",{name:"删除 末页指标.csv"}));
 fireEvent.click(screen.getByRole("button",{name:"确认删除"}));
 await screen.findByRole("button",{name:"查看 首页指标.csv"});
 const query=new URLSearchParams(screen.getByLabelText("当前地址").textContent!);
 expect(query.get("file_page")).toBeNull();expect(query.get("file_q")).toBe("指标");expect(query.get("asset_set")).toBe("甲");expect(query.get("history")).toBe("1");
});

it("删除附件末页最后一项恢复有效页并保留数据集",async()=>{
 let removed=false;
 vi.mocked(projects.listProjectAssets).mockImplementation(async(_p,options={})=>({assets:options.page===2?(removed?[]:[file("末页附件","project_file")]):[file("首页附件","project_file")],pagination:pages(options.page||1,removed?50:51)}));
 vi.stubGlobal("fetch",vi.fn().mockImplementation(async()=>{removed=true;return {ok:true,json:async()=>({})};}));
 const router=createMemoryRouter([{path:"/management/projects/:projectId",element:<ProjectDetail/>}],{initialEntries:["/management/projects/p?tab=attachments&asset_set=甲&attachment_page=2"]});
 render(<RouterProvider router={router}/>);
 fireEvent.click(await screen.findByRole("button",{name:"更多操作：末页附件.csv"}));
 fireEvent.click(await screen.findByRole("button",{name:"删除 末页附件.csv"}));fireEvent.click(screen.getByRole("button",{name:"确认删除"}));
 await screen.findByRole("button",{name:"查看 首页附件.csv"});
 expect(new URLSearchParams(router.state.location.search).get("attachment_page")).toBeNull();
 expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("甲");
});

it("样本读取失败可原位重试相同范围、搜索和页码",async()=>{
 const list=vi.spyOn(samplesApi,"listSamples").mockRejectedValueOnce(new Error("暂时不可用")).mockResolvedValue({samples:[],pagination:pages(3,150)});
 render(<MemoryRouter initialEntries={["/?project_id=p&asset_set=甲&q=001&page=3"]}><SampleRegistry/></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:"重新读取样本"}));
 await waitFor(()=>expect(list).toHaveBeenCalledTimes(2));
 expect(list).toHaveBeenLastCalledWith(expect.objectContaining({project_id:"p",asset_set:"甲",q:"001",page:3}));
 await waitFor(()=>expect(screen.queryByText("样本加载失败")).not.toBeInTheDocument());
});

it("从项目样本进入登记后，清除登记筛选仍保留原项目页面",async()=>{
 vi.spyOn(apiClient,"get").mockResolvedValue({samples:[],unresolved:[],note:"",pagination:pages(3,150)} as any);
 const source="/management/projects/p?tab=samples&asset_set=甲&sample_q=001&sample_state=multiple&sample_page=3";
 const parsed=new URL(source,window.location.origin);const expectedReturn=parsed.pathname+parsed.search+parsed.hash;
 const view=render(<MemoryRouter initialEntries={[source]}><ProjectInputSamples projectId="p" revision={0}/></MemoryRouter>);
 const target=screen.getByRole("link",{name:"补充登记信息"}).getAttribute("href")!;
 expect(new URL(target,"http://synthetic").searchParams.get("return_to")).toBe(expectedReturn);
 view.unmount();
 vi.spyOn(samplesApi,"listSamples").mockResolvedValue({samples:[],pagination:pages(1,0)});
 render(<MemoryRouter initialEntries={[target+"&q=其他"]}><SampleRegistry/></MemoryRouter>);
 expect(screen.getByRole("link",{name:"返回项目样本"})).toHaveAttribute("href",expectedReturn);
 fireEvent.click(screen.getByRole("button",{name:"清空筛选"}));
 expect(screen.getByRole("link",{name:"返回项目样本"})).toHaveAttribute("href",expectedReturn);
});

it.each(["https://outside.example/management/projects/p","/management/projects/other?tab=samples"])("登记返回地址 %s 不改变当前项目",async source=>{
 vi.spyOn(samplesApi,"listSamples").mockResolvedValue({samples:[],pagination:pages(1,0)});
 render(<MemoryRouter initialEntries={[`/?${new URLSearchParams({project_id:"p",asset_set:"甲",return_to:source})}`]}><SampleRegistry/></MemoryRouter>);
 expect(screen.getByRole("link",{name:"返回项目样本"})).toHaveAttribute("href","/management/projects/p?tab=samples&asset_set=%E7%94%B2");
});
