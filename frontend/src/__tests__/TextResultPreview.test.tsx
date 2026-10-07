import {afterEach, expect, it, vi} from "vitest";
import {act, cleanup, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {TextResultPreview} from "../features/results/TextResultPreview";
import {ViewArea, textOutputKind} from "../features/results/ResultViewer";
import {JobResultPanel} from "../features/jobs/JobResultPanel";
import type {JobResultsResponse} from "../shared/api/jobs";

afterEach(()=>{cleanup();sessionStorage.clear();vi.unstubAllGlobals();});
const rangeResponse=(text:string)=>{const n=new TextEncoder().encode(text).length;return new Response(text,{status:206,headers:{"Content-Range":"bytes 0-"+(n-1)+"/"+n,"Content-Type":"text/plain"}});};

it("文本按原文显示数值、编号和标签，并可重新读取及完整下载",async()=>{
 const original='样本 001\np=1.00000000001e-9\n编号=9007199254740993\n<script>window.bad=true</script>';
 const fetcher=vi.fn().mockResolvedValueOnce(rangeResponse(original)).mockResolvedValueOnce(rangeResponse(original+"\n更新"));
 vi.stubGlobal("fetch",fetcher);render(<ViewArea kind="data" url="/结果%20说明.TXT?download=1" />);
 await waitFor(()=>expect(screen.getByLabelText("文件原文").textContent).toBe(original));
 expect(document.querySelector("script")).toBeNull();expect(screen.queryByText(/无法按 JSON/)).not.toBeInTheDocument();
 expect(fetcher.mock.calls[0][1]).toMatchObject({cache:"no-store",headers:{Range:"bytes=0-2097151"}});
 expect(screen.getByRole("link",{name:"下载完整文本"})).toHaveAttribute("href","/结果%20说明.TXT?download=1");
 fireEvent.click(screen.getByRole("button",{name:"重新读取文本"}));
 await waitFor(()=>expect(screen.getByLabelText("文件原文").textContent).toBe(original+"\n更新"));
});

it("日志默认保留末尾2000行，可切换文件开头且保持原始数值",async()=>{
 const lines=Array.from({length:2105},(_,i)=>"日志 "+String(i).padStart(4,"0")+" p=1.00000000001e-9");
 const text=lines.join("\n")+"\n",fetcher=vi.fn().mockImplementation(()=>Promise.resolve(rangeResponse(text)));
 vi.stubGlobal("fetch",fetcher);render(<ViewArea kind="data" url="/run.log" />);
 await screen.findByText(/当前显示最后 2000 行/);
 expect(screen.getByLabelText("文件原文").textContent).toBe(lines.slice(-2000).join("\n")+"\n");
 expect(fetcher.mock.calls[0][1].headers.Range).toBe("bytes=-2097152");
 fireEvent.change(screen.getByLabelText("日志预览范围"),{target:{value:"start"}});
 await screen.findByText(/当前显示最前 2000 行/);
 expect(screen.getByLabelText("文件原文").textContent).toBe(lines.slice(0,2000).join("\n")+"\n");
 expect(fetcher.mock.calls[1][1].headers.Range).toBe("bytes=0-2097151");
});

it("真实后缀字节范围跨UTF8字符时跳过残余字节，取消读取且只显示末尾",async()=>{
 const bytes=new Uint8Array(2097152);bytes.fill(120);bytes.set([0xb8,0xad,0xe6,0x96,0x87],0);
 const ending=new TextEncoder().encode("\n末尾完成 001 p=1e-9");bytes.set(ending,bytes.length-ending.length);
 const cancelled=vi.fn(),body=new ReadableStream({start(c){c.enqueue(bytes);},cancel:cancelled});
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response(body,{status:206,headers:{"Content-Range":"bytes 100-2097251/2097252"}})));
 render(<TextResultPreview url="/large.log" kind="log"/>);await screen.findByText(/仅预览末尾 2 MB/);
 const text=screen.getByLabelText("文件原文").textContent!;
 expect(text.startsWith("文")).toBe(true);expect(text.endsWith("末尾完成 001 p=1e-9")).toBe(true);
 expect(text).not.toContain("�");expect(cancelled).toHaveBeenCalledTimes(1);
});

