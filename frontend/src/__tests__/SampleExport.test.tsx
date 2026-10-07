import {afterEach, expect, it, vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {SampleExportSheet} from "../features/samples/SampleExportSheet";
import * as api from "../shared/api/samples";
const scope={projectName:"甲项目",count:120,filters:{project_id:"p",asset_set:"甲",q:"001",illness:"病种甲"}};
afterEach(()=>{cleanup();vi.restoreAllMocks();vi.unstubAllGlobals();});
function urls(){vi.stubGlobal("URL",Object.assign(URL,{createObjectURL:vi.fn(()=>"blob:synthetic"),revokeObjectURL:vi.fn()}));vi.spyOn(HTMLAnchorElement.prototype,"click").mockImplementation(()=>{});}
it("明确全部匹配页范围，阻止重复请求，失败后保留格式并可重试",async()=>{
 urls();let reject!:(reason:Error)=>void;
 const download=vi.spyOn(api,"downloadSamples").mockImplementationOnce(()=>new Promise((_resolve,no)=>{reject=no;})).mockResolvedValue({blob:new Blob(["ok"]),count:"120"});
 render(<SampleExportSheet scope={scope} onClose={()=>{}}/>);
 expect(screen.getByRole("region",{name:"本次导出范围"})).toHaveTextContent("120 条登记");
 fireEvent.click(screen.getByRole("checkbox",{name:/附带来源/}));
 fireEvent.click(screen.getByRole("button",{name:"生成并下载"}));
 expect(screen.getByRole("button",{name:"正在准备…"})).toBeDisabled();
 expect(download).toHaveBeenCalledTimes(1);reject(new Error("临时导出失败"));
 expect(await screen.findByRole("alert")).toHaveTextContent("范围与格式已保留");
 fireEvent.click(screen.getByRole("button",{name:"重新导出"}));
 await screen.findByRole("button",{name:"再次下载文件"});
 expect(download).toHaveBeenLastCalledWith(scope.filters,"xlsx",true,expect.any(AbortSignal));
 fireEvent.click(screen.getByRole("button",{name:"再次下载文件"}));expect(download).toHaveBeenCalledTimes(2);
});
it("关闭窗口终止等待，迟到结果不触发下载",async()=>{
 urls();let resolve!:(value:{blob:Blob;count:null})=>void;
 const download=vi.spyOn(api,"downloadSamples").mockImplementation(()=>new Promise(yes=>{resolve=yes;}));
 const view=render(<SampleExportSheet scope={scope} onClose={()=>{}}/>);
 fireEvent.click(screen.getByRole("button",{name:"生成并下载"}));const signal=download.mock.calls[0][3]!;
 view.unmount();expect(signal.aborted).toBe(true);resolve({blob:new Blob(),count:null});
 await waitFor(()=>expect(URL.createObjectURL).not.toHaveBeenCalled());
});
it("下载使用完整筛选和凭据，拒绝登录页面伪装文件",async()=>{
 const fetch=vi.fn().mockResolvedValueOnce(new Response("<html>login</html>",{headers:{"Content-Type":"text/html"}}))
 .mockResolvedValueOnce(new Response("样本编号\n001",{headers:{"Content-Type":"text/csv","X-Export-Count":"1"}}));
 vi.stubGlobal("fetch",fetch);
 await expect(api.downloadSamples({...scope.filters,page:9,page_size:50},"csv",false)).rejects.toThrow("未收到数据文件");
 const url=new URL(fetch.mock.calls[0][0]);expect(url.searchParams.get("asset_set")).toBe("甲");expect(url.searchParams.has("page")).toBe(false);
 expect(fetch.mock.calls[0][1].credentials).toBe("include");
 expect((await api.downloadSamples(scope.filters,"csv",false)).count).toBe("1");
});
