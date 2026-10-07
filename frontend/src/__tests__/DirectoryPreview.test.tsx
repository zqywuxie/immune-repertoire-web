import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {AssetInputPreview} from "../features/assets/AssetInputPreview";
import {apiClient} from "../shared/api/client";
import type {ProjectAsset} from "../shared/types/domain";
const asset={id:"a",project_id:"p",asset_type:"pep",original_name:"目录",storage_path:"/synthetic",size:0} satisfies ProjectAsset;
const listing={directory:true,files:[{name:"one.csv",size:1},{name:"two.csv",size:1}],pagination:{page:1,page_size:20,total:22,total_pages:2},columns:[],rows:[]};
afterEach(()=>{cleanup();vi.restoreAllMocks();});
it("选择表格保留目录清单，失败重试只请求所选文件，刷新才重读目录",async()=>{
 let fileCalls=0;
 const request=vi.spyOn(apiClient,"get").mockImplementation(async(_url,params)=>{
  if(!params?.file)return listing as never;
  if(++fileCalls===1)throw new Error("合成读取失败");
  return {directory:true,files:[],columns:["编号"],rows:[["001"]]} as never;
 });
 render(<AssetInputPreview projectId="p" asset={asset}/>);
 fireEvent.click(await screen.findByRole("button",{name:"one.csv"}));await screen.findByRole("alert");
 expect(screen.getByRole("button",{name:"two.csv"})).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"重新预览所选表格"}));await screen.findByRole("cell",{name:"001"});
 expect(request.mock.calls.filter(call=>!call[1]?.file)).toHaveLength(1);
 expect(request).toHaveBeenLastCalledWith(expect.any(String),{file:"one.csv",include_files:false},{skipCache:true});
 fireEvent.click(screen.getByRole("button",{name:"刷新目录"}));await screen.findByRole("button",{name:"two.csv"});
 expect(request.mock.calls.filter(call=>!call[1]?.file)).toHaveLength(2);
});
it("换页清除旧表格，切换资产后不沿用旧目录路径",async()=>{
 const request=vi.spyOn(apiClient,"get").mockImplementation(async(_url,params)=>params?.file ? {directory:true,files:[],columns:["编号"],rows:[["001"]]} as never : {...listing,pagination:{...listing.pagination,page:Number(params?.page || 1)}} as never);
 const view=render(<AssetInputPreview projectId="p" asset={asset}/>);
 fireEvent.click(await screen.findByRole("button",{name:"one.csv"}));await screen.findByRole("cell",{name:"001"});
 fireEvent.click(screen.getByRole("button",{name:"下一页"}));await waitFor(()=>expect(request).toHaveBeenLastCalledWith(expect.any(String),{file:"",page:2,page_size:20},{skipCache:true}));
 expect(screen.queryByRole("cell",{name:"001"})).not.toBeInTheDocument();
 view.rerender(<AssetInputPreview projectId="p" asset={{...asset,id:"b"}}/>);
 await waitFor(()=>expect(request).toHaveBeenLastCalledWith("/api/projects/p/assets/b/table-preview",{file:"",page:1,page_size:20},{skipCache:true}));
});

it("目录刷新后页码越界回到末页，不把仍有文件的目录当成空目录",async()=>{
 let refreshed=false;
 const request=vi.spyOn(apiClient,"get").mockImplementation(async(_url,params)=>({
  ...listing,files:refreshed && params?.page===2?[]:listing.files,
  pagination:{page:Number(params?.page || 1),page_size:20,total:refreshed?2:22,total_pages:refreshed?1:2}}) as never);
 render(<AssetInputPreview projectId="p" asset={asset}/>);
 fireEvent.click(await screen.findByRole("button",{name:"下一页"}));
 await waitFor(()=>expect(request).toHaveBeenLastCalledWith(expect.any(String),expect.objectContaining({page:2}),expect.any(Object)));
 refreshed=true;fireEvent.click(await screen.findByRole("button",{name:"刷新目录"}));
 await waitFor(()=>expect(request).toHaveBeenLastCalledWith(expect.any(String),expect.objectContaining({page:1}),expect.any(Object)));
 await screen.findByRole("button",{name:"one.csv"});expect(screen.queryByText("目录内没有可预览表格。")).not.toBeInTheDocument();
});
