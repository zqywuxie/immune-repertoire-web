import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ResultOutputBrowser } from "../features/results/ResultOutputBrowser";
import { comparisonLabel, organizeOutput, resultComparisons } from "../features/results/resultOrganization";
import { JobResultPanel } from "../features/jobs/JobResultPanel";
import type { JobResultsResponse } from "../shared/api/jobs";

afterEach(() => { cleanup(); sessionStorage.clear(); });

it("按既有脚本路径区分链、内容和真实比较，保留无标签及含特殊字符的历史文件", () => {
  const comparisons = resultComparisons({comparisons:[{group1:"病例 A",group2:"对照(B)"}]});
  const output = organizeOutput({key:"v",kind:"image",label:"TRB_病例_A_vs_对照_B_volcano.png",url:"/api/script-hub/results/job/volcano/TRB_病例_A_vs_对照_B_volcano.png"}, comparisons);
  expect(output.content).toBe("差异比较");
  expect(output.chains).toEqual(["TRB"]);
  expect(organizeOutput({...output,kind:"pdf"}, comparisons).content).toBe("差异比较");
  expect(comparisonLabel(output.comparison,comparisons)).toBe("病例 A 与 对照(B)");
  expect(organizeOutput({key:"u",kind:"png",label:"TRAV1.png",url:"/api/script-hub/results/TRB-job/new.png?chain=IGH"}).chains).toEqual([]);
  expect(organizeOutput({key:"c",kind:"image",label:"TRB.csv",url:"/api/script-hub/results/job/病例_vs_对照/1VJusage/TRB/plot.png"})).toMatchObject({content:"基因使用频率",chains:["TRB"],comparison:"directory:病例_vs_对照"});
  expect(organizeOutput({key:"raw",kind:"image",label:"原始结果",url:"/%broken.png"})).toMatchObject({content:"其他结果",chains:[],comparison:""});
  const spaced = organizeOutput({key:"space",kind:"png",label:"TRB.png",url:"/api/script-hub/results/job/病例%20A_vs_对照%20B/TRB/plot.png"});
  expect(comparisonLabel(spaced.comparison,[])).toBe("病例 A 与 对照 B");
  const ambiguous = resultComparisons({comparisons:[{group1:"病例 一",group2:"对照"},{group1:"病例 二",group2:"对照"}]});
  expect(organizeOutput({key:"a",kind:"png",label:"",url:"/group_vs_group/plot.png"},ambiguous).comparison).toBe("");
});

it("千个图表分页、筛选和缩略图按需加载，搜索无匹配可清除", () => {
  const outputs = Array.from({length:1000},(_,i)=>({key:String(i),kind:"png",label:(i%2?"TRA":"TRB")+"_UMAP_"+i+".png",url:"/plots/"+i+".png"}));
  const select = vi.fn();
  render(<ResultOutputBrowser outputs={outputs} selectedKey="0" onSelect={select} storageKey="browser" comparisons={[]} />);
  const list = screen.getByLabelText("图表与报告列表");
  expect(within(list).getAllByRole("button")).toHaveLength(12);
  expect(list.querySelectorAll("img")).toHaveLength(0);
  fireEvent.click(within(screen.getByRole("navigation",{name:"图表列表分页"})).getByRole("button",{name:"下一页"}));
  fireEvent.click(screen.getByRole("button",{name:/TRB_UMAP_12.png/}));
  expect(select).toHaveBeenLastCalledWith("12");
  fireEvent.change(screen.getByLabelText("受体链"),{target:{value:"TRA"}});
  expect(screen.getByText("找到 500 个结果，共 1000 个")).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("显示缩略图"));
  expect(list.querySelectorAll("img")).toHaveLength(12);
  expect([...list.querySelectorAll("img")].every(img=>img.getAttribute("loading")==="lazy")).toBe(true);
  fireEvent.error(list.querySelector("img")!);
  expect(screen.getByText("缩略图不可用，点击查看文件")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("查找图表或报告"),{target:{value:"不存在"}});
  expect(screen.getByText(/没有匹配的结果/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"清除筛选"}));
  expect(screen.getByText("找到 1000 个结果，共 1000 个")).toBeInTheDocument();
});

it("刷新保留筛选与页码，移除分类后仍可浏览剩余结果", () => {
  const outputs = Array.from({length:30},(_,i)=>({key:String(i),kind:"png",label:"TRB_Shannon_"+i+".png",url:"/plots/"+i+".png"}));
  const props = {outputs,selectedKey:"14",onSelect:vi.fn(),storageKey:"remember",comparisons:[]};
  const view = render(<ResultOutputBrowser {...props} />);
  expect(screen.getByText("第 2 / 3 页")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("分析内容"),{target:{value:"多样性"}});
  fireEvent.click(within(screen.getByRole("navigation",{name:"图表列表分页"})).getByRole("button",{name:"下一页"}));
  view.unmount();
  const restored = render(<ResultOutputBrowser {...props} />);
  expect(screen.getByLabelText("分析内容")).toHaveValue("多样性");
  expect(screen.getByText("第 2 / 3 页")).toBeInTheDocument();
  restored.rerender(<ResultOutputBrowser {...props} outputs={[{key:"new",kind:"html",label:"分析报告",url:"/new.html"}]} />);
  expect(screen.getByRole("button",{name:/分析报告/})).toBeInTheDocument();
  expect(screen.getByLabelText("分析内容")).toHaveValue("");
});

it("共享结果面板使用卡片选择文件并恢复当前图表，不在浏览列表加载全部图片", () => {
  const result = {success:true,status:"completed",job:{id:"gallery",module:"profile"},outputs:[
    {kind:"html",label:"分析报告",url:"/report.html"},
    {kind:"png",label:"TRB_Shannon.png",url:"/TRB_Shannon.png"},
    {kind:"png",label:"TRA_Shannon.png",url:"/TRA_Shannon.png"},
  ],assets:[],result:{}} as unknown as JobResultsResponse;
  const view = render(<JobResultPanel result={result} loading={false} />,{wrapper:MemoryRouter});
  expect(screen.queryByLabelText("结果文件")).not.toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:/TRB_Shannon.png/}));
  expect(screen.getByRole("img")).toHaveAttribute("src","/TRB_Shannon.png");
  expect(screen.getAllByRole("img")).toHaveLength(1);
  expect(screen.getByLabelText("当前结果预览")).toHaveFocus();
  fireEvent.click(screen.getByRole("button", {name:"返回图表列表"}));
  expect(screen.getByRole("button",{name:/TRB_Shannon.png/})).toHaveFocus();
  view.unmount();
  render(<JobResultPanel result={result} loading={false} />,{wrapper:MemoryRouter});
  expect(screen.getByRole("button",{name:/TRB_Shannon.png/})).toHaveAttribute("aria-pressed","true");
  expect(screen.getByRole("img")).toHaveAttribute("src","/TRB_Shannon.png");
});
