import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { parseTable, TablePreview } from "../features/results/TablePreview";
import { ViewArea } from "../features/results/ResultViewer";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

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
