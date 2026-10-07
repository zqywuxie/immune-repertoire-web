import {act,cleanup,fireEvent,render,screen,within} from "@testing-library/react";
import {afterEach,beforeEach,expect,it,vi} from "vitest";
import {MemoryRouter,useLocation} from "react-router-dom";
import {ProjectDatasetManager} from "../features/assets/ProjectDatasetManager";
import {AssetUpload} from "../features/assets/AssetUpload";
import {AssetTable} from "../features/assets/AssetTable";
import {InputValidationStatus} from "../features/assets/InputValidationStatus";
import * as projects from "../shared/api/projects";
import {apiClient} from "../shared/api/client";

const kind=(statuses:Record<string,number>)=>({count:Object.values(statuses).reduce((a,b)=>a+b,0),statuses,sample_min:1,sample_max:2});
const summary=(statuses:Record<string,number>={valid:1,invalid:1})=>({datasets:[{name:"甲",input_count:2,kinds:{profile:kind(statuses)}},{name:"乙",input_count:1,kinds:{profile:kind({valid:1})}}]});
function Address(){return <output aria-label="地址">{useLocation().search}</output>;}
async function flush(){await act(async()=>{await Promise.resolve();await Promise.resolve();});}
beforeEach(()=>{
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue(summary());
 vi.spyOn(projects,"listProjectAssets").mockImplementation(async(_id,options)=>({assets:[],pagination:{page:options?.page||1,page_size:50,total:120,total_pages:3}}));
 vi.spyOn(apiClient,"get").mockResolvedValue({columns:[],rows:[],items:[],pagination:{page:1,total_pages:1,total:0}} as never);
 Object.defineProperty(HTMLElement.prototype,"scrollIntoView",{configurable:true,value:vi.fn()});
});
afterEach(()=>{cleanup();vi.useRealTimers();vi.restoreAllMocks();apiClient.invalidateCache();});
it("概况查看清除旧组合筛选，并保留项目数据集",async()=>{
 render(<MemoryRouter initialEntries={["/?tab=assets&asset_set=甲&file_q=旧搜索&history=1&file_status=failed&file_page=3"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/><Address/></MemoryRouter>);
 await flush();
 const card=screen.getByRole("heading",{name:"样本指标表"}).closest("article")!;
 fireEvent.click(within(card).getByRole("button",{name:"查看文件"}));await flush();
 const params=new URLSearchParams(screen.getByLabelText("地址").textContent!);
 expect(params.get("asset_set")).toBe("甲");expect(params.get("tab")).toBe("assets");expect(params.get("file_type")).toBe("profile");
 for(const key of ["file_q","file_status","history","file_page"])expect(params.has(key)).toBe(false);
 expect(screen.getByRole("textbox",{name:"搜索输入文件"})).toHaveValue("");
 expect(document.activeElement).toBe(screen.getByLabelText("输入文件筛选"));
 expect(projects.listProjectAssets).toHaveBeenLastCalledWith("p",expect.objectContaining({assetSet:"甲",assetType:"profile",search:"",validationStatus:"",includeSuperseded:false,page:1}));
});
it("处理入口清理旧名称和历史条件，只查看当前需要处理文件",async()=>{
 render(<MemoryRouter initialEntries={["/?asset_set=甲&file_q=旧&history=1&file_status=valid&file_page=3"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/><Address/></MemoryRouter>);
 await flush();fireEvent.click(screen.getByRole("button",{name:"处理 1 项"}));await flush();
 const params=new URLSearchParams(screen.getByLabelText("地址").textContent!);
 expect(params.get("file_status")).toBe("needs_attention");expect(params.get("file_type")).toBe("profile");
 for(const key of ["file_q","history","file_page"])expect(params.has(key)).toBe(false);
});
it("校验等待只刷新轻量摘要，终态后更新文件并停止轮询",async()=>{
 vi.useFakeTimers();vi.mocked(projects.listProjectDatasets).mockResolvedValue(summary({pending:1,valid:1}));
 render(<MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);await flush();
 expect(projects.listProjectAssets).toHaveBeenCalledTimes(1);
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});expect(projects.listProjectDatasets).toHaveBeenCalledTimes(2);
 expect(projects.listProjectAssets).toHaveBeenCalledTimes(1);
 vi.mocked(projects.listProjectDatasets).mockResolvedValue(summary({valid:2}));
 await act(async()=>{await vi.advanceTimersByTimeAsync(5000);});
 expect(projects.listProjectAssets).toHaveBeenCalledTimes(2);expect(screen.getByText("2 个通过")).toBeVisible();
 await act(async()=>{await vi.advanceTimersByTimeAsync(20000);});expect(projects.listProjectDatasets).toHaveBeenCalledTimes(3);
});
it("隐藏标签保留页面但暂停读取，重新显示读取最新状态",async()=>{
 vi.useFakeTimers();vi.mocked(projects.listProjectDatasets).mockResolvedValue(summary({pending:1,valid:1}));
 const view=(active:boolean)=><MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectDatasetManager projectId="p" revision={0} active={active} onChange={vi.fn()}/></MemoryRouter>;
 const rendered=render(view(true));await flush();rendered.rerender(view(false));await flush();
 const reads=vi.mocked(projects.listProjectDatasets).mock.calls.length,files=vi.mocked(projects.listProjectAssets).mock.calls.length;
 await act(async()=>{await vi.advanceTimersByTimeAsync(20000);});expect(projects.listProjectDatasets).toHaveBeenCalledTimes(reads);expect(projects.listProjectAssets).toHaveBeenCalledTimes(files);
 vi.mocked(projects.listProjectDatasets).mockResolvedValue(summary({valid:2}));rendered.rerender(view(true));await flush();
 expect(projects.listProjectDatasets).toHaveBeenLastCalledWith("p",{skipCache:true});expect(screen.getByText("2 个通过")).toBeVisible();
});
it("浏览器隐藏暂停轮询，返回时同步终态，不修改当前范围",async()=>{
 vi.useFakeTimers();const visibility=vi.spyOn(document,"visibilityState","get").mockReturnValue("visible");
 vi.mocked(projects.listProjectDatasets).mockResolvedValue(summary({pending:1,valid:1}));
 render(<MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/><Address/></MemoryRouter>);await flush();
 visibility.mockReturnValue("hidden");fireEvent(document,new Event("visibilitychange"));await flush();
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000);});expect(projects.listProjectDatasets).toHaveBeenCalledTimes(1);
 visibility.mockReturnValue("visible");vi.mocked(projects.listProjectDatasets).mockResolvedValue(summary({valid:2}));fireEvent(document,new Event("visibilitychange"));await flush();
 expect(screen.getByText("2 个通过")).toBeVisible();expect(new URLSearchParams(screen.getByLabelText("地址").textContent!).get("asset_set")).toBe("甲");
});
it("隐藏文件详情不继续校验读取，重新显示按原资产ID恢复",async()=>{
 vi.useFakeTimers();const asset={id:"a",project_id:"p",asset_type:"profile",original_name:"指标.csv",metadata:{asset_set:"甲",validation:{status:"pending"}}};
 const read=vi.spyOn(projects,"getProjectAsset").mockResolvedValue({asset} as never);
 const view=(active:boolean)=><MemoryRouter><AssetTable projectId="p" assets={[]} loading={false} focusedAssetId="a" active={active}/></MemoryRouter>;
 const rendered=render(view(true));await flush();expect(read).toHaveBeenCalledTimes(1);
 rendered.rerender(view(false));await flush();await act(async()=>{await vi.advanceTimersByTimeAsync(15000);});expect(read).toHaveBeenCalledTimes(1);
 rendered.rerender(view(true));await flush();expect(read).toHaveBeenCalledTimes(2);
});
it("关闭导入状态区后停止轮询，重开读取真实保存校验状态",async()=>{
 vi.useFakeTimers();vi.mocked(projects.listProjectDatasets).mockResolvedValue(summary({pending:1,valid:1}));
 const view=(active:boolean)=><InputValidationStatus projectId="p" revision={0} assetSet="甲" active={active}/>;
 const rendered=render(view(true));await flush();rendered.rerender(view(false));await flush();
 await act(async()=>{await vi.advanceTimersByTimeAsync(15000);});expect(projects.listProjectDatasets).toHaveBeenCalledTimes(1);
 rendered.rerender(view(true));await flush();expect(projects.listProjectDatasets).toHaveBeenCalledTimes(2);
});
it("目录移除按准确路径标识操作，并保留其他目录草稿",async()=>{
 render(<AssetUpload projectId="p" initialAssetType="pep" onSuccess={vi.fn()}/>);await flush();
 fireEvent.click(screen.getByText("从服务器已有目录导入"));
 const input=screen.getByPlaceholderText("/data/projects/.../pep_sample_dir/");
 fireEvent.change(input,{target:{value:"/synthetic/甲"}});fireEvent.click(screen.getByRole("button",{name:"添加"}));
 fireEvent.change(input,{target:{value:"/synthetic/乙"}});fireEvent.click(screen.getByRole("button",{name:"添加"}));
 const remove=screen.getByRole("button",{name:"移除目录 /synthetic/甲"});
 expect(remove).toHaveAttribute("type","button");fireEvent.click(remove);
 expect(screen.queryByRole("button",{name:"移除目录 /synthetic/甲"})).not.toBeInTheDocument();
 expect(screen.getByRole("button",{name:"移除目录 /synthetic/乙"})).toBeVisible();
 expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled();
});


