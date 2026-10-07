import {formatSourceTime} from "../features/scripthub/modules/SourceSelection";
import {act,cleanup,fireEvent,render,screen,waitFor,within} from "@testing-library/react";
import {afterEach,expect,it,vi} from "vitest";
import {PepCacheCardSelector} from "../features/scripthub/modules/shared";
import {DifferentialSourceSelector} from "../features/scripthub/modules/DifferentialSourceSelector";
import {PathwaySourcePicker} from "../features/scripthub/modules/PathwaySourcePicker";
import {apiClient} from "../shared/api/client";
const context={projectId:"项目 甲",assetSetId:"批次 01",sampleNames:[],chains:[],profileFields:[],groupFields:[],pepColumns:[]};
const pep={id:"source-one",artifact_id:"artifact-one",path:"/results/one",cache_type:"vj_usage",status:"available",job_id:"任务 001",label:"V/J 计数频率",usage_type:"VJ summary",sample_count:6};
const differential={id:"source-job:deg",job_id:"source-job",status:"available",files:["DEG.csv"],metadata:{output_name:"同一比较",comparisons:[{group1:"02",group2:"01"}],sample_count:6,logfc_cutoff:0,pvalue_threshold:0.05}};
const pathway={id:"go-one:0",job_id:"go-one",status:"available",reason:"",comparison:{group1:"甲",group2:"乙"}};
const reply=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json"}});
afterEach(()=>{cleanup();apiClient.invalidateCache();vi.restoreAllMocks();vi.unstubAllGlobals();});

it("前置读取失败不会当成空结果，重试保留已选产物并显示来源入口",async()=>{
 const callback=vi.fn(),fetcher=vi.fn().mockResolvedValueOnce(reply({message:"暂时无法访问"},403)).mockResolvedValueOnce(reply({candidates:[pep]}));
 vi.stubGlobal("fetch",fetcher);
 render(<PepCacheCardSelector sourceContext={context} cacheType="umapin" value="artifact-one" onSelect={callback}/>);
 expect(await screen.findByRole("alert")).toHaveTextContent("前置结果读取失败");
 expect(screen.queryByRole("link",{name:"前往运行克隆共享分析"})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"重新读取前置结果"}));
 expect(await screen.findByLabelText("选择前置分析结果")).toHaveValue("source-one");
 expect(callback).not.toHaveBeenCalled();
 expect(screen.getByText("V/J 特征汇总",{exact:true})).toBeInTheDocument();
 expect(screen.queryByText("VJ summary",{exact:true})).not.toBeInTheDocument();
 const link=screen.getByRole("link",{name:"查看来源任务 任务 001"});
 const query=new URL(link.getAttribute("href")!,window.location.origin).searchParams;
 expect(query.get("job")).toBe("任务 001");expect(query.get("project")).toBe("项目 甲");expect(query.get("asset_set")).toBe("批次 01");expect(link).toHaveAttribute("target","_blank");
});

