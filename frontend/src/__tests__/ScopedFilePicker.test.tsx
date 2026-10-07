import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DirectoryBrowser } from "../shared/components/DirectoryBrowser";
import { listProjectAssets } from "../shared/api/projects";
vi.mock("../shared/api/projects",()=>({listProjectAssets:vi.fn()}));
const file=(id:string,name:string)=>({id,project_id:"p1",asset_type:"profile",original_name:name,storage_path:`/input/${name}`,storage_uri:`/input/${name}`,uploaded_at:"2026-10-05T09:00:00",size:23,metadata:{asset_set:"甲"}} as any);
beforeEach(()=>{vi.mocked(listProjectAssets).mockReset();});
afterEach(cleanup);
describe("按数据集搜索与分页选择文件",()=>{
 it("后续页可选择文件，搜索零结果不会恢复无关文件，清空恢复第一页",async()=>{
  vi.mocked(listProjectAssets).mockImplementation(async(_project,options={})=>({assets:options.search?[]:[file(options.page===2?"later":"first",options.page===2?"后续文件.csv":"首页文件.csv")],pagination:{page:options.page||1,page_size:50,total:options.search?0:51,total_pages:options.search?0:2}}));
  const onSelect=vi.fn();render(<DirectoryBrowser projectId="p1" assetSet="甲" inputsOnly onSelect={onSelect}/>);
  await screen.findByRole("button",{name:/首页文件.csv/});
  expect(listProjectAssets).toHaveBeenLastCalledWith("p1",expect.objectContaining({assetSet:"甲",inputsOnly:true,page:1,pageSize:50}));
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));
  fireEvent.click(await screen.findByRole("button",{name:/后续文件.csv/}));
  expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({id:"later"}));
  fireEvent.change(screen.getByRole("searchbox",{name:"搜索文件名"}),{target:{value:"不存在"}});
  await screen.findByText("没有匹配的文件。");
  expect(screen.queryByRole("button",{name:/后续文件.csv/})).not.toBeInTheDocument();
  expect(listProjectAssets).toHaveBeenLastCalledWith("p1",expect.objectContaining({search:"不存在",page:1,assetSet:"甲"}));
  fireEvent.click(screen.getByRole("button",{name:"清除搜索"}));await screen.findByRole("button",{name:/首页文件.csv/});
 });
 it("历史版本需明确打开，加载失败保留检索条件并可重试",async()=>{
  vi.mocked(listProjectAssets).mockRejectedValueOnce(new Error("读取失败")).mockResolvedValue({assets:[{...file("old","旧文件.csv"),metadata:{asset_set:"甲",superseded:true}}]});
  render(<DirectoryBrowser projectId="p1" assetSet="甲" inputsOnly/>);
  await screen.findByRole("alert");fireEvent.click(screen.getByRole("button",{name:"重新读取"}));
  await screen.findByRole("button",{name:/旧文件.csv.*历史版本/});
  fireEvent.click(screen.getByRole("checkbox",{name:"显示历史版本"}));
  await waitFor(()=>expect(listProjectAssets).toHaveBeenLastCalledWith("p1",expect.objectContaining({includeSuperseded:true,assetSet:"甲",page:1})));
 });
});
