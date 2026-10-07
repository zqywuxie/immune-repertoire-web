import {afterEach,expect,it,vi} from "vitest";
import {cleanup,fireEvent,render,screen,waitFor} from "@testing-library/react";
import {MemoryRouter,useLocation} from "react-router-dom";
import {ProjectDataScope} from "../features/projects/ProjectDataScope";
import * as projects from "../shared/api/projects";
afterEach(()=>{cleanup();vi.restoreAllMocks();});
function Location(){return <output aria-label="当前地址">{useLocation().search}</output>;}
const datasets={datasets:[{name:"甲",input_count:2,kinds:{}},{name:"乙",input_count:3,kinds:{}}]};
it("样本与分组就地切范围，保留查询和标签且清除旧页码与详情",async()=>{
 vi.spyOn(projects,"listProjectDatasets").mockResolvedValue(datasets);
 render(<MemoryRouter initialEntries={["/management/projects/p?tab=samples&sample_q=001&sample_page=5&file_page=2&asset=old&group_spec=old"]}><ProjectDataScope projectId="p" revision={0}/><Location/></MemoryRouter>);
 await waitFor(()=>expect(screen.getByRole("button",{name:"切换当前数据集"})).toBeEnabled());
 fireEvent.click(screen.getByRole("button",{name:"切换当前数据集"}));fireEvent.click(screen.getByRole("option",{name:"乙"}));
 const params=new URLSearchParams(screen.getByLabelText("当前地址").textContent!);
 expect(params.get("asset_set")).toBe("乙");expect(params.get("tab")).toBe("samples");expect(params.get("sample_q")).toBe("001");
 for(const key of ["sample_page","file_page","asset","group_spec"])expect(params.has(key)).toBe(false);
 expect(screen.getByText("3 个当前输入文件")).toBeVisible();
});
it("范围读取失败保持原数据集，重试不将未知数量显示成零",async()=>{
 vi.spyOn(projects,"listProjectDatasets").mockRejectedValueOnce(new Error("范围断连")).mockResolvedValue(datasets);
 render(<MemoryRouter initialEntries={["/management/projects/p?tab=group-specs&asset_set=乙"]}><ProjectDataScope projectId="p" revision={0}/><Location/></MemoryRouter>);
 await screen.findByRole("button",{name:"重新读取数据范围"});
 expect(screen.getByRole("button",{name:"切换当前数据集"})).toBeDisabled();expect(screen.getByText("数据集数量暂未读取")).toBeVisible();
 expect(screen.getByRole("button",{name:"切换当前数据集"})).toHaveTextContent("乙");
 fireEvent.click(screen.getByRole("button",{name:"重新读取数据范围"}));await screen.findByText("3 个当前输入文件");
 expect(screen.getByRole("button",{name:"切换当前数据集"})).toBeEnabled();
});
