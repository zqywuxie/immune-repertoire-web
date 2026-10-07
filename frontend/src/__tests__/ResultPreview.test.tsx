import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { parseTable, TablePreview } from "../features/results/TablePreview";
import { ViewArea } from "../features/results/ResultViewer";
import { JobResultPanel } from "../features/jobs/JobResultPanel";
import type { JobResultsResponse } from "../shared/api/jobs";
import { MemoryRouter } from "react-router-dom";

afterEach(() => { cleanup(); sessionStorage.clear(); vi.unstubAllGlobals(); });

it("保留编号、科学计数法、引号中的逗号和换行", () => {
  expect(parseTable('\uFEFF样本,备注,值\r\n001,"第一行,内容\n第二行""引号",1.00000000001e-9\r\n').rows).toEqual([
    ["样本", "备注", "值"], ["001", '第一行,内容\n第二行"引号', "1.00000000001e-9"],
  ]);
  expect(parseTable("样本\t值\n001\t2", "\t").rows[1]).toEqual(["001", "2"]);
  expect(parseTable('样本,值\n001,"不完整', ",", true)).toEqual({ rows: [["样本", "值"]], limited: true });
});

it("分页筛选数据，切换文件不保留旧表格", async () => {
  const csv = "样本,值\n" + Array.from({ length: 30 }, (_, i) => `样本${i},${i}`).join("\n");
  vi.stubGlobal("fetch", vi.fn().mockImplementation((url: string) => Promise.resolve(new Response(url === "/first.csv" ? csv : "样本,值\n新样本,1"))));
  const view = render(<TablePreview url="/first.csv" />);
  expect(await screen.findByText("样本0")).toBeInTheDocument();
  expect(screen.queryByText("样本29")).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("下一页"));
  expect(screen.getByText("样本29")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("筛选预览内容"), { target: { value: "样本1" } });
  expect(screen.getByText("样本1")).toBeInTheDocument();
  expect(screen.getByText(/匹配 11 行/)).toBeInTheDocument();
  view.rerender(<TablePreview url="/second.csv" />);
  expect(await screen.findByText("新样本")).toBeInTheDocument();
  expect(screen.queryByText("样本1")).not.toBeInTheDocument();
});

it("区别空表与文件缺失，并可重试", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(new Response("", { status: 404 })).mockResolvedValueOnce(new Response("")));
  render(<TablePreview url="/missing.csv" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("结果文件不存在或已移除");
  fireEvent.click(screen.getByText("重新加载"));
  expect(await screen.findByText("数据表为空。")).toBeInTheDocument();
});

it("大表提示预览范围，图片失败提供恢复操作", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("样本\n" + Array.from({ length: 1100 }, (_, i) => `S${i}`).join("\n"))));
  const view = render(<TablePreview url="/large.csv" />);
  expect(await screen.findByText(/仅预览前 1000 行/)).toBeInTheDocument();
  view.unmount();
  render(<ViewArea kind="png" url="/missing.png" />);
  fireEvent.error(screen.getByRole("img"));
  expect(screen.getByRole("alert")).toHaveTextContent("图片加载失败");
  fireEvent.click(screen.getByText("重新加载"));
  expect(screen.getByRole("img")).toBeInTheDocument();
});

