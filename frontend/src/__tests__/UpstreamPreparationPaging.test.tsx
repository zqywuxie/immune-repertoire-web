import {useState} from "react";
import {afterEach,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MemoryRouter,useLocation} from "react-router-dom";
import {UpstreamPreparation} from "../features/assets/UpstreamPreparation";
import * as api from "../shared/api/upstreamSources";
import {apiClient} from "../shared/api/client";
const source={kind:"pep" as const,cacheType:"umapin",title:"特征结果",upstreamTool:"sharing",hint:"确认范围"};
const summary={total:45,available:44,unavailable:1,reasons:[]};
afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});
function Address(){return <output aria-label="当前地址">{useLocation().search}</output>;}
function mount(entry="/?prepare_sources=1&asset_set=甲") {return render(<MemoryRouter initialEntries={[entry]}><UpstreamPreparation projectId="p" dataset="甲" source={source} revision={0} returnPath="/management/projects/p?tab=assets"/><Address/></MemoryRouter>);}
it("来源目录服务器分页和筛选保留项目范围，页外不全量呈现",async()=>{
 const list=vi.spyOn(api,"getUpstreamCatalog").mockImplementation(async(_p,_d,_s,options)=>({success:true,summary,
  pagination:{page:options.page,page_size:20,total:options.search?1:45,total_pages:options.search?1:3},
  candidates:Array.from({length:options.search?1:options.page===3?5:20},(_,i)=>({id:`${options.page}-${i}`,project_id:"p",asset_set:"甲",job_id:`任务-${options.page}-${i}`,source_task_name:options.search || `来源-${options.page}-${i}`,status:"available" as const,reason:""}))}));
 const overview=vi.spyOn(api,"getUpstreamSummary");mount();await screen.findByText("来源-1-19");expect(screen.queryByText("来源-2-0")).not.toBeInTheDocument();expect(overview).not.toHaveBeenCalled();
 fireEvent.click(screen.getByRole("button",{name:"下一页"}));await screen.findByText("来源-2-0");expect(screen.queryByText("来源-1-0")).not.toBeInTheDocument();
 expect(screen.getByLabelText("当前地址")).toHaveTextContent("prepare_page=2");
 fireEvent.change(screen.getByRole("textbox",{name:"查找前置结果"}),{target:{value:"中文来源"}});fireEvent.click(screen.getByRole("button",{name:"查询来源"}));await screen.findByText("中文来源");
 expect(list).toHaveBeenLastCalledWith("p","甲",source,{page:1,search:"中文来源",status:""});
 fireEvent.click(screen.getByRole("button",{name:"前置结果状态"}));fireEvent.click(screen.getByRole("option",{name:"不可用结果"}));
 await waitFor(()=>expect(list).toHaveBeenLastCalledWith("p","甲",source,{page:1,search:"中文来源",status:"unavailable"}));
 expect(screen.getByLabelText("当前地址")).toHaveTextContent("asset_set");
});
it("隐藏页和revision变化不请求，返回重新读取摘要",async()=>{
 const read=vi.spyOn(api,"getUpstreamSummary").mockResolvedValue({success:true,summary});
 const list=vi.spyOn(api,"getUpstreamCatalog");
 function Fixture(){const [active,setActive]=useState(false),[revision,setRevision]=useState(0);return <><button onClick={()=>setActive(!active)}>切换可见</button><button onClick={()=>setRevision(revision+1)}>修改版本</button><UpstreamPreparation projectId="p" dataset="甲" source={source} revision={revision} active={active} returnPath="/"/></>;}
 render(<MemoryRouter><Fixture/></MemoryRouter>);expect(read).not.toHaveBeenCalled();fireEvent.click(screen.getByText("修改版本"));expect(read).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText("切换可见"));await screen.findByText(/44 项前置结果可用/);expect(read).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByText("切换可见"));fireEvent.click(screen.getByText("修改版本"));expect(read).toHaveBeenCalledTimes(1);
 fireEvent.click(screen.getByText("切换可见"));await waitFor(()=>expect(read).toHaveBeenCalledTimes(2));expect(list).not.toHaveBeenCalled();
});
it("新页请求未完成不显示旧来源，失败保留查询并可重试",async()=>{
 let resolveNew!:(value:any)=>void;
 const data={success:true,summary,pagination:{page:1,page_size:20,total:45,total_pages:3},candidates:[{id:"first",project_id:"p",status:"available" as const,reason:"",source_task_name:"旧页来源"}]};
 const read=vi.spyOn(api,"getUpstreamCatalog").mockResolvedValueOnce(data).mockImplementationOnce(()=>new Promise(resolve=>{resolveNew=resolve;})).mockRejectedValueOnce(new Error("来源连接失败")).mockResolvedValueOnce({...data,candidates:[]});
 mount();await screen.findByText("旧页来源");fireEvent.click(screen.getByRole("button",{name:"下一页"}));expect(screen.queryByText("旧页来源")).not.toBeInTheDocument();
 await act(async()=>resolveNew({...data,pagination:{...data.pagination,page:2},candidates:[{...data.candidates[0],id:"new",source_task_name:"新页来源"}]}));await screen.findByText("新页来源");
 fireEvent.change(screen.getByRole("textbox",{name:"查找前置结果"}),{target:{value:"保留"}});fireEvent.click(screen.getByRole("button",{name:"查询来源"}));expect(await screen.findByRole("alert")).toHaveTextContent("来源连接失败");
 expect(screen.getByRole("textbox",{name:"查找前置结果"})).toHaveValue("保留");fireEvent.click(screen.getByRole("button",{name:"刷新前置结果"}));await screen.findByText(/没有符合筛选的前置结果/);expect(read).toHaveBeenCalledTimes(4);
});
