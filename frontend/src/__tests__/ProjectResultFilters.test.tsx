import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {createMemoryRouter,RouterProvider} from "react-router-dom";
import {ProjectResultFilters} from "../features/results/ProjectResultFilters";
import {ProjectDetail} from "../pages/management/ProjectDetail";
import * as projects from "../shared/api/projects";
import {analysisLabel} from "../shared/utils/analysisLabels";
import {apiClient} from "../shared/api/client";
const facets={datasets:[{name:"甲",count:3},{name:"乙",count:3}],analysis_types:[{name:"profile",count:6},{name:"vj",count:2}],unscoped_count:2};
afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});
function mount(element:React.ReactNode,url:string,path="*"){const router=createMemoryRouter([{path,element}],{initialEntries:[url]});render(<RouterProvider router={router}/>);return router;}
it("结果筛选立即限定服务端范围并重置页码，保留项目数据页面的范围",async()=>{
 const router=mount(<ProjectResultFilters facets={facets}/>,"/management/projects/p?tab=results&asset_set=原输入&result_page=5");
 fireEvent.click(screen.getByRole("button",{name:"结果数据集"}));fireEvent.click(screen.getByRole("option",{name:"甲（3）"}));
 await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("result_dataset")).toBe("甲"));
 expect(new URLSearchParams(router.state.location.search).has("result_page")).toBe(false);
 fireEvent.click(screen.getByRole("button",{name:"结果分析类型"}));fireEvent.click(screen.getByRole("option",{name:analysisLabel("profile")+"（6）"}));
 fireEvent.change(screen.getByRole("textbox",{name:"来源任务标识"}),{target:{value:"job-1"}});
 expect(new URLSearchParams(router.state.location.search).has("result_job")).toBe(false);
 expect(screen.getByRole("status")).toHaveTextContent("任务标识尚未应用");
 fireEvent.submit(screen.getByRole("textbox",{name:"来源任务标识"}).closest("form")!);
 await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("result_job")).toBe("job-1"));
 fireEvent.click(screen.getByRole("button",{name:"清除结果筛选"}));
 expect(new URLSearchParams(router.state.location.search).get("asset_set")).toBe("原输入");
 expect(new URLSearchParams(router.state.location.search).get("tab")).toBe("results");
 expect(new URLSearchParams(router.state.location.search).has("result_type")).toBe(false);
});
it("未记录数据集使用独立条件，当前页没有该数据集时保留已选筛选",async()=>{
 const router=mount(<ProjectResultFilters facets={facets}/>,"/management/projects/p?tab=results&result_dataset=历史数据集");
 expect(screen.getByRole("button",{name:"结果数据集"})).toHaveTextContent("历史数据集");
 fireEvent.click(screen.getByRole("button",{name:"结果数据集"}));fireEvent.click(screen.getByRole("option",{name:"未记录数据集（2）"}));
 await waitFor(()=>expect(new URLSearchParams(router.state.location.search).get("result_unscoped")).toBe("1"));
 expect(new URLSearchParams(router.state.location.search).has("result_dataset")).toBe(false);
});
it("项目页将筛选交给结果接口，空筛选结果与未运行区分",async()=>{
 vi.spyOn(projects,"getProject").mockResolvedValue({id:"p",name:"项目",asset_counts:{},group_specs:[]} as never);
 const list=vi.spyOn(projects,"listProjectResults").mockResolvedValue({success:true,results:[],pagination:{page:1,page_size:10,total:0,total_pages:0},facets});
 mount(<ProjectDetail/>,"/management/projects/p?tab=results&result_dataset=乙&result_type=profile&result_job=job-8","/management/projects/:projectId");
 await screen.findByText("没有符合当前筛选的分析结果，请调整筛选。");
 expect(list).toHaveBeenCalledWith("p",expect.objectContaining({assetSet:"乙",analysisType:"profile",jobId:"job-8",unscoped:false}));
 expect(screen.queryByText("尚未生成分析结果。")).not.toBeInTheDocument();
});