it("鍘嗗彶浠诲姟鍙湪缁撴灉闈㈤€夋嫨骞堕瑙堟満鍣ㄥ涔犵ǔ瀹氱壒寰佽〃", async () => {
  const fetcher = vi.fn().mockImplementation((_url, options) => options?.method === "HEAD" ? Promise.resolve(new Response("", {headers:{"Content-Type":"text/html"}})) : Promise.resolve(new Response(JSON.stringify({
    success: true,
    columns: ["feature", "selection_frequency", "selected_for_final_model"],
    rows: [["signal", "1.0", "true"]],
    total_rows: 1,
    matched_rows: 1,
    offset: 0,
    limit: 25,
  }), { headers: { "Content-Type": "application/json" } })));
  vi.stubGlobal("fetch", fetcher);
  const result = {
    success: true,
    status: "completed",
    job: { id: "ml-job", module: "ml-analysis", status: "completed" },
    outputs: [
      { kind: "html", label: "鍒嗘瀽鎶ュ憡", url: "/ml-job.html" },
      { kind: "csv", label: "feature_stability.csv", url: "/api/script-hub/results/ml-job/profile_Disease/feature_stability.csv" },
      { kind: "csv", label: "stable_features.csv", url: "/api/script-hub/results/ml-job/profile_Disease/stable_features.csv" },
    ],
    assets: [],
    result: {},
  } as unknown as JobResultsResponse;

  render(<JobResultPanel result={result} loading={false} />, { wrapper: MemoryRouter });
  fireEvent.click(screen.getByRole("tab", { name: /数据表/ }));
  const stabilityOption = screen.getByRole("option", { name: /feature_stability\.csv/ });
  fireEvent.change(screen.getByLabelText("结果文件"), { target: { value: stabilityOption.getAttribute("value") } });

  expect(await screen.findByText("selection_frequency")).toBeInTheDocument();
  expect(screen.getByText("signal")).toBeInTheDocument();
  expect(JSON.parse(String(fetcher.mock.calls.find(call => call[1]?.method === "POST")![1].body))).toEqual({
    url: "/api/script-hub/results/ml-job/profile_Disease/feature_stability.csv",
    offset: 0,
    limit: 25,
    query: "",
  });
});


it("结果刷新与输出排序变化后恢复选择，切换任务不沿用旧任务文件", async () => {
  const makeResult = (id: string, reverse = false) => ({
    success: true, status: "completed",
    job: { id, module: "profile", status: "completed" },
    outputs: reverse ? [
      { kind: "html", label: "默认报告", url: `/${id}/first.html`, module: "profile" },
      { kind: "html", label: "新增报告", url: `/${id}/third.html`, module: "profile" },
      { kind: "html", label: "另一组报告", url: `/${id}/second.html`, module: "profile" },
    ] : [
      { kind: "html", label: "默认报告", url: `/${id}/first.html`, module: "profile" },
      { kind: "html", label: "另一组报告", url: `/${id}/second.html`, module: "profile" },
    ], assets: [], result: {},
  } as unknown as JobResultsResponse);
  const view = render(<JobResultPanel result={makeResult("job-one")} loading={false} />, { wrapper: MemoryRouter });
  fireEvent.click(screen.getByRole("button", { name: /另一组报告/ }));
  expect(screen.getByRole("link", { name: "打开交互报告" })).toHaveAttribute("href", "/job-one/second.html");
  view.unmount();
  const refreshed = render(<JobResultPanel result={makeResult("job-one", true)} loading={false} />, { wrapper: MemoryRouter });
  expect(screen.getByRole("link", { name: "打开交互报告" })).toHaveAttribute("href", "/job-one/second.html");
  refreshed.rerender(<JobResultPanel result={makeResult("job-two")} loading={false} />);
  expect(screen.getByRole("link", { name: "打开交互报告" })).toHaveAttribute("href", "/job-two/first.html");
  refreshed.rerender(<JobResultPanel result={makeResult("job-one")} loading={false} />);
  expect(screen.getByRole("link", { name: "打开交互报告" })).toHaveAttribute("href", "/job-one/second.html");
  refreshed.rerender(<JobResultPanel result={{...makeResult("job-one"), outputs: makeResult("job-one").outputs.slice(0,1)}} loading={false} />);
  expect(screen.getByRole("link", { name: "打开交互报告" })).toHaveAttribute("href", "/job-one/first.html");
});


it("失败与中断的结果页直接展示原因，取消不呈现成功结果", () => {
  const result = {success: true, status: "failed", job: {id: "failed-go", module: "go-kegg-enrichment", detail: "差异表达结果中没有可映射的人类基因符号。"}, outputs: [], assets: [], result: {}} as unknown as JobResultsResponse;
  const view = render(<JobResultPanel result={result} loading={false} />, {wrapper: MemoryRouter});
  expect(screen.getByRole("alert")).toHaveTextContent("分析未成功完成");
  expect(screen.getByRole("alert")).toHaveTextContent("没有可映射的人类基因符号");
  view.rerender(<JobResultPanel result={{...result, status: "interrupted"}} loading={false} />);
  expect(screen.getByRole("alert")).toHaveTextContent("分析运行已中断");
  view.rerender(<JobResultPanel result={{...result, status: "cancelled"}} loading={false} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText(/分析已取消；已生成的文件仍可查看/)).toBeInTheDocument();
});


