import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { TablePreview } from "../features/results/TablePreview";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("向后端请求整表分页，筛选后回到第一页，切换结果重置条件", async () => {
  const fetcher = vi.fn().mockImplementation((_url: string, options: RequestInit) => {
    const body = JSON.parse(String(options.body));
    return Promise.resolve(new Response(JSON.stringify({success:true,columns:["样本"],rows:[[body.query ? "第1100行匹配" : body.url === "/new.csv" ? "新结果" : `行${body.offset}`]],total_rows:1200,matched_rows:body.query?1:1200,offset:body.offset,limit:25}), {headers:{"Content-Type":"application/json"}}));
  });
  vi.stubGlobal("fetch", fetcher);
  const view = render(<TablePreview jobId="job" url="/data.csv" />);
  await screen.findByText("行0");
  fireEvent.click(screen.getByText("下一页"));
  await screen.findByText("行25");
  fireEvent.change(screen.getByLabelText("筛选全部数据"), {target:{value:"目标"}});
  expect(fetcher).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole("button", {name:"筛选"}));
  await screen.findByText("第1100行匹配");
  expect(JSON.parse(fetcher.mock.calls[2][1].body)).toEqual({url:"/data.csv",query:"目标",offset:0,limit:25});
  view.rerender(<TablePreview jobId="job" url="/new.csv" />);
  await screen.findByText("新结果");
  expect(screen.getByLabelText("筛选全部数据")).toHaveValue("");
});

it("查询失败后可重试，切换页面取消原请求", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({message:"文件已移除"}), {status:409})).mockResolvedValueOnce(new Response(JSON.stringify({columns:[],rows:[],total_rows:0,matched_rows:0,offset:0,limit:25})));
  vi.stubGlobal("fetch",fetcher);
  const view=render(<TablePreview jobId="job" url="/data.csv" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("文件已移除");
  fireEvent.click(screen.getByText("重新加载"));
  await screen.findByText("数据表为空。");
  view.unmount();
  await waitFor(()=>expect(fetcher.mock.calls[1][1].signal.aborted).toBe(true));
});