it("刷新前置来源不替换旧引用，来源消失时明确提示而不自动选其他结果",async()=>{
 const callback=vi.fn();
 vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(reply({candidates:[pep]})).mockResolvedValueOnce(reply({candidates:[{...pep,id:"other",artifact_id:"other",job_id:"other-job"}]})));
 render(<PepCacheCardSelector sourceContext={context} cacheType="umapin" value="artifact-one" onSelect={callback}/>);
 await screen.findByLabelText("选择前置分析结果");
 fireEvent.click(screen.getByRole("button",{name:"刷新前置结果"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("所选前置结果未在当前来源中找到");
 expect(screen.getByLabelText("选择前置分析结果")).toHaveValue("");
 expect(callback).not.toHaveBeenCalled();
});

it("切换范围后独立发起请求，迟到来源不自动关联到新数据集",async()=>{
 let old!:(response:Response)=>void;
 const callback=vi.fn(),fetcher=vi.fn().mockImplementationOnce(()=>new Promise<Response>(resolve=>{old=resolve;}))
 .mockResolvedValueOnce(reply({candidates:[{...pep,id:"new",artifact_id:"new"}]}));
 vi.stubGlobal("fetch",fetcher);
 const view=render(<PepCacheCardSelector sourceContext={context} cacheType="umapin" onSelect={callback}/>);
 view.rerender(<PepCacheCardSelector sourceContext={{...context,assetSetId:"批次 02"}} cacheType="umapin" onSelect={callback}/>);
 await waitFor(()=>expect(callback).toHaveBeenCalledWith(expect.objectContaining({artifact_id:"new"})));
 await act(async()=>old(reply({candidates:[pep]})));
 expect(callback).toHaveBeenCalledTimes(1);expect(screen.queryByRole("option",{name:/source-one/})).not.toBeInTheDocument();
 expect(fetcher.mock.calls[1][0]).toContain("asset_set=%E6%89%B9%E6%AC%A1+02");
});

it("缺少项目时停止旧的读取提示并禁用刷新",async()=>{
 let old!:(response:Response)=>void;
 vi.stubGlobal("fetch",vi.fn(()=>new Promise<Response>(resolve=>{old=resolve;})));
 const view=render(<PepCacheCardSelector sourceContext={context} cacheType="umapin" onSelect={vi.fn()}/>);
 view.rerender(<PepCacheCardSelector cacheType="umapin" onSelect={vi.fn()}/>);
 await screen.findByText("请选择项目数据集以读取前置分析结果。");
 expect(screen.queryByRole("status")).not.toBeInTheDocument();
 expect(screen.getByRole("button",{name:"刷新前置结果"})).toBeDisabled();
 await act(async()=>old(reply({candidates:[pep]})));
 expect(screen.queryByLabelText("选择前置分析结果")).not.toBeInTheDocument();
});

it("差异来源同名比较以任务区分，刷新失效来源不修改统计条件或引用",async()=>{
 const callback=vi.fn(),fetcher=vi.fn().mockResolvedValueOnce(reply({candidates:[differential,{...differential,id:"second:deg",job_id:"second"}]}))
 .mockResolvedValueOnce(reply({candidates:[{...differential,status:"unavailable",reason:"来源输入已改变"}]}));
 vi.stubGlobal("fetch",fetcher);
 render(<DifferentialSourceSelector sourceContext={context} value={differential.id} onSelect={callback}/>);
 await screen.findByText(/比较方向：02 \/ 01/);
 expect(screen.getByRole("option",{name:/source-job/})).toBeEnabled();expect(screen.getByRole("option",{name:/second/})).toBeEnabled();
 expect(screen.getByText(/对数倍数变化阈值：0/)).toBeInTheDocument();
 expect(screen.getByRole("link",{name:"查看来源任务 source-job"})).toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"刷新差异来源"}));
 await screen.findByText("来源输入已改变",{exact:true});
 expect(screen.getByRole("option",{name:/source-job/})).toBeDisabled();
 expect(screen.getByRole("alert")).toHaveTextContent("所选来源当前不可用");
 expect(callback).not.toHaveBeenCalled();
});

it("差异查询失败可以重试，没有来源时提供真实上游工具入口",async()=>{
 const callback=vi.fn();
 vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(reply({message:"来源读取中断"},403)).mockResolvedValueOnce(reply({candidates:[]})));
 render(<DifferentialSourceSelector sourceContext={context} value="" onSelect={callback}/>);
 expect(await screen.findByRole("alert")).toHaveTextContent("差异结果读取失败");
 expect(screen.queryByRole("link",{name:/前往差异表达/})).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole("button",{name:"重新读取差异来源"}));
 const link=await screen.findByRole("link",{name:/前往差异表达/});
 expect(new URL(link.getAttribute("href")!,window.location.origin).pathname).toBe("/analysis/tools/expression");
 expect(callback).not.toHaveBeenCalled();
});

it("通路同组对候选以任务区分，缺少或相同方向的候选禁用",async()=>{
 const callback=vi.fn();
 vi.stubGlobal("fetch",vi.fn().mockImplementation(()=>Promise.resolve(reply({candidates:[pathway,{...pathway,id:"go-two:0",job_id:"go-two"},
 {...pathway,id:"missing",job_id:"missing",comparison:undefined},{...pathway,id:"same",job_id:"same",comparison:{group1:"甲",group2:"甲"}}]}))));
 render(<PathwaySourcePicker projectId="p" assetSet="Set1" value="missing" disabled={false} onChange={callback}/>);
 const first=await screen.findByRole("radio",{name:"甲 相对于 乙 · go-one"}),second=screen.getByRole("radio",{name:"甲 相对于 乙 · go-two"});
 expect(first).toBeEnabled();expect(second).toBeEnabled();
 expect(screen.getByRole("radio",{name:"来源方向缺失 · missing"})).toBeDisabled();
 expect(screen.getByRole("radio",{name:"甲 相对于 甲 · same"})).toBeDisabled();
 expect(screen.getByRole("alert")).toHaveTextContent("所选来源当前不可用");
 fireEvent.click(second);expect(callback).toHaveBeenCalledWith("go-two:0",["甲","乙"]);
 expect(screen.getByRole("link",{name:"查看来源任务 go-two"})).toHaveAttribute("target","_blank");
});

