import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { UnifiedAnalysis } from "../pages/analysis/UnifiedAnalysis";
import { AnalysisDataProvider, useAnalysisData } from "../features/analysis/AnalysisDataContext";
import { getProjectAsset, resolveProjectInputSelection } from "../shared/api/projects";
import { getAnalysisInputFile, listDataFiles } from "../shared/api/files";
import { submitJob } from "../shared/api/jobs";
vi.mock("../shared/api/projects",()=>({listProjects:vi.fn().mockResolvedValue({projects:[{id:"p1",name:"项目甲"}]}),getProjectAsset:vi.fn(),resolveProjectInputSelection:vi.fn(),INPUT_RESOLUTION_BATCH_SIZE:500}));
vi.mock("../shared/api/files",()=>({listDataFiles:vi.fn(),getAnalysisInputFile:vi.fn()}));
vi.mock("../shared/api/jobs",()=>({submitJob:vi.fn().mockResolvedValue({success:true,job_id:"job-one"})}));
vi.mock("../shared/hooks/useJobResult",()=>({useJobResult:()=>({jobId:null,status:"unknown",result:null,error:null})}));
vi.mock("../shared/api/unified",async()=>{
 const actual=await vi.importActual<any>("../shared/api/unified");
 const scheme={id:"test",description:"合成方案",required_fields:[{field:"sample",display_name:"样本"},{field:"metric",display_name:"指标",mapping_hints:["mapped_metric"]}]};
 return {...actual,listAnalysisSchemes:vi.fn().mockResolvedValue({schemes:[scheme]}),getAnalysisScheme:vi.fn().mockResolvedValue(scheme)};
});
const asset=(id:string)=>({id,project_id:"p1",asset_type:"profile",original_name:id==="old"?"旧指标.csv":"当前指标.csv",storage_path:`/inputs/${id}.csv`,metadata:{asset_set:"甲",superseded:id==="old",content_version:id}} as any);
function Location(){const location=useLocation();return <output data-testid="location">{location.search}</output>;}
function mount(){render(<MemoryRouter initialEntries={["/analysis/tools/shm?project=p1&asset_set=甲&input_asset=old&return_to=%2Fmanagement%2Fprojects%2Fp1%3Ffile_page%3D3"]}><AnalysisDataProvider><UnifiedAnalysis fixedScheme="test"/><Location/></AnalysisDataProvider></MemoryRouter>);}
beforeEach(()=>{
 sessionStorage.clear();vi.clearAllMocks();
 vi.mocked(getProjectAsset).mockImplementation(async(_p,id)=>({asset:asset(id)}));
 vi.mocked(resolveProjectInputSelection).mockImplementation(async(_p,scope,ids)=>({asset_set:scope,assets:ids.map(id=>id.startsWith("clone")?{...asset(id),asset_type:"pep"}:asset(id))}));
 vi.mocked(getAnalysisInputFile).mockImplementation(async(_p,id)=>({id,name:asset(id).original_name,asset_id:id,asset_set:"甲",row_count:2,columns:["sample","mapped_metric"]}));
 vi.mocked(listDataFiles).mockResolvedValue({files:[{id:"current",asset_id:"current",asset_set:"甲",name:"当前指标.csv",row_count:2,columns:["stale_catalog"]}]});
});
afterEach(cleanup);
describe("方案分析使用明确来源的实际表头",()=>{
 it("页外历史版本读取整理后的表头，提交保留来源和返回地址",async()=>{
  mount();await screen.findByText(/旧指标.csv · 2 行 · 2 列/);
  expect(getAnalysisInputFile).toHaveBeenCalledWith("p1","old","甲");
  expect(listDataFiles).toHaveBeenCalledWith("p1","甲");
  expect(screen.getByRole("link",{name:"返回来源文件"})).toHaveAttribute("href","/management/projects/p1?file_page=3");
  fireEvent.click(screen.getByRole("button",{name:"开始分析"}));
  await waitFor(()=>expect(submitJob).toHaveBeenCalledWith(expect.objectContaining({projectId:"p1",payload:expect.objectContaining({file_id:"old",asset_set:"甲",field_mapping:{sample:"sample",metric:"mapped_metric"}})})));
  await waitFor(()=>expect(screen.getByTestId("location")).toHaveTextContent("job=job-one"));
  expect(screen.getByTestId("location")).toHaveTextContent("input_asset=old");
 });
 it("手动选择另一资产重新读实际表头，不采用列表里的过期列",async()=>{
  mount();await screen.findByText(/旧指标.csv · 2 行 · 2 列/);
  fireEvent.change(screen.getByRole("combobox",{name:"选择本项目已上传文件"}),{target:{value:"current"}});
  await screen.findByText(/当前指标.csv · 2 行 · 2 列/);
  expect(getAnalysisInputFile).toHaveBeenCalledWith("p1","current","甲");
  expect(screen.getByTestId("location")).toHaveTextContent("input_asset=current");
  expect(screen.queryByRole("option",{name:"stale_catalog"})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"开始分析"}));
  await waitFor(()=>expect(submitJob).toHaveBeenCalledWith(expect.objectContaining({payload:expect.objectContaining({file_id:"current"})})));
 });
 it("跨数据集入口不能读取表头或提交，重新选择后清除入口意图",async()=>{
  vi.mocked(getProjectAsset).mockResolvedValue({asset:{...asset("old"),metadata:{asset_set:"乙"}}});
  mount();await screen.findByText("所选文件不属于当前数据集，请重新选择。");
  expect(getAnalysisInputFile).not.toHaveBeenCalled();
  expect(screen.getByRole("button",{name:"开始分析"})).toBeDisabled();
  expect(submitJob).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"重新选择文件"}));
  expect(screen.getByTestId("location").textContent).not.toContain("input_asset");
 });
});


