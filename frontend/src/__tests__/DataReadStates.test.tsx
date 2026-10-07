import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ManagementDashboard } from "../pages/management/ManagementDashboard";
import { ProjectDetail } from "../pages/management/ProjectDetail";
import { SampleRegistry } from "../pages/management/SampleRegistry";
import { ProjectDatasetManager } from "../features/assets/ProjectDatasetManager";
import * as projects from "../shared/api/projects";
import * as jobs from "../shared/api/jobs";
import * as samples from "../shared/api/samples";
import { apiClient } from "../shared/api/client";
const project={id:"p",name:"重试项目",status:"active",asset_counts:{},input_sample_count:1,registered_sample_count:0,result_count:0};
const dataset={name:"甲",input_count:1,kinds:{profile:{count:1,statuses:{valid:1}}}};
const pagination={page:1,page_size:50,total:0,total_pages:0};
beforeEach(()=>{
  vi.spyOn(projects,"getProject").mockResolvedValue(project as never);
  vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[dataset]} as never);
  vi.spyOn(projects,"getProjectStatistics").mockResolvedValue({project_count:3,result_count:5} as never);
});
afterEach(()=>{cleanup();vi.restoreAllMocks();apiClient.invalidateCache();});
it("概览失败替代空数据，独立重试不重取其他区域",async()=>{
  const list=vi.spyOn(projects,"listProjects").mockRejectedValueOnce(new Error("项目断连")).mockResolvedValue({projects:[project],pagination:{...pagination,total:1,total_pages:1}});
  const tasks=vi.spyOn(jobs,"listJobs").mockRejectedValue(new Error("任务断连"));
  render(<MemoryRouter><ManagementDashboard/></MemoryRouter>);
  await screen.findByText("最近项目暂时无法读取");await screen.findByText("最近任务暂时无法读取");
  expect(screen.queryByText("还没有项目")).not.toBeInTheDocument();expect(screen.queryByText(/暂无任务。/)).not.toBeInTheDocument();
  expect(screen.getAllByRole("alert")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button",{name:"重新读取项目"}));
  await screen.findByText("重试项目");expect(list).toHaveBeenCalledTimes(2);expect(tasks).toHaveBeenCalledTimes(1);
});
it("文件请求失败不显示空表，原数据集与筛选在重试后保持",async()=>{
  const list=vi.spyOn(projects,"listProjectAssets").mockRejectedValueOnce(new Error("文件断连")).mockResolvedValue({assets:[],pagination});
  render(<MemoryRouter initialEntries={["/?asset_set=甲&file_q=指标"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);
  await screen.findByText("输入文件暂时无法读取");
  expect(screen.queryByText("当前筛选下没有文件，请调整筛选。")).not.toBeInTheDocument();
  expect(screen.queryByText(/尚未导入分析输入/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"重新读取文件"}));
  await screen.findByText("当前筛选下没有文件，请调整筛选。");
  expect(list).toHaveBeenLastCalledWith("p",expect.objectContaining({assetSet:"甲",search:"指标"}));
});
it("数据集摘要失败不显示零输入或未提供，保留原范围",async()=>{
  vi.mocked(projects.listProjectDatasets).mockRejectedValueOnce(new Error("概况断连")).mockResolvedValue({datasets:[dataset]} as never);
  vi.spyOn(projects,"listProjectAssets").mockResolvedValue({assets:[],pagination});
  render(<MemoryRouter initialEntries={["/?asset_set=甲"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()}/></MemoryRouter>);
  await screen.findByText("数据集概况暂时无法读取");
  expect(screen.queryByText("按分析需要添加")).not.toBeInTheDocument();
  expect(screen.getByRole("button",{name:"当前项目数据集"})).toHaveTextContent("甲");
  fireEvent.click(screen.getByRole("button",{name:"重新读取数据集"}));
  await waitFor(()=>expect(screen.getByRole("button",{name:"当前项目数据集"})).toBeEnabled());
  expect(screen.getByRole("button",{name:"当前项目数据集"})).toHaveTextContent("甲");
});
it("附件失败不提示没有附件，重试后才显示真实空态",async()=>{
  vi.spyOn(projects,"listProjectAssets").mockRejectedValueOnce(new Error("附件断连")).mockResolvedValue({assets:[],pagination});
  render(<MemoryRouter initialEntries={["/management/projects/p?tab=attachments"]}><Routes><Route path="/management/projects/:projectId" element={<ProjectDetail/>}/></Routes></MemoryRouter>);
  await screen.findByText("项目附件暂时无法读取");expect(screen.queryByText("尚未上传项目附件。")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"重新读取附件"}));await screen.findByText("尚未上传项目附件。");
});
it("登记失败只显示一次错误，数量不显示零，重试后更新",async()=>{
  vi.spyOn(samples,"listSamples").mockRejectedValueOnce(new Error("登记断连")).mockResolvedValue({samples:[],pagination});
  vi.spyOn(samples,"getSampleFieldOptions").mockResolvedValue({fields:{}});
  render(<MemoryRouter><SampleRegistry/></MemoryRouter>);
  await screen.findByText("样本加载失败");
  expect(screen.getAllByText("登记断连")).toHaveLength(1);expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.getByText("补充登记信息 · 样本数量暂未读取")).toBeVisible();
  expect(screen.queryByText("补充登记信息 · 0 个样本")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button",{name:"重新读取样本"}));await screen.findByText("补充登记信息 · 0 个样本");
});
it("候选读取失败有独立重试，不重取已读取登记与筛选",async()=>{
  const list=vi.spyOn(samples,"listSamples").mockResolvedValue({samples:[],pagination});
  const options=vi.spyOn(samples,"getSampleFieldOptions").mockRejectedValueOnce(new Error("候选断连")).mockResolvedValue({fields:{institution:["甲机构"]}});
  render(<MemoryRouter initialEntries={["/?project_id=p&asset_set=甲&institution=原机构"]}><SampleRegistry/></MemoryRouter>);
  const alert=await screen.findByRole("alert");expect(alert).toHaveTextContent("筛选候选暂时无法读取");
  fireEvent.click(within(alert).getByRole("button",{name:"重新读取筛选候选"}));
  await waitFor(()=>expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(options).toHaveBeenLastCalledWith("p","","甲",{view:"filters"});expect(list).toHaveBeenCalledTimes(1);
  expect(list).toHaveBeenLastCalledWith(expect.objectContaining({institution:"原机构",project_id:"p",asset_set:"甲"}));
});
