import {afterEach,beforeEach,describe,expect,it,vi} from "vitest";
import {act,cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {ContinueAnalysis} from "../features/results/ContinueAnalysis";
import {apiClient} from "../shared/api/client";
import * as sources from "../shared/api/scriptHub";
import type {JobResultsResponse} from "../shared/api/jobs";
const result={success:true,status:"completed",job:{id:"source-1",module:"pep-analysis",project_id:"项目 01",payload:{asset_set:"数据集 02"}},outputs:[],assets:[],result:{}} as unknown as JobResultsResponse;
const candidate={id:"a",artifact_id:"source-1:table:路径",job_id:"source-1",cache_type:"umapin_table",path:"/saved/table.csv",label:"已登记汇总表",status:"available",available_for:["umapin"],chains:["TRB"],group_fields:["临床分组"],sample_count:6};
function deferred<T>(){let resolve!:(value:T)=>void;const promise=new Promise<T>(done=>{resolve=done;});return {promise,resolve};}
afterEach(()=>{cleanup();vi.restoreAllMocks();});
describe("继续分析入口读取与上下文",()=>{
 it("来源目录未记录样本数的零默认值不展示为真实零样本",async()=>{
  vi.spyOn(sources,"listPepCacheCandidates").mockResolvedValue({success:true,candidates:[{...candidate,sample_count:0}]});
  render(<ContinueAnalysis result={result}/>);
  await screen.findByRole("link",{name:"机器学习"});
  expect(screen.queryByText("样本：0")).not.toBeInTheDocument();
  expect(screen.getByText("分组字段：临床分组")).toBeInTheDocument();
 });
 it("加载状态明确且未读取完成不能使用旧入口",async()=>{
  const pending=deferred<{success:boolean;candidates:typeof candidate[]}>();
  vi.spyOn(sources,"listPepCacheCandidates").mockReturnValue(pending.promise);
  render(<ContinueAnalysis result={result}/>);
  expect(screen.getByText("正在读取本次分析的后续入口…")).toBeInTheDocument();
  expect(screen.getByRole("button",{name:"刷新可用结果"})).toBeDisabled();
  await act(async()=>pending.resolve({success:true,candidates:[candidate]}));
  expect(await screen.findByRole("link",{name:"UMAP 特征降维"})).toBeInTheDocument();
 });
 it("主动刷新读取新来源且刷新期间移除旧链接",async()=>{
  const pending=deferred<{success:boolean;candidates:typeof candidate[]}>();
  const list=vi.spyOn(sources,"listPepCacheCandidates").mockResolvedValueOnce({success:true,candidates:[candidate]}).mockReturnValueOnce(pending.promise);
  render(<ContinueAnalysis result={result}/>);
  await screen.findByRole("link",{name:"UMAP 特征降维"});
  fireEvent.click(screen.getByRole("button",{name:"刷新可用结果"}));
  expect(screen.queryByRole("link",{name:"UMAP 特征降维"})).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"刷新可用结果"})).toBeDisabled();
  const next={...candidate,id:"next",artifact_id:"source-1:table:新的路径",label:"刷新后的汇总表"};
  await act(async()=>pending.resolve({success:true,candidates:[next]}));
  const url=new URL((await screen.findByRole("link",{name:"UMAP 特征降维"})).getAttribute("href")!,"http://local");
  expect(url.searchParams.get("upstream_artifact")).toBe(next.artifact_id);
  expect(list).toHaveBeenLastCalledWith("项目 01",undefined,"数据集 02",{deduplicate:false});
 });
 it("错误与无来源分开提示，重读不启动计算",async()=>{
  const list=vi.spyOn(sources,"listPepCacheCandidates").mockRejectedValueOnce(new Error("合成网络中断")).mockResolvedValueOnce({success:true,candidates:[candidate]});
  render(<ContinueAnalysis result={result}/>);
  expect(await screen.findByRole("alert")).toHaveTextContent("后续分析入口暂时读取失败");
  expect(screen.queryByText("本次结果暂无可直接继续的分析入口。")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"重新读取"}));
  expect(await screen.findByRole("link",{name:"机器学习"})).toBeInTheDocument();
  expect(list).toHaveBeenCalledTimes(2);
 });
 it("没有本任务可用后续产物时显示空状态及保留上下文的分析中心",async()=>{
  vi.spyOn(sources,"listPepCacheCandidates").mockResolvedValue({success:true,candidates:[{...candidate,job_id:"other"},{...candidate,id:"unavailable",artifact_id:"source-1:missing",status:"unavailable"},{...candidate,id:"usage",artifact_id:"source-1:usage",cache_type:"usage"}]});
  render(<ContinueAnalysis result={result}/>);
  expect(await screen.findByText("本次结果暂无可直接继续的分析入口。")).toBeInTheDocument();
  const link=screen.getByRole("link",{name:"前往分析中心"});
  const url=new URL(link.getAttribute("href")!,"http://local");
  expect(url.pathname).toBe("/analysis/center");expect(url.searchParams.get("project")).toBe("项目 01");
  expect(url.searchParams.get("asset_set")).toBe("数据集 02");
  expect(screen.queryByRole("link",{name:"机器学习"})).not.toBeInTheDocument();
 });
 it("更换任务后不保留旧产物，新请求按新范围生成链接",async()=>{
  const pending=deferred<{success:boolean;candidates:typeof candidate[]}>();
  vi.spyOn(sources,"listPepCacheCandidates").mockResolvedValueOnce({success:true,candidates:[candidate]}).mockReturnValueOnce(pending.promise);
  const view=render(<ContinueAnalysis result={result}/>);
  await screen.findByRole("link",{name:"机器学习"});
  view.rerender(<ContinueAnalysis result={{...result,job:{...result.job,id:"source-2",project_id:"另一项目",payload:{asset_set:"另一数据集"}}}}/>);
  expect(screen.queryByRole("link",{name:"机器学习"})).not.toBeInTheDocument();
  expect(screen.getByText("正在读取本次分析的后续入口…")).toBeInTheDocument();
  await act(async()=>pending.resolve({success:true,candidates:[{...candidate,job_id:"source-2",artifact_id:"source-2:表"}]}));
  const url=new URL((await screen.findByRole("link",{name:"机器学习"})).getAttribute("href")!,"http://local");
  expect(url.searchParams.get("project")).toBe("另一项目");expect(url.searchParams.get("asset_set")).toBe("另一数据集");
 });
 it("差异来源刷新沿用本任务过滤且主动请求不合并",async()=>{
  const get=vi.spyOn(apiClient,"get").mockResolvedValueOnce({candidates:[{id:"source-1:deg",job_id:"source-1",status:"available"}]})
   .mockResolvedValueOnce({candidates:[{id:"other:deg",job_id:"other",status:"available"}]});
  render(<ContinueAnalysis result={{...result,job:{...result.job,module:"volcano"}}}/>);
  await screen.findByRole("link",{name:"GO / KEGG 富集"});
  fireEvent.click(screen.getByRole("button",{name:"刷新可用结果"}));
  await screen.findByText("本次结果暂无可直接继续的分析入口。");
  expect(get).toHaveBeenLastCalledWith("/api/script-hub/go-kegg-enrichment/sources",{project_id:"项目 01",asset_set:"数据集 02"},{skipCache:true,deduplicate:false});
 });
 it("来源卡片显示实际条件，来源任务单独打开且不改写候选",async()=>{
  const original=structuredClone(candidate);
  vi.spyOn(sources,"listPepCacheCandidates").mockResolvedValue({success:true,candidates:[candidate]});
  render(<ContinueAnalysis result={result}/>);
  await screen.findByRole("link",{name:"机器学习"});
  expect(screen.getByText("样本：6")).toBeInTheDocument();expect(screen.getByText("分组字段：临床分组")).toBeInTheDocument();
  const source=screen.getByRole("link",{name:"查看来源任务 source-1"});
  const url=new URL(source.getAttribute("href")!,"http://local");
  expect(url.searchParams.get("job")).toBe("source-1");expect(url.searchParams.get("asset_set")).toBe("数据集 02");
  expect(source).toHaveAttribute("target","_blank");expect(candidate).toEqual(original);
 });
});
