import { useEffect, useState } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Stage1DataIntake } from "../features/scripthub/stages/Stage1DataIntake";
import { ProjectDatasetSummary } from "../features/projects/ProjectDatasetSummary";
import { AnalysisDataProvider, useAnalysisData, type AnalysisData } from "../features/analysis/AnalysisDataContext";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
import type { ProjectAsset } from "../shared/types/domain";

const asset = (id:string, type:string, status="valid", history=false) => ({id,project_id:"p",asset_type:type,original_name:`${id}.csv`,storage_path:`/inputs/${id}.csv`,size:10,uploaded_at:"2026-10-05T09:00:00",metadata:{asset_set:"甲",validation:{status},superseded:history}} as ProjectAsset);
const a=asset("克隆甲","pep"), b=asset("克隆乙旧版","pep","valid",true), unselected=asset("未选失败文件","pep","failed");
const profile=asset("指标甲","profile"), alternate=asset("指标乙","profile");
const initial:AnalysisData={projectId:"p",assetSetName:"甲",pepPaths:[a.storage_path!],profilePath:profile.storage_path!,transcriptomePath:"",deconvolutionPath:""};
beforeEach(()=>{
 sessionStorage.clear();
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[{name:"甲",input_count:3,kinds:{pep:{count:2,statuses:{valid:2},sample_min:null,sample_max:null},profile:{count:1,statuses:{valid:1},sample_min:null,sample_max:null}}}]});
 vi.spyOn(projects,"getProjectInputSelection").mockResolvedValue({asset_set:"甲",assets:[a,profile],totals:{pep:1,profile:1},truncated_kinds:[]});
 vi.spyOn(projects,"listProjects").mockResolvedValue({projects:[{id:"p",name:"项目"}] as any,pagination:{page:1,page_size:20,total:1,total_pages:1}});
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"项目"} as any);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();sessionStorage.clear();});

it("通过真实文件浏览器追加历史克隆文件，保留已有克隆和指标表",async()=>{
 vi.spyOn(projects,"listProjectAssets").mockImplementation(async (_project, options={})=>({assets:options.includeSuperseded?[b]:[a,profile]}));
 function Selection(){
  const [data,setData]=useState(initial);const [requested,setRequested]=useState<ProjectAsset>(a);
  return <><Stage1DataIntake {...data} requestedAsset={requested} onUpdate={(next,chosen)=>{setData(next);if(chosen)setRequested(chosen);}}/><output aria-label="实际选择">{JSON.stringify(data)}</output></>;
 }
 render(<MemoryRouter><Selection/></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:/浏览当前数据集文件/}));
 fireEvent.click(await screen.findByRole("checkbox",{name:"显示历史版本"}));
 fireEvent.click(await screen.findByRole("button",{name:/克隆乙旧版.csv.*历史版本/}));
 await waitFor(()=>expect(JSON.parse(screen.getByLabelText("实际选择").textContent!)).toMatchObject({...initial,pepPaths:[a.storage_path,b.storage_path]}));
});

function SummarySelection({requested}:{requested?:ProjectAsset}){
 const {data,setData}=useAnalysisData();const location=useLocation();
 useEffect(()=>{setData(initial);},[]);
 return <>{data && <ProjectDatasetSummary projectId="p" revision={0} requestedAsset={requested}/>}<output aria-label="实际选择">{JSON.stringify(data)}</output><output aria-label="当前地址">{location.search}</output></>;
}
it("摘要只显示本次选中的克隆文件，未选失败文件不污染状态",async()=>{
 vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[a,unselected,profile]});
 vi.mocked(projects.getProjectInputSelection).mockResolvedValue({asset_set:"甲",assets:[a,unselected,profile],totals:{pep:2,profile:1},truncated_kinds:[]});
 render(<MemoryRouter initialEntries={["/?project=p&asset_set=甲"]}><AnalysisDataProvider><SummarySelection/></AnalysisDataProvider></MemoryRouter>);
 const heading=await screen.findByRole("heading",{name:"克隆序列表"});const card=heading.closest("article")!;
 await waitFor(()=>expect(within(card).getByText("克隆甲.csv")).toBeVisible());
 expect(within(card).getByText("校验通过")).toBeVisible();
 expect(within(card).queryByText("2 个输入文件")).not.toBeInTheDocument();
});
it("手动切换指标表版本更新资产身份，明确显示校验失败",async()=>{
 const failed={...alternate,metadata:{asset_set:"甲",validation:{status:"failed"}}};
 vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[a,profile,failed]});
 vi.mocked(projects.getProjectInputSelection).mockResolvedValue({asset_set:"甲",assets:[a,profile,failed],totals:{pep:1,profile:2},truncated_kinds:[]});
 render(<MemoryRouter initialEntries={["/?project=p&asset_set=甲&input_asset=指标甲"]}><AnalysisDataProvider><SummarySelection requested={profile}/></AnalysisDataProvider></MemoryRouter>);
 fireEvent.click(await screen.findByRole("button",{name:"样本指标表版本"}));
 fireEvent.click(screen.getByRole("option",{name:/指标乙.csv/}));
 await waitFor(()=>expect(new URLSearchParams(screen.getByLabelText("当前地址").textContent!).get("input_asset")).toBe(failed.id));
 expect(JSON.parse(screen.getByLabelText("实际选择").textContent!).profilePath).toBe(failed.storage_path);
 expect(within(screen.getByRole("heading",{name:"样本指标表"}).closest("article")!).getByText("校验失败，请重试")).toBeVisible();
});
