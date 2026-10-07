import { useLayoutEffect, useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useSearchParams } from "react-router-dom";
import { AssetTable } from "../features/assets/AssetTable";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { ProjectDatasetManager } from "../features/assets/ProjectDatasetManager";
import { useAssetSelection } from "../features/assets/useAssetSelection";
import { apiClient } from "../shared/api/client";
import * as projects from "../shared/api/projects";
import type { ProjectAsset } from "../shared/types/domain";
const asset=(id:string)=>({id,project_id:"p",asset_type:"profile",original_name:id+".csv",storage_path:"/synthetic/"+id+".csv",size:10,
  metadata:{asset_set:"甲",content_version:"v-"+id,validation:{status:"valid"},upload_manifest:"x".repeat(100000)}} as ProjectAsset);
beforeEach(()=>{vi.spyOn(apiClient,"get").mockResolvedValue({});});
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();apiClient.invalidateCache();});
function Harness({many=false}:{many?:boolean}){
 const [page,setPage]=useState(1),[scope,setScope]=useState("甲");const selection=useAssetSelection(scope);
 const assets=many?(page===1?Array.from({length:200},(_,i)=>asset("a"+i)):[asset("last")]):page===1?[asset("a"),asset("a2")]:[asset("b"),asset("b2")];
 return <><button onClick={()=>setPage(page===1?2:1)}>翻页</button><button onClick={()=>setScope(scope==="甲"?"乙":"甲")}>切换范围</button>
  <AssetTable key={scope} projectId="p" selection={selection} assets={assets} loading={false}/><output aria-label="选择身份">{JSON.stringify(selection.items)}</output></>;
}
it("跨页选择保留，所选清单包含页外文件且可单独移除",async()=>{
 render(<Harness/>);fireEvent.click(screen.getByRole("checkbox",{name:"选择 a.csv"}));fireEvent.click(screen.getByRole("button",{name:"翻页"}));
 fireEvent.click(screen.getByRole("checkbox",{name:"选择 b.csv"}));expect(screen.getByText("已选择 2 个文件")).toBeVisible();expect(screen.getByText("1 个在其他页面")).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"查看所选清单"}));const dialog=screen.getByRole("dialog",{name:"已选择 2 个文件"});
 expect(within(dialog).getByText("a.csv")).toBeVisible();expect(within(dialog).getByText("b.csv")).toBeVisible();
 fireEvent.click(within(dialog).getByRole("button",{name:"从选择清单移除 a.csv"}));expect(screen.getByRole("checkbox",{name:"选择 b.csv"})).toBeChecked();
 expect(JSON.parse(screen.getByLabelText("选择身份").textContent!).map((item:ProjectAsset)=>item.id)).toEqual(["b"]);
});
it("表头全选和取消只作用于当前页，切换范围清空原选择",()=>{
 render(<Harness/>);fireEvent.click(screen.getByRole("checkbox",{name:"选择当前列表全部文件"}));fireEvent.click(screen.getByRole("button",{name:"翻页"}));
 fireEvent.click(screen.getByRole("checkbox",{name:"选择当前列表全部文件"}));expect(screen.getByText("已选择 4 个文件")).toBeVisible();
 fireEvent.click(screen.getByRole("checkbox",{name:"选择当前列表全部文件"}));expect(screen.getByText("已选择 2 个文件")).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"切换范围"}));expect(screen.queryByRole("button",{name:"查看所选清单"})).not.toBeInTheDocument();
 expect(screen.getByLabelText("选择身份")).toHaveTextContent("[]");
});
it("跨页下载只发送明确选择的资产ID",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:true,blob:async()=>new Blob(["synthetic zip"])}));
 Object.defineProperty(URL,"createObjectURL",{configurable:true,value:vi.fn().mockReturnValue("blob:synthetic")});Object.defineProperty(URL,"revokeObjectURL",{configurable:true,value:vi.fn()});
 vi.spyOn(HTMLAnchorElement.prototype,"click").mockImplementation(()=>{});
 render(<Harness/>);fireEvent.click(screen.getByRole("checkbox",{name:"选择 a.csv"}));fireEvent.click(screen.getByRole("button",{name:"翻页"}));fireEvent.click(screen.getByRole("checkbox",{name:"选择 b.csv"}));
 fireEvent.click(screen.getByRole("button",{name:"打包下载"}));await waitFor(()=>expect(fetch).toHaveBeenCalled());
 expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)).toEqual({asset_ids:["a","b"]});
});
it("跨页删除展示完整确认，移除成功项，失败项保留并支持重试",async()=>{
 const fetcher=vi.fn().mockImplementation(async (url:string)=>url.endsWith("/a")?{ok:true,json:async()=>({success:true})}:{ok:false,json:async()=>({message:"任务引用保护"})});vi.stubGlobal("fetch",fetcher);
 render(<Harness/>);fireEvent.click(screen.getByRole("checkbox",{name:"选择 a.csv"}));fireEvent.click(screen.getByRole("button",{name:"翻页"}));fireEvent.click(screen.getByRole("checkbox",{name:"选择 b.csv"}));
 fireEvent.click(screen.getByRole("button",{name:"删除所选"}));const dialog=screen.getByRole("dialog",{name:"确认删除 2 个文件"});
 expect(within(dialog).getByText("a.csv")).toBeVisible();expect(within(dialog).getByText("b.csv")).toBeVisible();
 fireEvent.click(within(dialog).getByRole("button",{name:/确认删除/}));await screen.findByText(/已删除 1 个文件，1 个未删除/);
 expect(screen.getByRole("dialog",{name:"确认删除 1 个文件"})).toBeVisible();expect(screen.getByRole("checkbox",{name:"选择 b.csv"})).toBeChecked();
 expect(JSON.parse(screen.getByLabelText("选择身份").textContent!).map((item:ProjectAsset)=>item.id)).toEqual(["b"]);
 fetcher.mockResolvedValue({ok:true,json:async()=>({success:true})});fireEvent.click(screen.getByRole("button",{name:"重试未删除项"}));await waitFor(()=>expect(screen.queryByRole("dialog",{name:/确认删除/})).not.toBeInTheDocument());
 expect(screen.getByLabelText("选择身份")).toHaveTextContent("[]");
});
it("选择上限200，页外未选项禁用，可移除后再选且只保留轻量确认事实",()=>{
 render(<Harness many/>);fireEvent.click(screen.getByRole("checkbox",{name:"选择当前列表全部文件"}));
 expect(screen.getByText("已选择 200 个文件")).toBeVisible();const identities=JSON.parse(screen.getByLabelText("选择身份").textContent!);
 expect(identities).toHaveLength(200);expect(identities[0].metadata).not.toHaveProperty("upload_manifest");
 fireEvent.click(screen.getByRole("button",{name:"翻页"}));expect(screen.getByRole("checkbox",{name:"选择 last.csv"})).toBeDisabled();
 fireEvent.click(screen.getByRole("button",{name:"查看所选清单"}));fireEvent.click(screen.getByRole("button",{name:"从选择清单移除 a0.csv"}));fireEvent.click(screen.getByRole("button",{name:"返回文件列表"}));
 expect(screen.getByRole("checkbox",{name:"选择 last.csv"})).toBeEnabled();fireEvent.click(screen.getByRole("checkbox",{name:"选择 last.csv"}));expect(screen.getByText("已选择 200 个文件")).toBeVisible();
});
it("实际文件管理分页保留选择，改变服务器筛选后清空",async()=>{
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{name:"甲",input_count:2,kinds:{profile:{count:2,statuses:{valid:2},sample_min:1,sample_max:1}}}]});
 vi.spyOn(projects,"listProjectAssets").mockImplementation(async (_id,options={})=>({assets:[asset(options.page===2?"b":"a")],pagination:{page:options.page || 1,page_size:50,total:51,total_pages:2}}));
 render(<MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);
 fireEvent.click(await screen.findByRole("checkbox",{name:"选择 a.csv"}));fireEvent.click(screen.getByRole("button",{name:"下一页"}));
 fireEvent.click(await screen.findByRole("checkbox",{name:"选择 b.csv"}));expect(screen.getByText("已选择 2 个文件")).toBeVisible();
 fireEvent.change(screen.getByRole("textbox",{name:"搜索输入文件"}),{target:{value:"a"}});
 await waitFor(()=>expect(projects.listProjectAssets).toHaveBeenCalledWith("p",expect.objectContaining({search:"a",page:1})));
 expect(screen.queryByRole("button",{name:"查看所选清单"})).not.toBeInTheDocument();
});