function SharedSelection(){const {data}=useAnalysisData();return <output data-testid="shared-selection">{JSON.stringify(data)}</output>;}
function continueFromClone(){
 sessionStorage.setItem("analysis-selection",JSON.stringify({projectId:"p1",assetSetName:"甲",inputs:{pep:["clone-a","clone-b"],profile:"old",transcriptome:"",deconvolution:""}}));
 vi.mocked(getProjectAsset).mockImplementation(async (_p,id)=>({asset:id.startsWith("clone")?{...asset(id),asset_type:"pep"}:asset(id)}));
 render(<MemoryRouter initialEntries={["/analysis/tools/shm?project=p1&asset_set=甲&input_asset=clone-b&reuse_inputs=1"]}><AnalysisDataProvider><UnifiedAnalysis fixedScheme="test"/><Location/><SharedSelection/></AnalysisDataProvider></MemoryRouter>);
}
it("指标工具续用完整选择中的历史指标，不把最后点击的克隆当作数据表",async()=>{
 continueFromClone();await screen.findByText(/旧指标.csv · 2 行 · 2 列/);
 expect(getAnalysisInputFile).toHaveBeenCalledWith("p1","old","甲");
 expect(vi.mocked(getAnalysisInputFile).mock.calls.every(call=>call[1]!=="clone-b")).toBe(true);
 expect(screen.getByTestId("location")).toHaveTextContent("input_asset=old");
 fireEvent.click(screen.getByRole("button",{name:"开始分析"}));
 await waitFor(()=>expect(submitJob).toHaveBeenCalledWith(expect.objectContaining({payload:expect.objectContaining({file_id:"old"})})));
 expect(JSON.parse(screen.getByTestId("shared-selection").textContent!).pepPaths).toEqual(["/inputs/clone-a.csv","/inputs/clone-b.csv"]);
});
it("方案工具手动换指标表同步完整选择，返回其他工具时仍保留两份克隆",async()=>{
 continueFromClone();await screen.findByText(/旧指标.csv · 2 行 · 2 列/);
 fireEvent.change(screen.getByRole("combobox",{name:"选择本项目已上传文件"}),{target:{value:"current"}});
 await screen.findByText(/当前指标.csv · 2 行 · 2 列/);
 await waitFor(()=>expect(JSON.parse(screen.getByTestId("shared-selection").textContent!)).toMatchObject({profilePath:"/inputs/current.csv",pepPaths:["/inputs/clone-a.csv","/inputs/clone-b.csv"]}));
 expect(JSON.parse(sessionStorage.getItem("analysis-selection")!).inputs).toMatchObject({pep:["clone-a","clone-b"],profile:"current"});
});

it("方案工具重新选择文件会清空本次指标选择，不自动选回旧表，保留其他输入",async()=>{
 continueFromClone();await screen.findByText(/旧指标.csv · 2 行 · 2 列/);
 fireEvent.click(screen.getByRole("button",{name:"重新选择文件"}));
 await waitFor(()=>expect(screen.getByRole("combobox",{name:"选择本项目已上传文件"})).toHaveValue(""));
 expect(screen.getByRole("button",{name:"开始分析"})).toBeDisabled();
 expect(JSON.parse(screen.getByTestId("shared-selection").textContent!)).toMatchObject({profilePath:"",pepPaths:["/inputs/clone-a.csv","/inputs/clone-b.csv"]});
 expect(screen.getByTestId("location").textContent).not.toContain("input_asset");
});
