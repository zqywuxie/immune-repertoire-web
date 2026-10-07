import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { JobResultPanel } from "../features/jobs/JobResultPanel";
import { BatchResultPanel } from "../features/jobs/BatchResultPanel";
import * as jobs from "../shared/api/jobs";
import type { JobResultsResponse } from "../shared/api/jobs";

const result = {
  success: true, status: "completed", job: { id: "address-job", module: "volcano", status: "completed" },
  outputs: [
    { kind: "png", label: "TRA_01_vs_02_volcano.png", url: "/plots/TRA_01_vs_02_volcano.png" },
    { kind: "png", label: "TRB_01_vs_02_volcano.png", url: "/plots/TRB_01_vs_02_volcano.png" },
    { kind: "png", label: "TRB_01_vs_03_volcano 中文.png", url: "/plots/TRB_01_vs_03_volcano%20中文.png" },
  ], assets: [], result: { comparisons: [{group1:"01",group2:"02"},{group1:"01",group2:"03"}] },
} as unknown as JobResultsResponse;
const outputKey = "volcano:png:/plots/TRB_01_vs_03_volcano%20中文.png:";
function Location() {
  const location = useLocation(), navigate = useNavigate();
  return <><output aria-label="结果地址">{location.pathname + location.search + location.hash}</output>
    <button onClick={() => navigate(-1)}>返回上个地址</button></>;
}
function view(address: string) {
  return <MemoryRouter initialEntries={[address]}><JobResultPanel result={result} loading={false}/><Location/></MemoryRouter>;
}
afterEach(() => { cleanup(); sessionStorage.clear(); vi.restoreAllMocks(); });

it("外部结果地址优先恢复实际图表和比较，不依赖旧浏览器会话", () => {
  sessionStorage.setItem("analysis-result-selection:address-job", JSON.stringify({module:"volcano",output:"volcano:png:/plots/TRA_01_vs_02_volcano.png:",section:"figures"}));
  const params = new URLSearchParams({job:"address-job",result_job:"address-job",result_module:"volcano",result_section:"figures",result_output:outputKey,result_chain:"TRB",result_comparison:JSON.stringify(["01","03"])});
  render(view("/analysis/script-hub/jobs?"+params));
  expect(screen.getByRole("img")).toHaveAttribute("src",result.outputs[2].url);
  expect(screen.getByLabelText("受体链")).toHaveValue("TRB");
  expect(screen.getByLabelText("组间比较")).toHaveValue(JSON.stringify(["01","03"]));
  expect(screen.getByText("找到 1 个结果，共 3 个")).toBeInTheDocument();
});

it("图表和筛选写入地址，保持项目及列表位置，清空会话后可重新打开", () => {
  const initial="/analysis/script-hub/jobs?job=address-job&project=project-a&asset_set=甲&status=completed&offset=50&q=病例#results";
  const first=render(view(initial));
  fireEvent.change(screen.getByLabelText("受体链"),{target:{value:"TRB"}});
  fireEvent.change(screen.getByLabelText("组间比较"),{target:{value:JSON.stringify(["01","03"])}});
  fireEvent.click(screen.getByRole("button",{name:/TRB_01_vs_03/}));
  const address=screen.getByLabelText("结果地址").textContent!;
  const url=new URL(address,"http://localhost");
  expect(url.searchParams.get("result_output")).toBe(outputKey);
  expect(url.searchParams.get("result_chain")).toBe("TRB");
  expect(url.searchParams.get("result_comparison")).toBe(JSON.stringify(["01","03"]));
  expect(url.searchParams.get("project")).toBe("project-a");
  expect(url.searchParams.get("asset_set")).toBe("甲");
  expect(url.searchParams.get("offset")).toBe("50");
  expect(url.searchParams.get("q")).toBe("病例");
  expect(url.hash).toBe("#results");
  first.unmount(); sessionStorage.clear();
  render(view(address));
  expect(screen.getByRole("img")).toHaveAttribute("src",result.outputs[2].url);
  expect(screen.getByLabelText("组间比较")).toHaveValue(JSON.stringify(["01","03"]));
});

it("过期或其他任务的文件引用只回退到本任务实际结果", () => {
  const params=new URLSearchParams({job:"address-job",result_job:"address-job",result_module:"removed",result_output:"https://unrelated.invalid/file.png",result_section:"removed",result_chain:"gone",result_comparison:"gone"});
  render(view("/analysis/script-hub/jobs?"+params));
  expect(screen.getByRole("img")).toHaveAttribute("src",result.outputs[0].url);
  expect(screen.getByLabelText("受体链")).toHaveValue("");
  expect(screen.getByLabelText("组间比较")).toHaveValue("");
  expect(screen.queryByRole("img",{name:/unrelated/})).not.toBeInTheDocument();
});

it("批次恢复指定子结果，仅允许读取当前计划内编号", async () => {
  const batch={...result,job:{id:"batch",module:"analysis-batch",status:"completed",payload:{items:[{module:"profile",status:"completed",job_id:"first"},{module:"volcano",status:"completed",job_id:"second"}]}}} as unknown as JobResultsResponse;
  const get=vi.spyOn(jobs,"getJob").mockImplementation(async id=>({success:true,job:{id,module:"profile",status:"completed"}}) as Awaited<ReturnType<typeof jobs.getJob>>);
  const results=vi.spyOn(jobs,"getJobResults").mockImplementation(async id=>({...result,job:{...result.job,id}}));
  const snapshots={jobs:{},readErrors:{},retry:vi.fn()};
  const current=render(<BatchResultPanel result={batch} snapshots={snapshots as never} selectedJobId="second" renderResult={child=><p>恢复子结果：{child.job.id}</p>}/>);
  expect(await screen.findByText("恢复子结果：second")).toBeInTheDocument();
  expect(results).toHaveBeenCalledWith("second");
  current.rerender(<BatchResultPanel result={batch} snapshots={snapshots as never} selectedJobId="foreign" renderResult={child=><p>恢复子结果：{child.job.id}</p>}/>);
  expect(await screen.findByText("恢复子结果：first")).toBeInTheDocument();
  await waitFor(()=>expect(get.mock.calls.some(([id])=>id==="foreign")).toBe(false));
});

it("浏览器返回已有结果地址时恢复图表及筛选，不沿用较新的会话选择", async () => {
  const first=new URLSearchParams({job:"address-job",result_job:"address-job",result_module:"volcano",result_section:"figures",result_output:"volcano:png:/plots/TRA_01_vs_02_volcano.png:",result_chain:"TRA"});
  const second=new URLSearchParams({job:"address-job",result_job:"address-job",result_module:"volcano",result_section:"figures",result_output:outputKey,result_chain:"TRB",result_comparison:JSON.stringify(["01","03"])});
  render(<MemoryRouter initialEntries={["/analysis/script-hub/jobs?"+first,"/analysis/script-hub/jobs?"+second]} initialIndex={1}>
    <JobResultPanel result={result} loading={false}/><Location/></MemoryRouter>);
  expect(screen.getByRole("img")).toHaveAttribute("src",result.outputs[2].url);
  fireEvent.click(screen.getByRole("button",{name:"返回上个地址"}));
  await waitFor(()=>expect(screen.getByRole("img")).toHaveAttribute("src",result.outputs[0].url));
  expect(screen.getByLabelText("受体链")).toHaveValue("TRA");
  expect(screen.getByLabelText("组间比较")).toHaveValue("");
});
