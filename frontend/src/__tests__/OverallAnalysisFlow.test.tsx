import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,within} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {AssetTable} from "../features/assets/AssetTable";
import {ContinueAnalysis} from "../features/results/ContinueAnalysis";
import {AnalysisResultSummary} from "../features/results/AnalysisResultSummary";
import {JobProgressPanel} from "../features/jobs/JobProgressPanel";
import {apiClient} from "../shared/api/client";
import * as sources from "../shared/api/scriptHub";
import type {JobResultsResponse} from "../shared/api/jobs";

afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});
const result={success:true,status:"completed",job:{id:"source-1",module:"pep-analysis",project_id:"项目 01",payload:{asset_set:"数据 02"}},outputs:[],assets:[],result:{}} as unknown as JobResultsResponse;

it("待映射文件可以携带具体版本和返回位置处理，不重复上传",async()=>{
 vi.spyOn(apiClient,"get").mockResolvedValue({columns:[],rows:[],files:[],pagination:{page:1,page_size:20,total:0,total_pages:0}});
 render(<MemoryRouter><AssetTable projectId="项目 01" loading={false} assets={[{id:"asset-001",project_id:"项目 01",asset_type:"profile",original_name:"待映射.csv",storage_path:"/isolated/a.csv",size:1,metadata:{asset_set:"数据 02",validation:{status:"needs_mapping"}}}]}/></MemoryRouter>);
 fireEvent.click(screen.getByRole("button",{name:"查看 待映射.csv"}));
 const dialog=within(screen.getByRole("dialog",{name:"文件详情与校验"}));
 expect(dialog.getByText("下一步：确认列与样本映射")).toBeVisible();
 const url=new URL(dialog.getByRole("link",{name:"确认列与样本映射"}).getAttribute("href")!,"http://local");
 expect(url.searchParams.get("project")).toBe("项目 01");expect(url.searchParams.get("asset_set")).toBe("数据 02");expect(url.searchParams.get("input_asset")).toBe("asset-001");
 expect(new URL(url.searchParams.get("return_to")!,"http://local").searchParams.get("asset")).toBe("asset-001");
});

it("续接说明区分本任务不可用产物与不兼容产物，其他任务原因不会混入",async()=>{
 vi.spyOn(sources,"listPepCacheCandidates").mockResolvedValue({success:true,candidates:[
  {id:"missing",artifact_id:"source-1:missing",job_id:"source-1",cache_type:"vj_usage",path:"/isolated/missing",label:"缺失汇总表",status:"unavailable",reason:"结果文件已不存在，请重新运行来源分析。"},
  {id:"incompatible",artifact_id:"source-1:usage",job_id:"source-1",cache_type:"usage",path:"/isolated/usage",label:"原始使用表",status:"available"},
  {id:"other",job_id:"another",cache_type:"usage",path:"",status:"unavailable",reason:"其他任务的错误"},
 ]});
 render(<ContinueAnalysis result={result}/>);
 fireEvent.click(await screen.findByText("需核对的本次产物（2）"));
 expect(screen.getByText("结果文件已不存在，请重新运行来源分析。")).toBeVisible();
 expect(screen.getByText("此类产物暂无兼容的后续分析入口，可下载或查看本次结果。")).toBeVisible();
 expect(screen.queryByText("其他任务的错误")).not.toBeInTheDocument();expect(screen.queryByRole("link",{name:"机器学习"})).not.toBeInTheDocument();
 const url=new URL(screen.getByRole("link",{name:"查看来源任务 source-1"}).getAttribute("href")!,"http://local");expect(url.searchParams.get("asset_set")).toBe("数据 02");
});

it("失败任务返回分析中心保留项目与数据集",()=>{
 render(<JobProgressPanel job={{...result.job,status:"failed"}}/>);
 const url=new URL(screen.getByRole("link",{name:"进入分析中心"}).getAttribute("href")!,"http://local");
 expect(url.searchParams.get("project")).toBe("项目 01");expect(url.searchParams.get("asset_set")).toBe("数据 02");
});

it("结果摘要沿用执行快照与比较方向，不推算排除数量，不把缺失记录当零",()=>{
 const saved={...result,job:{...result.job,payload:{asset_set:"数据 02",input_assets:[{asset_id:"old-001",asset_type:"profile",path:"/isolated/old.csv",content_version:"旧版本",asset_set:"数据 02"}]}},result:{metadata:{sample_count:4,selected_sample_count:6,unused_selected_samples:["001","002"],group_field:"临床分组",chains:["TRB"],comparison_sample_counts:[{group1:"病例",group2:"对照",group1_n:2,group2_n:2}],warnings:["只纳入指定比较的样本"]}}};
 const view=render(<AnalysisResultSummary result={saved}/>);
 expect(screen.getByText("4 个")).toBeVisible();expect(screen.getByText(/未参与本次比较的所选样本：001、002/)).toBeVisible();
 fireEvent.click(screen.getByText("比较方向与样本数量（1）"));expect(screen.getByText("病例 / 对照：前组 2，后组 2 个样本")).toBeVisible();
 fireEvent.click(screen.getByText("本次保存的输入版本（1）"));expect(screen.getByText("执行时版本：旧版本")).toBeVisible();
 const url=new URL(screen.getByRole("link",{name:"查看对应输入登记"}).getAttribute("href")!,"http://local");expect(url.searchParams.get("asset")).toBe("old-001");
 expect(screen.queryByText(/未匹配输入而排除/)).not.toBeInTheDocument();
 view.rerender(<AnalysisResultSummary result={result}/>);expect(screen.getByText("本任务未记录")).toBeVisible();expect(screen.queryByText("0 个")).not.toBeInTheDocument();
});
