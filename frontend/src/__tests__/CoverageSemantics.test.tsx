import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { apiClient } from "../shared/api/client";
import { ProjectInputSamples } from "../features/assets/ProjectInputSamples";

afterEach(() => { cleanup(); vi.restoreAllMocks(); apiClient.invalidateCache(); });
const row = {sample_id:"001",asset_set:"甲",needs_version_selection:false,
  coverage:{profile:[{asset_id:"profile-1",name:"指标.csv",status:"valid"}]}};
function setup(input_scopes?: Record<string, Record<string, {asset_count:number;unresolved_count:number}>>) {
  vi.spyOn(apiClient,"get").mockResolvedValue({samples:[row],input_scopes,unresolved:[],note:"保留原始编号",
    pagination:{page:1,page_size:50,total:1,total_pages:1}});
  render(<MemoryRouter initialEntries={["/management/projects/p?tab=samples&asset_set=甲"]}>
    <ProjectInputSamples projectId="p" revision={0}/></MemoryRouter>);
}

it("区分未提供的可选输入、识别未完成和有效文件不含编号，并提供真实范围入口", async () => {
  setup({甲:{profile:{asset_count:1,unresolved_count:0},transcriptome:{asset_count:2,unresolved_count:1},
    deconvolution:{asset_count:1,unresolved_count:0}}});
  const cells=within(await screen.findByRole("row",{name:/甲 001/})).getAllByRole("cell");
  expect(cells[2]).toHaveTextContent("尚未提供此类输入");
  expect(cells[4]).toHaveTextContent("已有文件，样本识别待完成");
  expect(cells[5]).toHaveTextContent("已识别输入中未包含该编号");
  expect(within(cells[2]).queryByRole("link")).not.toBeInTheDocument();
  const target=new URL(within(cells[4]).getByRole("link",{name:"查看文件状态"}).getAttribute("href")!,"http://fixture");
  expect(target.pathname).toBe("/management/projects/p");
  expect(target.searchParams.get("asset_set")).toBe("甲");
  expect(target.searchParams.get("file_type")).toBe("transcriptome");
  expect(screen.getByText(/未提供的可选输入不视为错误/)).toBeInTheDocument();
});

it("其他数据集的未识别文件不影响当前样本的空格原因", async () => {
  setup({甲:{profile:{asset_count:1,unresolved_count:0}},乙:{pep:{asset_count:1,unresolved_count:1}}});
  expect(await screen.findAllByText("尚未提供此类输入")).toHaveLength(3);
  expect(screen.queryByText("已有文件，样本识别待完成")).not.toBeInTheDocument();
});

it("缺少范围摘要时不把未知状态解释为未提供输入", async () => {
  setup();
  expect(await screen.findAllByText("暂无已识别来源")).toHaveLength(3);
  expect(screen.queryByText("尚未提供此类输入")).not.toBeInTheDocument();
});
