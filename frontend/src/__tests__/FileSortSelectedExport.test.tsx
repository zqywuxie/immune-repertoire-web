import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {RouterProvider,createMemoryRouter} from "react-router-dom";
import {ProjectDatasetManager} from "../features/assets/ProjectDatasetManager";
import {SampleRegistry} from "../pages/management/SampleRegistry";
import {InputFileFilters} from "../features/assets/InputFileFilters";
import * as projects from "../shared/api/projects";
import * as samples from "../shared/api/samples";
import {apiClient} from "../shared/api/client";

afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
it("文件排序发起服务器全范围查询并重置页码，刷新地址保留数据集和条件",async()=>{
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{name:"甲",input_count:100,kinds:{}}]});
  const list=vi.spyOn(projects,"listProjectAssets").mockImplementation(async(_id,options)=>({assets:[],pagination:{page:options?.page||1,page_size:50,total:100,total_pages:2}}));
  const router=createMemoryRouter([{path:"*",element:<ProjectDatasetManager projectId="p" revision={0} onChange={()=>{}}/>}],{initialEntries:["/management/projects/p?tab=assets&asset_set=甲&file_q=说明&history=1&file_page=2"]});
  render(<RouterProvider router={router}/>);
  await waitFor(()=>expect(list).toHaveBeenCalledWith("p",expect.objectContaining({page:2,sort:"uploaded_desc",search:"说明"})));
  fireEvent.click(screen.getByRole("button",{name:"文件排序"}));
  fireEvent.click(screen.getByRole("option",{name:"名称：升序"}));
  await waitFor(()=>expect(list).toHaveBeenLastCalledWith("p",expect.objectContaining({page:1,sort:"name_asc",assetSet:"甲",search:"说明",includeSuperseded:true})));
  const query=new URLSearchParams(router.state.location.search);
  expect(query.get("file_sort")).toBe("name_asc");expect(query.get("file_page")).toBeNull();expect(query.get("asset_set")).toBe("甲");
});
it("手机排序只在应用后生效，关闭丢弃待应用修改",()=>{
  const apply=vi.fn();
  render(<InputFileFilters mobile type="" status="" history={false} sort="uploaded_desc" search="" searchDraft="" types={[]} onSearchChange={()=>{}} onSearchSubmit={()=>{}} onApply={apply} onClear={()=>{}}/>);
  fireEvent.click(screen.getByRole("button",{name:"文件筛选（0）"}));
  fireEvent.click(screen.getByRole("button",{name:"文件排序"}));fireEvent.click(screen.getByRole("option",{name:"大小：从大到小"}));
  fireEvent.keyDown(document,{key:"Escape"});expect(apply).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"文件筛选（0）"}));expect(screen.getByRole("button",{name:"文件排序"})).toHaveTextContent("上传时间：最新优先");
  fireEvent.click(screen.getByRole("button",{name:"文件排序"}));fireEvent.click(screen.getByRole("option",{name:"大小：从大到小"}));
  fireEvent.click(screen.getByRole("button",{name:"应用文件筛选"}));expect(apply).toHaveBeenCalledWith({type:"",status:"",history:false,sort:"size_desc"});
});
it("跨页所选导出使用两个精确登记ID，导出窗口明确限定勾选范围",async()=>{
  const row={id:"r1",project_id:"p",project_name:"研究项目",sample_id:"001",sample_name:"样本",extra_metadata:{asset_set:"甲"},
    sequence_id:null,spices:null,institution:null,chain_flag:null,is_healthy:null,illness:null,is_pe:null,contain_method:null,iso_tag:null,created_at:null,updated_at:null};
  vi.spyOn(samples,"listSamples").mockImplementation(async params=>({samples:[params?.page===2?{...row,id:"r2",sample_id:"055"}:row],pagination:{page:params?.page||1,page_size:50,total:60,total_pages:2}}));
  vi.spyOn(samples,"getSampleFieldOptions").mockResolvedValue({fields:{}});
  vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"研究项目"} as never);
  const download=vi.spyOn(samples,"downloadSamples").mockResolvedValue({blob:new Blob(["001,055"]),count:"2"});
  vi.stubGlobal("URL",Object.assign(URL,{createObjectURL:vi.fn(()=>"blob:synthetic"),revokeObjectURL:vi.fn()}));
  vi.spyOn(HTMLAnchorElement.prototype,"click").mockImplementation(()=>{});
  const router=createMemoryRouter([{path:"*",element:<SampleRegistry/>}],{initialEntries:["/management/samples?project_id=p&asset_set=甲"]});
  render(<RouterProvider router={router}/>);
  fireEvent.click(await screen.findByRole("checkbox",{name:"选择登记 001（甲）"}));
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));fireEvent.click(await screen.findByRole("checkbox",{name:"选择登记 055（甲）"}));
  fireEvent.click(screen.getByRole("button",{name:"导出所选"}));
  expect(screen.getByRole("region",{name:"本次导出范围"})).toHaveTextContent("2 条登记 · 仅导出勾选项，包含跨页选择");
  fireEvent.click(screen.getByRole("button",{name:"生成并下载"}));
  await waitFor(()=>expect(download).toHaveBeenCalledWith({project_id:"p",asset_set:"甲",q:""},"xlsx",false,expect.any(AbortSignal),["r1","r2"]));
});
it("所选下载使用POST传递精确ID，省略分页且空选择不能发起全量请求",async()=>{
  const fetch=vi.fn().mockResolvedValue(new Response("样本编号\n001",{headers:{"Content-Type":"text/csv","X-Export-Count":"1"}}));
  vi.stubGlobal("fetch",fetch);
  await expect(samples.downloadSamples({project_id:"p"},"csv",false,undefined,[])).rejects.toThrow("请选择");expect(fetch).not.toHaveBeenCalled();
  await samples.downloadSamples({project_id:"p",asset_set:"甲",page:2,page_size:50},"csv",false,undefined,["r1"]);
  expect(fetch.mock.calls[0][1]).toMatchObject({method:"POST",credentials:"include"});
  expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({filters:{project_id:"p",asset_set:"甲"},record_ids:["r1"],format:"csv",columns:"business"});
});
