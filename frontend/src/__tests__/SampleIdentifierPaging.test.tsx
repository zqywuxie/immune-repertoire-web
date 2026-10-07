import {useState} from "react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {RouterProvider,createMemoryRouter} from "react-router-dom";
import {SampleIdentifierFilter} from "../features/samples/SampleIdentifierFilter";
import {SampleRegistry} from "../pages/management/SampleRegistry";
import * as api from "../shared/api/samples";
import * as projects from "../shared/api/projects";
import {apiClient} from "../shared/api/client";

beforeEach(()=>{vi.spyOn(api,"getSampleFieldCandidates").mockImplementation(async(_project,_dataset,field,q,page)=>({field,values:q?[q]:Array.from({length:page===3?6:20},(_,i)=>String((page-1)*20+i).padStart(3,"0")),pagination:{page,page_size:20,total:q?1:46,total_pages:q?1:3}}));});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
function Harness(){const[value,setValue]=useState("999");return <SampleIdentifierFilter field="sample_id" label="样本编号" value={value} projectId="p" dataset="甲" onChange={setValue}/>;}
it("关闭时不读编号，分页搜索保留页外条件并以文本选择001",async()=>{
 render(<Harness/>);expect(api.getSampleFieldCandidates).not.toHaveBeenCalled();
 fireEvent.click(screen.getByLabelText("样本编号筛选"));await screen.findByText("匹配 46 个编号 · 每页最多 20 个");expect(screen.getByText("当前条件：999")).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"第 3 页"}));await waitFor(()=>expect(api.getSampleFieldCandidates).toHaveBeenLastCalledWith("p","甲","sample_id","",3));await screen.findByRole("button",{name:"045"});
 fireEvent.change(screen.getByRole("textbox",{name:"搜索样本编号候选"}),{target:{value:"001"}});fireEvent.click(screen.getByRole("button",{name:"查询"}));
 fireEvent.click(await screen.findByRole("button",{name:"001"}));expect(screen.getByLabelText("样本编号筛选")).toHaveTextContent("001");expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
});
it("候选失败保留当前条件和查询，重试相同页且不误当空结果",async()=>{
 vi.mocked(api.getSampleFieldCandidates).mockRejectedValueOnce(new Error("暂时断开"));render(<Harness/>);fireEvent.click(screen.getByLabelText("样本编号筛选"));
 expect(await screen.findByRole("alert")).toHaveTextContent("暂时断开");expect(screen.getByText("当前条件：999")).toBeVisible();expect(screen.queryByText(/没有匹配/)).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"重新读取候选"}));await screen.findByRole("button",{name:"001"});expect(api.getSampleFieldCandidates).toHaveBeenLastCalledWith("p","甲","sample_id","",1);
});
it("手机选择编号仅改变待应用草稿，应用后保留项目数据集搜索与文本001",async()=>{
 vi.stubGlobal("matchMedia",vi.fn().mockImplementation(query=>({matches:true,media:query,addEventListener:vi.fn(),removeEventListener:vi.fn()})));
 vi.spyOn(api,"getSampleFieldOptions").mockResolvedValue({fields:{spices:["人"]}});vi.spyOn(api,"listSamples").mockResolvedValue({samples:[],pagination:{page:1,page_size:50,total:0,total_pages:0}});
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"研究项目"} as never);
 const router=createMemoryRouter([{path:"*",element:<SampleRegistry/>}],{initialEntries:["/?project_id=p&asset_set=甲&q=研究"]});render(<RouterProvider router={router}/>);
 await waitFor(()=>expect(api.getSampleFieldOptions).toHaveBeenCalledWith("p","","甲",{view:"filters"}));expect(api.getSampleFieldCandidates).not.toHaveBeenCalled();fireEvent.click(screen.getByRole("button",{name:"筛选条件（0）"}));
 const dialog=screen.getByRole("dialog",{name:"样本筛选"});fireEvent.click(within(dialog).getByLabelText("样本编号筛选"));fireEvent.click(await within(dialog).findByRole("button",{name:"001"}));expect(new URLSearchParams(router.state.location.search).get("sample_id")).toBeNull();
 fireEvent.click(within(dialog).getByRole("button",{name:"应用筛选"}));await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("sample_id")).toBe("001"));
 const query=new URLSearchParams(router.state.location.search);expect(query.get("project_id")).toBe("p");expect(query.get("asset_set")).toBe("甲");expect(query.get("q")).toBe("研究");
});
