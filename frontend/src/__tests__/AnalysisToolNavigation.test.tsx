import {afterEach,describe,expect,it,vi} from "vitest";
import {cleanup,render,screen} from "@testing-library/react";
import {MemoryRouter,Route,Routes} from "react-router-dom";
import {AnalysisToolPage} from "../pages/analysis/AnalysisToolPage";
vi.mock("../pages/analysis/ScriptHubWizard",()=>({ScriptHubWizard:()=><p>工具配置</p>}));
vi.mock("../pages/analysis/UnifiedAnalysis",()=>({UnifiedAnalysis:()=><p>方案配置</p>}));
afterEach(cleanup);
function page(path:string){return render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/analysis/tools/:toolId" element={<AnalysisToolPage/>}/></Routes></MemoryRouter>);}
describe("前置分析导航",()=>{
 it.each(["umapin","vj-difference"])("%s 的前置分析保留项目数据集且在新标签打开",tool=>{
  page("/analysis/tools/"+tool+"?project="+encodeURIComponent("项目 01")+"&asset_set="+encodeURIComponent("数据集 02")+"&upstream_artifact=existing");
  const prerequisite=screen.getByRole("link",{name:"进入 CDR3 共享分析"});
  const url=new URL(prerequisite.getAttribute("href")!,"http://local");
  expect(url.pathname).toBe("/analysis/tools/sharing");expect(url.searchParams.get("project")).toBe("项目 01");
  expect(url.searchParams.get("asset_set")).toBe("数据集 02");expect(url.searchParams.has("upstream_artifact")).toBe(false);
  expect(prerequisite).toHaveAttribute("target","_blank");expect(prerequisite).toHaveAttribute("rel","noreferrer");
  const center=new URL(screen.getByRole("link",{name:/^返回/}).getAttribute("href")!,"http://local");
  expect(center.pathname).toBe("/analysis/center");expect(center.searchParams.get("asset_set")).toBe("数据集 02");
 });
 it("未指定项目时保留分类且不编造项目数据集",()=>{
  page("/analysis/tools/profile");
  const url=new URL(screen.getByRole("link",{name:/^返回/}).getAttribute("href")!,"http://local");
  expect(url.searchParams.get("category")).toBe("overview");expect(url.searchParams.has("project")).toBe(false);
  expect(url.searchParams.has("asset_set")).toBe(false);
 });
});


it("准备入口可返回原项目筛选，拒绝其他项目和外站返回地址",()=>{
 const origin="/management/projects/p1?tab=assets&asset_set=甲&prepare_tool=profile&file_page=3";
 page("/analysis/tools/profile?project=p1&return_to="+encodeURIComponent(origin));
 expect(screen.getByRole("link",{name:"返回数据准备"})).toHaveAttribute("href",new URL(origin,"http://localhost").pathname+new URL(origin,"http://localhost").search);
 cleanup();page("/analysis/tools/profile?project=p1&return_to="+encodeURIComponent("/management/projects/p2?tab=assets"));
 expect(screen.queryByRole("link",{name:"返回数据准备"})).not.toBeInTheDocument();
 cleanup();page("/analysis/tools/profile?project=p1&return_to="+encodeURIComponent("https://elsewhere.example/management/projects/p1"));
 expect(screen.queryByRole("link",{name:"返回数据准备"})).not.toBeInTheDocument();
});
