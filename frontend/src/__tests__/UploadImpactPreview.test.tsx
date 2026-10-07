import { afterEach,expect,it,vi } from "vitest";
import {cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {AssetUpload} from "../features/assets/AssetUpload";
import * as projects from "../shared/api/projects";
import {ApiError,apiClient} from "../shared/api/client";
const saved={id:"new",project_id:"p",asset_type:"profile",metadata:{asset_set:"甲",validation:{status:"valid"}}} as any;
const kind={count:2,statuses:{valid:2},sample_min:1,sample_max:1};
const datasets: {datasets:projects.DatasetSummary[]}={datasets:[{name:"甲",input_count:2,kinds:{profile:kind}},{name:"乙",input_count:1,kinds:{}}]};
const old=(id:string,name:string)=>({id,original_name:name,uploaded_at:"2026-10-05T09:00:00",content_version:`version-${id}`});
function impact(items:projects.UploadImpactItem[],assets=[old("a","指标甲.csv"),old("b","指标乙.csv")]){
 return {impacts:items.map(item=>({...item,assets,expected_versions:assets.map(a=>({id:a.id,content_version:a.content_version})),pagination:{page:1,page_size:20,total:assets.length,total_pages:1}}))};
}
afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});
async function select(name="新指标.csv"){
 await screen.findByText("已登记 2 个样本指标表文件");
 fireEvent.change(screen.getByLabelText("选择新的样本指标表",{selector:"input"}),{target:{files:[new File(["sample,metric\n001,1"],name)]}});
 fireEvent.click(screen.getByRole("switch",{name:/更新当前版本/}));
 await waitFor(()=>expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled());
}
function setup(){
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue(datasets);
 const full=vi.spyOn(projects,"listProjectAssets");
 const preview=vi.spyOn(projects,"previewUploadImpact").mockImplementation(async (_id,items)=>impact(items));
 render(<AssetUpload projectId="p" initialAssetSet="甲" initialAssetType="profile" onSuccess={vi.fn()}/>);
 return {full,preview};
}
it("服务器轻量预检限定范围并把完整版本集合交给上传",async()=>{
 const upload=vi.spyOn(projects,"uploadProjectAssets").mockResolvedValue({assets:[saved]});
 const {full,preview}=setup();await select();
 expect(full).not.toHaveBeenCalled();expect(preview).toHaveBeenCalledWith("p",[{asset_set:"甲",asset_type:"profile",name:"新指标.csv",directory:false}]);
 const region=screen.getByRole("region",{name:"本次更新影响"});
 expect(within(region).getByText(/更新 2 个当前文件/)).toBeVisible();expect(within(region).getByText("指标甲.csv")).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"保存数据（1 项）"}));
 await waitFor(()=>expect(upload).toHaveBeenCalledWith("p",expect.objectContaining({assetType:"profile",assetSet:"甲",replaceExisting:true,expectedVersions:[{id:"a",content_version:"version-a"},{id:"b",content_version:"version-b"}]})));
});
it("版本冲突保留原文件且必须显式重新核对，重试沿用操作标识",async()=>{
 const upload=vi.spyOn(projects,"uploadProjectAssets").mockRejectedValueOnce(new ApiError("版本冲突",409,{error_code:"UPLOAD_IMPACT_CHANGED"})).mockResolvedValue({assets:[saved]});
 const {preview}=setup();await select("保留.csv");
 fireEvent.click(screen.getByRole("button",{name:"保存数据（1 项）"}));
 await screen.findByText("当前文件版本已变化");
 expect(screen.getByRole("button",{name:"从提交清单移除 保留.csv"})).toBeVisible();expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeDisabled();
 expect(preview).toHaveBeenCalledTimes(1);
 preview.mockImplementation(async (_id,items)=>impact(items,[old("next","最新指标.csv")]));
 fireEvent.click(screen.getByRole("button",{name:"重新核对更新范围"}));
 await screen.findByText("最新指标.csv");await waitFor(()=>expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled());
 fireEvent.click(screen.getByRole("button",{name:"保存数据（1 项）"}));await waitFor(()=>expect(upload).toHaveBeenCalledTimes(2));
 expect(upload.mock.calls[1][1].expectedVersions).toEqual([{id:"next",content_version:"version-next"}]);
 expect(upload.mock.calls[1][1].operationId).toBe(upload.mock.calls[0][1].operationId);
});
it("预检失败阻止保存，原位重试保留文件",async()=>{
 vi.spyOn(projects,"uploadProjectAssets").mockResolvedValue({assets:[]});
 const {preview}=setup();preview.mockRejectedValueOnce(new Error("暂时无法读取"));
 await screen.findByText("已登记 2 个样本指标表文件");
 fireEvent.change(screen.getByLabelText("选择新的样本指标表",{selector:"input"}),{target:{files:[new File(["sample,value\n001,1"],"保留.csv")]}});
 fireEvent.click(screen.getByRole("switch",{name:/更新当前版本/}));
 await screen.findByRole("button",{name:"重新核对更新范围"});expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeDisabled();
 fireEvent.click(screen.getByRole("button",{name:"重新核对更新范围"}));
 await waitFor(()=>expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled());expect(screen.getByRole("button",{name:"从提交清单移除 保留.csv"})).toBeVisible();
});
it("影响分页保持完整快照，后续页发现范围变化要求重新确认",async()=>{
 const {preview}=setup();const assets=Array.from({length:21},(_,i)=>old(String(i),`指标${i}.csv`));
 preview.mockImplementation(async (_id,items,options)=>{
  const result=impact(items,assets);result.impacts[0].assets=options?.page===2?[assets[20]]:assets.slice(0,20);
  result.impacts[0].pagination={page:options?.page||1,page_size:20,total:21,total_pages:2};return result;
 });
 await select();fireEvent.click(screen.getByRole("button",{name:"下一页受影响文件"}));await screen.findByText("指标20.csv");
 expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeEnabled();
 preview.mockImplementation(async (_id,items)=>impact(items,[old("changed","变动.csv")]));
 fireEvent.click(screen.getByRole("button",{name:"上一页受影响文件"}));
 await screen.findByText("当前文件版本已变化");expect(screen.getByRole("button",{name:"保存数据（1 项）"})).toBeDisabled();
});
it("重复同名克隆更新在提交前明确提示",async()=>{
 setup();await screen.findByText("已登记 2 个样本指标表文件");
 // All type sections remain mounted so pending entries survive type changes.
 fireEvent.change(screen.getByLabelText(/上传克隆序列表/,{selector:"input"}),{target:{files:[new File(["a"],"001.csv"),new File(["b"],"001.csv")]}});
 fireEvent.click(screen.getByRole("switch",{name:/更新当前版本/}));
 await screen.findByText(/同一数据集存在重复更新目标/);expect(screen.getByRole("button",{name:"保存数据（2 项）"})).toBeDisabled();
});