it("结果分区只加载选中文件，兼容历史选择并在刷新后恢复", async () => {
  const fetcher = vi.fn().mockImplementation((_url, options) => options?.method === "HEAD" ? Promise.resolve(new Response("", {headers:{"Content-Type":"text/html"}})) : Promise.resolve(new Response(JSON.stringify({success:true, columns:["sample"], rows:[["001"]], total_rows:1, matched_rows:1, offset:0, limit:25}), {headers:{"Content-Type":"application/json"}})));
  vi.stubGlobal("fetch", fetcher);
  const result = { success:true, status:"completed", job:{id:"sections-job", module:"profile"}, outputs:[
    {kind:"html", label:"分析报告", url:"/report.html"},
    {kind:"png", label:"分组图表", url:"/plot.png"},
    {kind:"csv", label:"样本坐标.csv", url:"/points.csv"},
    {kind:"json", label:"计算参数", url:"/parameters.json"},
    {kind:"zip", label:"完整结果包", url:"/results.zip"},
  ], assets:[], result:{} } as unknown as JobResultsResponse;
  const view = render(<JobResultPanel result={result} loading={false} />, {wrapper: MemoryRouter});
  expect(screen.getByRole("tab", {name:/图表与报告/})).toHaveAttribute("aria-selected", "true");
  expect(screen.queryByRole("option", {name:/样本坐标/})).not.toBeInTheDocument();
  expect(fetcher.mock.calls.every(call => call[1]?.method === "HEAD")).toBe(true);
  fireEvent.click(screen.getByRole("tab", {name:/数据表/}));
  expect(await screen.findByText("001")).toBeInTheDocument();
  expect(fetcher.mock.calls.filter(call => call[1]?.method === "POST")).toHaveLength(1);
  view.unmount();
  const refreshed = render(<JobResultPanel result={result} loading={false} />, {wrapper: MemoryRouter});
  expect(screen.getByRole("tab", {name:/数据表/})).toHaveAttribute("aria-selected", "true");
  expect(await screen.findByText("001")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("tab", {name:"分析详情"}));
  expect(screen.getByText("分析记录与复现参数")).toBeInTheDocument();
  expect(screen.getByRole("option", {name:/计算参数/})).toBeInTheDocument();
  expect(screen.queryByRole("option", {name:/样本坐标/})).not.toBeInTheDocument();
  refreshed.unmount();
  // Older saved selections had no section field.
  sessionStorage.setItem("analysis-result-selection:sections-job", JSON.stringify({module:"profile", output:"profile:csv:/points.csv:"}));
  render(<JobResultPanel result={result} loading={false} />, {wrapper: MemoryRouter});
  expect(screen.getByRole("tab", {name:/数据表/})).toHaveAttribute("aria-selected", "true");
  expect(screen.getByLabelText("结果文件")).toHaveValue("profile:csv:/points.csv:");
});

it("图片切换清除失败状态，放大查看支持缩放、关闭与焦点恢复", () => {
  const view = render(<ViewArea kind="png" url="/missing.png" />);
  fireEvent.error(screen.getByRole("img"));
  expect(screen.getByRole("alert")).toHaveTextContent("图片加载失败");
  view.rerender(<ViewArea kind="png" url="/actual.png" label="样本分组图" />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("button", {name:"放大查看"})).toBeDisabled();
  fireEvent.load(screen.getByRole("img", {name:"样本分组图"}));
  const expand = screen.getByRole("button", {name:"放大查看"});
  expand.focus();fireEvent.click(expand);
  expect(screen.getByRole("dialog", {name:"图表放大查看"})).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", {name:"放大图表"}));
  expect(screen.getByLabelText("缩放比例")).toHaveTextContent("150%");
  expect(screen.getByRole("img", {name:/放大视图/})).toHaveStyle({width:"150%"});
  fireEvent.click(screen.getByRole("button", {name:"适应窗口"}));
  expect(screen.getByLabelText("缩放比例")).toHaveTextContent("100%");
  fireEvent.keyDown(document, {key:"Escape"});
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(expand).toHaveFocus();
});


