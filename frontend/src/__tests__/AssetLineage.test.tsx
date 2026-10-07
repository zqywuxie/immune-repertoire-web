import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {AssetLineage} from "../features/assets/AssetLineage";
import {AssetResultProvenance} from "../features/assets/AssetResultProvenance";
import {AssetTable} from "../features/assets/AssetTable";
import {apiClient} from "../shared/api/client";
import * as api from "../shared/api/assetLineage";
import type {ProjectAsset} from "../shared/types/domain";
const paging={page:1,page_size:20,total:2,total_pages:1};
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
it("展开后读取版本，当前版本标记与链接依据资产标识",async()=>{
 const get=vi.spyOn(api,"getAssetLineage").mockResolvedValue({section:"versions",items:[
  {id:"new",name:"同名.csv",asset_set:"甲",content_version:"新版本",superseded:false},
  {id:"old",name:"同名.csv",asset_set:"甲",content_version:"旧版本",superseded:true}],pagination:paging});
 render(<AssetLineage projectId="p1" assetId="old"/>);expect(get).not.toHaveBeenCalled();
 fireEvent.click(screen.getByText("版本与引用"));await screen.findByText("版本：旧版本");
 expect(get).toHaveBeenCalledWith("p1","old","versions",1);
 const link=screen.getByRole("link",{name:"查看此版本"});expect(new URL(link.getAttribute("href")!,"http://localhost").searchParams.get("asset")).toBe("new");
 expect(screen.getByText("正在查看此版本")).toBeVisible();expect(screen.getByText("历史版本")).toBeVisible();
});
it("分类切换按需读取且失败不冒充无引用，重试可恢复",async()=>{
 const get=vi.spyOn(api,"getAssetLineage").mockResolvedValueOnce({section:"versions",items:[],pagination:{...paging,total:0}})
 .mockRejectedValueOnce(new Error("读取中断")).mockResolvedValueOnce({section:"jobs",items:[{id:"old-job",name:"旧输入任务",module:"profile",status:"completed",match:"asset_id",asset_set:"甲"}],pagination:{...paging,total:1}});
 render(<AssetLineage projectId="p1" assetId="old" initialOpen/>);await screen.findByText("没有可展示的版本记录。");
 fireEvent.click(screen.getByRole("button",{name:"引用任务"}));await screen.findByRole("alert");expect(screen.queryByText("没有找到引用此文件的任务。")).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"重新读取引用任务"}));await screen.findByText("旧输入任务");
 expect(get).toHaveBeenLastCalledWith("p1","old","jobs",1);const url=new URL(screen.getByRole("link",{name:"查看任务与结果"}).getAttribute("href")!,"http://localhost");
 expect(url.searchParams.get("job")).toBe("old-job");expect(url.searchParams.get("asset_set")).toBe("甲");
});
it("任务引用分页不加载其他分类，分组链接可定位具体方案",async()=>{
 const get=vi.spyOn(api,"getAssetLineage").mockResolvedValueOnce({section:"jobs",items:[{id:"one",name:"第一页"}],pagination:{...paging,total:21,total_pages:2}})
 .mockResolvedValueOnce({section:"jobs",items:[{id:"two",name:"第二页"}],pagination:{...paging,page:2,total:21,total_pages:2}})
 .mockResolvedValueOnce({section:"groups",items:[{id:"spec one",name:"分组甲"}],pagination:{...paging,total:1}});
 render(<AssetLineage projectId="p1" assetId="old" initialOpen initialSection="jobs"/>);await screen.findByText("第一页");
 fireEvent.click(screen.getByRole("button",{name:"下一页"}));await screen.findByText("第二页");expect(get).toHaveBeenLastCalledWith("p1","old","jobs",2);
 fireEvent.click(screen.getByRole("button",{name:"引用分组方案"}));await screen.findByText("分组甲");
 expect(new URL(screen.getByRole("link",{name:"定位分组方案"}).getAttribute("href")!,"http://localhost").searchParams.get("group_spec")).toBe("spec one");
});
it("删除冲突保留文件并提供精确引用任务入口",async()=>{
 vi.spyOn(apiClient,"get").mockResolvedValue({datasets:[]});
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:false,json:async()=>({message:"文件仍被任务引用",details:{job_id:"job-old"}})}));
 const asset={id:"a1",project_id:"p1",asset_type:"profile",original_name:"旧版本.csv",storage_path:"/synthetic/old.csv",size:1,metadata:{asset_set:"甲"}} as ProjectAsset;
 render(<AssetTable projectId="p1" assets={[asset]} loading={false}/>);
 fireEvent.click(screen.getByRole("button",{name:"更多操作：旧版本.csv"}));
 fireEvent.click(screen.getByRole("button",{name:"删除 旧版本.csv"}));fireEvent.click(screen.getByRole("button",{name:"确认删除"}));
 const link=await screen.findByRole("link",{name:/查看引用任务 job-old/});expect(new URL(link.getAttribute("href")!,"http://localhost").searchParams.get("project")).toBe("p1");
 expect(screen.getByRole("button",{name:"重试未删除项"})).toBeVisible();expect(screen.getByRole("checkbox",{name:"选择 旧版本.csv"})).toBeChecked();
});

it("项目结果保留来源任务与旧输入链接，没有任务标识时不猜测",()=>{
 const asset:ProjectAsset={id:"result",storage_path:"/synthetic/result.html",size:1,project_id:"p1",asset_type:"processed_result",original_name:"分析报告",metadata:{job_id:"old-task",analysis_type:"profile",input_assets:[{asset_type:"profile",asset_id:"old-input",original_name:"旧输入.csv",asset_set:"甲"}]}} as ProjectAsset;
 render(<AssetResultProvenance asset={asset} projectId="p1"/>);
 expect(new URL(screen.getByRole("link",{name:"查看来源任务与输入"}).getAttribute("href")!,"http://localhost").searchParams.get("job")).toBe("old-task");
 fireEvent.click(screen.getByText("结果保存的输入与分组"));expect(new URL(screen.getByRole("link",{name:"查看执行时的文件"}).getAttribute("href")!,"http://localhost").searchParams.get("asset")).toBe("old-input");
 cleanup();render(<AssetResultProvenance asset={{...asset,metadata:{}}} projectId="p1"/>);expect(screen.queryByRole("link",{name:"查看来源任务与输入"})).not.toBeInTheDocument();expect(screen.getByText("此结果未保存来源任务标识。")).toBeVisible();
});

it("结果详情不把缺失的数据集来源显示为默认输入数据集",async()=>{
 const asset:ProjectAsset={id:"result-unknown",project_id:"p1",asset_type:"processed_result",original_name:"旧结果",storage_path:"/synthetic/result",size:1,metadata:{source:"mongodb"}};
 render(<AssetTable projectId="p1" assets={[asset]} loading={false} showSelect={false}/>);
 fireEvent.click(screen.getByRole("button",{name:"查看 旧结果"}));
 expect((await screen.findAllByText("未记录数据集"))[0]).toBeVisible();expect(screen.queryByText("Set1")).not.toBeInTheDocument();
});
