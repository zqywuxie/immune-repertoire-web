import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ViewArea } from "../features/results/ResultViewer";

afterEach(() => {cleanup();vi.useRealTimers();vi.unstubAllGlobals();});
const htmlHead = () => new Response("",{headers:{"content-type":"text/html","content-length":"120"}});
const pdfHead = () => new Response("",{headers:{"content-type":"application/pdf","content-length":"120"}});

it("报告缺失阻止空白预览，重试检查后载入并保留原始打开链接", async () => {
  const fetcher=vi.fn().mockResolvedValueOnce(new Response("",{status:404})).mockResolvedValueOnce(htmlHead());
  vi.stubGlobal("fetch",fetcher);
  render(<ViewArea kind="html" url="/report.html" label="分组分析报告" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("结果文件不存在或已移除");
  expect(screen.queryByTitle("分组分析报告（网页报告）")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"重新加载"}));
  const frame=await screen.findByTitle("分组分析报告（网页报告）");
  expect(frame.getAttribute("src")).toContain("_preview_retry=1");
  expect(frame).toHaveAttribute("sandbox","allow-scripts allow-same-origin allow-downloads");
  fireEvent.load(frame);
  expect(screen.queryByText("正在载入网页报告…")).not.toBeInTheDocument();
  expect(screen.getByRole("link",{name:"在新标签页查看报告"})).toHaveAttribute("href","/report.html");
  expect(fetcher.mock.calls.every(call=>call[1].method==="HEAD")).toBe(true);
});

it("PDF 区分错误网页、登录失效和空文件，错误状态不会沿用到另一文件", async () => {
  vi.stubGlobal("fetch",vi.fn().mockResolvedValueOnce(htmlHead()).mockResolvedValueOnce(new Response("",{status:403})).mockResolvedValueOnce(new Response("",{headers:{"content-type":"application/pdf","content-length":"0"}})));
  const view=render(<ViewArea kind="pdf" url="/wrong.pdf" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("未返回 PDF 文档");
  view.rerender(<ViewArea kind="pdf" url="/private.pdf" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("项目权限");
  expect(screen.queryByText(/未返回 PDF 文档/)).not.toBeInTheDocument();
  view.rerender(<ViewArea kind="pdf" url="/empty.pdf" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("报告文件为空");
  expect(screen.queryByTitle("文档查看器")).not.toBeInTheDocument();
});

it("HEAD 不可用时只检查 GET 元数据并取消内容流，预览失败保留下载入口", async () => {
  const cancel=vi.fn();
  const stream=new ReadableStream<Uint8Array>({start(controller){controller.enqueue(new Uint8Array(3*1024*1024));},cancel});
  const fetcher=vi.fn().mockResolvedValueOnce(new Response("",{status:405}))
    .mockResolvedValueOnce(new Response(stream,{headers:{"content-type":"application/pdf"}}));
  vi.stubGlobal("fetch",fetcher);
  render(<ViewArea kind="pdf" url="/view.pdf" downloadUrl="/original.pdf?download=1" />);
  const frame=await screen.findByTitle("文档查看器");
  await waitFor(()=>expect(cancel).toHaveBeenCalledOnce());
  expect(fetcher.mock.calls[1][1].method).toBeUndefined();
  fireEvent.error(frame);
  expect(screen.getByRole("alert")).toHaveTextContent("报告预览加载失败");
  expect(screen.getByRole("link",{name:"下载文档"})).toHaveAttribute("href","/original.pdf?download=1");
});

it("切换报告中止旧检查，迟到结果不能替换当前文档", async () => {
  let finishOld!: (value:Response)=>void;
  const fetcher=vi.fn().mockImplementationOnce(()=>new Promise<Response>(resolve=>{finishOld=resolve;})).mockResolvedValueOnce(htmlHead());
  vi.stubGlobal("fetch",fetcher);
  const view=render(<ViewArea kind="html" url="/old.html" />);
  const signal=fetcher.mock.calls[0][1].signal as AbortSignal;
  view.rerender(<ViewArea kind="html" url="/new.html" />);
  expect(signal.aborted).toBe(true);
  expect(await screen.findByTitle("网页报告")).toHaveAttribute("src","/new.html");
  await act(async()=>{finishOld(htmlHead());});
  expect(screen.getByTitle("网页报告")).toHaveAttribute("src","/new.html");
});

it("长时间检查保留等待和重试，重试中止旧请求", async () => {
  vi.useFakeTimers();
  const fetcher=vi.fn().mockImplementation(()=>new Promise<Response>(()=>{}));
  vi.stubGlobal("fetch",fetcher);
  render(<ViewArea kind="html" url="/slow.html" />);
  await act(async()=>{vi.advanceTimersByTime(30000);});
  expect(screen.getByText(/加载时间较长/)).toBeInTheDocument();
  const signal=fetcher.mock.calls[0][1].signal as AbortSignal;
  fireEvent.click(screen.getByRole("button",{name:"重新加载"}));
  expect(signal.aborted).toBe(true);
  expect(fetcher).toHaveBeenCalledTimes(2);
});

it("下载型响应和不支持内嵌 PDF 的浏览器提供明确回退操作", async () => {
  const fetcher=vi.fn().mockResolvedValueOnce(new Response("",{headers:{"content-type":"application/pdf","content-disposition":"attachment; filename=document.pdf"}})).mockResolvedValueOnce(pdfHead());
  vi.stubGlobal("fetch",fetcher);
  const view=render(<ViewArea kind="pdf" url="/attachment.pdf" />);
  expect(await screen.findByText(/此链接以下载方式提供文件/)).toBeInTheDocument();
  expect(screen.queryByTitle("文档查看器")).not.toBeInTheDocument();
  vi.stubGlobal("navigator",{pdfViewerEnabled:false});
  view.rerender(<ViewArea kind="pdf" url="/supported.pdf" />);
  expect(await screen.findByText(/当前浏览器不支持内嵌 PDF/)).toBeInTheDocument();
  expect(screen.getByRole("link",{name:"下载文档"})).toBeInTheDocument();
});

it("外部报告保留原有嵌入能力与签名链接，不发跨域检查请求", async () => {
  const fetcher=vi.fn();vi.stubGlobal("fetch",fetcher);
  render(<ViewArea kind="html" url="https://example.org/report.html?signature=fixture" />);
  const frame=await screen.findByTitle("网页报告");
  expect(frame).toHaveAttribute("src","https://example.org/report.html?signature=fixture");
  fireEvent.load(frame);
  fireEvent.click(screen.getByRole("button",{name:"重新加载"}));
  expect(await screen.findByTitle("网页报告")).toHaveAttribute("src","https://example.org/report.html?signature=fixture");
  expect(fetcher).not.toHaveBeenCalled();
});