it("结构化文件保留大整数与原始精度，缺失、空文件和错误网页可重试区分", async () => {
  const source = '{"sample":"001","mtime_ns":1790983155444449151,"value":1.00000000001e-9}\n';
  const fetcher = vi.fn().mockResolvedValueOnce(new Response("", {status:404}))
    .mockResolvedValueOnce(new Response(source, {headers:{"content-type":"application/json"}}))
    .mockResolvedValueOnce(new Response(""))
    .mockResolvedValueOnce(new Response("<html>login</html>", {headers:{"content-type":"text/html"}}));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<ViewArea kind="json" url="/metadata.json" downloadUrl="/original.json" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("结果文件不存在或已移除");
  fireEvent.click(screen.getByRole("button", {name:"重新加载"}));
  const preview = await screen.findByLabelText("文件原文");
  expect(preview.textContent).toBe(source);
  expect(screen.getByRole("link", {name:"下载完整结构化数据"})).toHaveAttribute("href", "/original.json");
  view.rerender(<ViewArea kind="json" url="/empty.json" />);
  expect(screen.queryByLabelText("文件原文")).not.toBeInTheDocument();
  expect(await screen.findByText("结构化数据文件为空。")).toBeInTheDocument();
  view.rerender(<ViewArea kind="json" url="/unexpected.json" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("此链接返回了网页");
  expect(screen.queryByText("login")).not.toBeInTheDocument();
});

it("切换结构化文件中止旧读取，迟到内容不覆盖当前文件", async () => {
  let finishOld!: (response: Response) => void;
  const fetcher = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { finishOld = resolve; }))
    .mockResolvedValueOnce(new Response('{"current":"新文件"}'));
  vi.stubGlobal("fetch", fetcher);
  const view = render(<ViewArea kind="json" url="/old.json" />);
  const signal = fetcher.mock.calls[0][1].signal as AbortSignal;
  view.rerender(<ViewArea kind="json" url="/new.json" />);
  expect(signal.aborted).toBe(true);
  expect((await screen.findByLabelText("文件原文")).textContent).toBe('{"current":"新文件"}');
  await act(async () => { finishOld(new Response('{"old":"迟到内容"}')); });
  expect(screen.getByLabelText("文件原文").textContent).toBe('{"current":"新文件"}');
  expect(screen.queryByText(/迟到内容/)).not.toBeInTheDocument();
});

it("大结构化结果只预览前2MB并取消流，截断多字节字符不报格式错误", async () => {
  const limit = 2 * 1024 * 1024, prefix = '{"blob":"';
  const payload = prefix + 'a'.repeat(limit - prefix.length - 1) + '中文' + 'b'.repeat(2000) + 'UNREAD_TAIL"}';
  const cancel = vi.fn();
  const stream = new ReadableStream<Uint8Array>({start(controller) {controller.enqueue(new TextEncoder().encode(payload));},cancel});
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(stream, {headers:{"content-type":"application/json"}})));
  render(<ViewArea kind="json" url="/large.json" />);
  expect(await screen.findByText(/仅预览前 2 MB/)).toBeInTheDocument();
  const text = screen.getByLabelText("文件原文").textContent!;
  expect(new TextEncoder().encode(text).byteLength).toBeLessThanOrEqual(limit);
  expect(text.includes('UNREAD_TAIL')).toBe(false);
  expect(text.includes('�')).toBe(false);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.queryByText(/无法按 JSON 解析/)).not.toBeInTheDocument();
  await waitFor(() => expect(cancel).toHaveBeenCalledOnce());
});

it("语法错误的结构化结果提示原文检查，不修改或隐藏文件内容", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"unfinished":')));
  render(<ViewArea kind="json" url="/invalid.json" />);
  expect(await screen.findByText(/文件内容无法按 JSON 解析/)).toBeInTheDocument();
  expect(screen.getByLabelText("文件原文").textContent).toBe('{"unfinished":');
});
