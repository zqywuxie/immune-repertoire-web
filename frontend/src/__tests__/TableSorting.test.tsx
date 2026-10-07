import { afterEach, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { TablePreview } from "../features/results/TablePreview";
import { compareTableValues } from "../features/results/tableSorting";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("精确比较大整数、极小科学计数法与零，两个方向都将空值置后", () => {
  expect(compareTableValues("1790983155444449152","1790983155444449151","numeric","asc")).toBeGreaterThan(0);
  expect(compareTableValues("1.000000000000000000000001e-9","1.000000000000000000000000e-9","numeric","asc")).toBeGreaterThan(0);
  expect(compareTableValues("1e-1000","0","numeric","asc")).toBeGreaterThan(0);
  expect(compareTableValues("-0","+0.000","numeric","desc")).toBe(0);
  expect(compareTableValues("NaN","1","numeric","desc")).toBeGreaterThan(0);
  expect(compareTableValues("NA","","numeric","asc")).toBe(0);
});

it("有限本地预览排序保留原文、切换方向、恢复顺序及分页复位", async () => {
  const rows = Array.from({length:30},(_,i)=>[String(i+1).padStart(3,"0"),String(30-i)]);
  rows.push(["031","1790983155444449152"],["032","1790983155444449151"]);
  vi.stubGlobal("fetch",vi.fn().mockResolvedValue(new Response("编号,数值\n"+rows.map(row=>row.join(",")).join("\n"))));
  render(<TablePreview url="/local.csv" />);
  await screen.findByText("001");
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));
  fireEvent.change(screen.getByLabelText("排序方式"),{target:{value:"numeric"}});
  fireEvent.click(screen.getByRole("button",{name:"按数值排序"}));
  expect(within(screen.getByRole("table")).getAllByRole("row")[1]).toHaveTextContent("030");
  expect(screen.getByText("第 1 / 2 页 · 匹配 32 行")).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"按数值排序"}).closest("th")).toHaveAttribute("aria-sort","ascending");
  fireEvent.click(screen.getByRole("button",{name:"按数值排序"}));
  expect(within(screen.getByRole("table")).getAllByRole("row")[1]).toHaveTextContent("1790983155444449152");
  expect(within(screen.getByRole("table")).getAllByRole("row")[2]).toHaveTextContent("1790983155444449151");
  fireEvent.click(screen.getByRole("button",{name:"恢复原始顺序"}));
  expect(within(screen.getByRole("table")).getAllByRole("row")[1]).toHaveTextContent("001");
});

it("服务端排序请求针对整张表，排序复位页码，失败可以恢复原始顺序", async () => {
  const respond = (rows: string[][]) => new Response(JSON.stringify({success:true,columns:["编号","数值"],rows,total_rows:32,matched_rows:32,offset:0,limit:25}),{headers:{"content-type":"application/json"}});
  const fetcher = vi.fn().mockImplementation((_url,options)=>{
    const body = JSON.parse(options.body);
    if (body.sort_direction === "desc") return Promise.resolve(new Response(JSON.stringify({message:"临时排序空间不可用"}),{status:503,headers:{"content-type":"application/json"}}));
    return Promise.resolve(respond(body.sort_column === 1 ? [["032","1e-1000"]] : body.offset ? [["026","10"]] : [["001","20"]]));
  });
  vi.stubGlobal("fetch",fetcher);
  render(<TablePreview jobId="table-job" url="/table.csv" />);
  await screen.findByText("001");
  fireEvent.click(screen.getByRole("button",{name:"下一页"}));await screen.findByText("026");
  fireEvent.change(screen.getByLabelText("排序方式"),{target:{value:"numeric"}});
  fireEvent.click(screen.getByRole("button",{name:"按数值排序"}));
  await screen.findByText("032");
  expect(JSON.parse(fetcher.mock.calls.at(-1)![1].body)).toEqual({url:"/table.csv",offset:0,limit:25,query:"",sort_column:1,sort_direction:"asc",sort_mode:"numeric"});
  fireEvent.click(screen.getByRole("button",{name:"按数值排序"}));
  expect(await screen.findByRole("alert")).toHaveTextContent("临时排序空间不可用");
  fireEvent.click(screen.getByRole("button",{name:"恢复原始顺序"}));
  await screen.findByText("001");
  expect(JSON.parse(fetcher.mock.calls.at(-1)![1].body)).not.toHaveProperty("sort_column");
});

it("切换文件中止旧排序，迟到页不覆盖新表", async () => {
  let finishOld!: (value:Response)=>void;
  const page = (value:string) => new Response(JSON.stringify({success:true,columns:["编号"],rows:[[value]],total_rows:1,matched_rows:1,offset:0,limit:25}),{headers:{"content-type":"application/json"}});
  const fetcher = vi.fn().mockResolvedValueOnce(page("旧记录"))
    .mockImplementationOnce(()=>new Promise<Response>(resolve=>{finishOld=resolve;}))
    .mockResolvedValueOnce(page("新记录"));
  vi.stubGlobal("fetch",fetcher);
  const view=render(<TablePreview jobId="table-job" url="/first.csv" />);
  await screen.findByText("旧记录");
  fireEvent.click(screen.getByRole("button",{name:"按编号排序"}));
  await waitFor(()=>expect(fetcher).toHaveBeenCalledTimes(2));
  const signal=fetcher.mock.calls[1][1].signal;
  view.rerender(<TablePreview jobId="table-job" url="/new.csv" />);
  expect(signal.aborted).toBe(true);
  await screen.findByText("新记录");
  await act(async()=>{finishOld(page("迟到旧排序"));});
  expect(screen.queryByText("迟到旧排序")).not.toBeInTheDocument();
});