it("关闭准备区在刷新版本时不读取前置结果，展开和重开核对真实摘要",async()=>{
 vi.mocked(apiClient.get).mockResolvedValue({success:true,summary:{total:0,available:0,unavailable:0,reasons:[]}} as never);
 const view=(revision:number)=><MemoryRouter initialEntries={["/?asset_set=甲&prepare_tool=umapin&prepare_open=0"]}><ProjectDatasetManager projectId="p" revision={revision} onChange={vi.fn()}/></MemoryRouter>;
 const rendered=render(view(0));await flush();
 const requests=()=>vi.mocked(apiClient.get).mock.calls.filter(([url])=>url==="/api/script-hub/pep-cache-candidates");
 expect(requests()).toHaveLength(0);expect(screen.getByRole("button",{name:"目标分析"})).not.toBeVisible();
 const disclosure=screen.getByText("按分析目标准备数据").closest("details")!;
 disclosure.open=true;fireEvent(disclosure,new Event("toggle"));await flush();
 expect(requests()).toHaveLength(1);expect(screen.getByRole("button",{name:"目标分析"})).toBeVisible();
 disclosure.open=false;fireEvent(disclosure,new Event("toggle"));await flush();rendered.rerender(view(1));await flush();expect(requests()).toHaveLength(1);
 const reopened=screen.getByText("按分析目标准备数据").closest("details")!;reopened.open=true;fireEvent(reopened,new Event("toggle"));await flush();expect(requests()).toHaveLength(2);
});