it("不支持范围的大日志不会把开头冒充末尾，切换开头仍有界读取",async()=>{
 const text="开始 001\n"+"x".repeat(3*1024*1024)+"结束";
 vi.stubGlobal("fetch",vi.fn().mockImplementation(()=>Promise.resolve(new Response(text))));
 render(<ViewArea kind="log" url="/ignored.log"/>);
 expect(await screen.findByRole("alert")).toHaveTextContent("不支持文件末尾预览");
 expect(screen.queryByLabelText("文件原文")).not.toBeInTheDocument();
 expect(screen.getByRole("link",{name:"下载完整日志"})).toBeInTheDocument();
 fireEvent.change(screen.getByLabelText("日志预览范围"),{target:{value:"start"}});
 await screen.findByText(/仅预览前 2 MB/);
 expect(screen.getByLabelText("文件原文").textContent).toMatch(/^开始 001/);
 expect(screen.getByLabelText("文件原文").textContent).not.toContain("结束");
});

it.each([
 [404,{}, "结果文件不存在或已移除"],
 [410,{}, "结果文件不存在或已移除"],
 [403,{}, "项目权限"],
 [200,{"Content-Type":"text/html"},"返回了网页"],
])("日志错误状态%s提供明确反馈和重新读取",async(status,headers,message)=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(new Response("bad",{status,headers})).mockResolvedValueOnce(rangeResponse("恢复 001")));
 render(<TextResultPreview url="/retry.log" kind="log"/>);
 expect(await screen.findByRole("alert")).toHaveTextContent(message);
 fireEvent.click(screen.getByRole("button",{name:"重新读取日志"}));
 await waitFor(()=>expect(screen.getByLabelText("文件原文").textContent).toBe("恢复 001"));
});

it("空日志范围416与错误编码分别处理",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(new Response("",{status:416,headers:{"Content-Range":"bytes */0"}})).mockResolvedValueOnce(new Response(new Uint8Array([0xff]))));
 render(<TextResultPreview url="/empty.log" kind="log"/>);await screen.findByText("日志文件为空。");
 fireEvent.click(screen.getByRole("button",{name:"重新读取日志"}));
 expect(await screen.findByRole("alert")).toHaveTextContent("文件编码");
});

it("切换文件会取消旧读取，迟到响应不会覆盖当前文件",async()=>{
 let release!:(response:Response)=>void;
 const fetcher=vi.fn().mockImplementationOnce(()=>new Promise<Response>(resolve=>{release=resolve;})).mockResolvedValueOnce(rangeResponse("当前文本"));
 vi.stubGlobal("fetch",fetcher);
 const view=render(<TextResultPreview url="/old.txt" kind="text"/>);
 view.rerender(<TextResultPreview url="/new.txt" kind="text"/>);
 await screen.findByText("当前文本");expect(fetcher.mock.calls[0][1].signal.aborted).toBe(true);
 await act(async()=>{release(rangeResponse("旧文本"));});
 expect(screen.getByLabelText("文件原文").textContent).toBe("当前文本");
});

it("登记的无扩展名资产按原文件名预览，保持旧选择键",async()=>{
 const url="/api/projects/p/assets/log-id/download",key="profile:data:"+url+":log-id";
 sessionStorage.setItem("analysis-result-selection:asset-job",JSON.stringify({module:"profile",output:key}));
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue(rangeResponse("已登记日志 001")));
 const result={success:true,status:"completed",job:{id:"asset-job",module:"profile"},outputs:[],
 assets:[{id:"notes-id",original_name:"说明.txt",download_url:"/api/projects/p/assets/notes-id/download"},
 {id:"log-id",original_name:"运行.log",download_url:url}],result:{}} as unknown as JobResultsResponse;
 render(<JobResultPanel result={result} loading={false}/>,{wrapper:MemoryRouter});
 await screen.findByText("已登记日志 001");
 expect(screen.getByLabelText("结果文件")).toHaveValue(key);
 expect(screen.getByLabelText("日志预览范围")).toHaveValue("end");
});

it("空白行边界不误报2000行，未知格式仍只下载",async()=>{
 vi.stubGlobal("fetch",vi.fn().mockResolvedValue(rangeResponse("\n")));
 const view=render(<TextResultPreview url="/blank.log" kind="log"/>);
 await screen.findByText("日志文件为空。");expect(screen.queryByText(/2000 行/)).not.toBeInTheDocument();
 view.unmount();const fetcher=vi.fn();vi.stubGlobal("fetch",fetcher);
 render(<ViewArea kind="data" url="/data.rds"/>);expect(fetcher).not.toHaveBeenCalled();
 expect(textOutputKind("csv","/table.log")).toBeNull();
});