it("输入及附件翻页提交新地址的首帧不提供旧页可选行",async()=>{
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"合成项目",asset_counts:{}} as never);
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{name:"甲",input_count:51,kinds:{profile:{count:51,statuses:{valid:51},sample_min:1,sample_max:1}}}]});
 vi.spyOn(projects,"listProjectAssets").mockImplementation(async (_id,options={})=>({assets:[{...asset(options.page===2?"b":"a"),asset_type:options.assetType || "profile"}],pagination:{page:options.page || 1,page_size:50,total:51,total_pages:2}}));
 for(const tab of ["assets","attachments"]){
  const observations:boolean[]=[];
  function Observe(){const [query]=useSearchParams();useLayoutEffect(()=>{if(query.get(tab==="assets"?"file_page":"attachment_page")==="2")observations.push(!!document.querySelector('input[aria-label="选择 a.csv"]'));},[query.toString()]);return null;}
  const router=createMemoryRouter([{path:"/management/projects/:projectId",element:<><ProjectDetail/><Observe/></>}],{initialEntries:["/management/projects/p?tab="+tab+"&asset_set=甲"]});
  render(<RouterProvider router={router}/>);await screen.findByRole("checkbox",{name:"选择 a.csv"});
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));await screen.findByRole("checkbox",{name:"选择 b.csv"});
  expect(observations.length).toBeGreaterThan(0);expect(observations.every(oldPageSelectable=>!oldPageSelectable)).toBe(true);cleanup();
 }
});