it("通路刷新保留方向且使范围确认失效，失败后的重试不清空保存方向",async()=>{
 const callback=vi.fn(),fetcher=vi.fn().mockResolvedValueOnce(reply({candidates:[pathway]}))
 .mockResolvedValueOnce(reply({message:"通路读取失败"},403)).mockResolvedValueOnce(reply({candidates:[pathway]}));
 vi.stubGlobal("fetch",fetcher);
 render(<PathwaySourcePicker projectId="p" assetSet="Set1" value={pathway.id} disabled={false} onChange={callback}/>);
 await screen.findByRole("radio",{name:"甲 相对于 乙 · go-one"});
 fireEvent.click(screen.getByRole("button",{name:"刷新来源"}));
 expect(callback).toHaveBeenCalledWith(pathway.id,["甲","乙"]);
 expect(await screen.findByRole("alert")).toHaveTextContent("通路来源读取失败");
 callback.mockClear();fireEvent.click(screen.getByRole("button",{name:"重新读取通路来源"}));
 expect(await screen.findByRole("radio",{name:"甲 相对于 乙 · go-one"})).toBeChecked();
 expect(callback).not.toHaveBeenCalled();
});

it("通路项目切换后的迟到结果不覆盖新范围，两处选择器不共享单选组",async()=>{
 let old!:(response:Response)=>void;
 vi.stubGlobal("fetch",vi.fn().mockImplementationOnce(()=>new Promise<Response>(resolve=>{old=resolve;})).mockImplementation(()=>Promise.resolve(reply({candidates:[{...pathway,id:"new:0",job_id:"new"}]}))));
 const view=render(<PathwaySourcePicker projectId="old" assetSet="Set1" value="" disabled={false} onChange={vi.fn()}/>);
 view.rerender(<PathwaySourcePicker projectId="new" assetSet="Set2" value="" disabled={false} onChange={vi.fn()}/>);
 await screen.findByRole("radio",{name:"甲 相对于 乙 · new"});
 await act(async()=>old(reply({candidates:[pathway]})));
 expect(screen.queryByRole("radio",{name:"甲 相对于 乙 · go-one"})).not.toBeInTheDocument();
 const second=render(<PathwaySourcePicker projectId="new" assetSet="Set2" value="" disabled={false} onChange={vi.fn()}/>);
 await waitFor(()=>expect(screen.getAllByRole("radio",{name:"甲 相对于 乙 · new"})).toHaveLength(2));
 const radios=screen.getAllByRole("radio",{name:"甲 相对于 乙 · new"});
 expect(radios[0].getAttribute("name")).not.toBe(radios[1].getAttribute("name"));
 expect(within(second.container).getByRole("radio")).toBeEnabled();
});

it("来源时间按旧 UTC 记录解析，保留显式时区和未知原文",()=>{
 const display=vi.spyOn(Date.prototype,"toLocaleString").mockImplementation(function(this:Date){return this.toISOString();});
 expect(formatSourceTime("2026-10-03T02:30:03.123456")).toBe("2026-10-03T02:30:03.123Z");
 expect(formatSourceTime("2026-10-03T10:30:03.123+08:00")).toBe("2026-10-03T02:30:03.123Z");
 expect(formatSourceTime("2026-10-03 02:30:03")).toBe("2026-10-03T02:30:03.000Z");
 expect(display).toHaveBeenCalledWith("zh-CN",{hour12:false,timeZoneName:"short"});
 expect(formatSourceTime()).toBe("未记录时间");
 expect(formatSourceTime("历史时间未保存")).toBe("历史时间未保存");
});
