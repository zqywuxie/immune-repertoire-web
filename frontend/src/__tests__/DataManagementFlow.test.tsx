import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { ProjectDatasetManager } from "../features/assets/ProjectDatasetManager";
import { AssetInputPreview } from "../features/assets/AssetInputPreview";
import { GroupSpecSelect } from "../features/scripthub/modules/shared";
import * as projects from "../shared/api/projects";
import { apiClient } from "../shared/api/client";
import type { ProjectAsset } from "../shared/types/domain";

afterEach(() => { cleanup(); vi.restoreAllMocks(); apiClient.invalidateCache(); });
function Address() { return <output aria-label="当前地址">{useLocation().search}</output>; }
const summary = { datasets: [{ name: "科研", input_count: 215, kinds: { profile: { count: 215, statuses: { valid: 215 }, sample_min: 2, sample_max: 2 } } }] };

it("数据集卡片读取完整汇总，全部视图可表达，添加入口定位输入类型", async () => {
  vi.spyOn(projects, "listProjectDatasets").mockResolvedValue(summary);
  const list = vi.spyOn(projects, "listProjectAssets").mockResolvedValue({ assets: [], pagination: { page: 1, page_size: 50, total: 215, total_pages: 5 } });
  render(<MemoryRouter initialEntries={["/?tab=assets"]}><ProjectDatasetManager projectId="p" revision={0} onChange={vi.fn()} /><Address /></MemoryRouter>);
  await screen.findByText("215 个输入文件", { exact: false });
  expect(list.mock.calls[0][1]).toEqual(expect.objectContaining({ inputsOnly: true, pageSize: 50 }));
  expect(list.mock.calls[0][1]?.allPages).toBeUndefined();
  fireEvent.click(screen.getByRole("button", { name: "当前项目数据集" }));
  fireEvent.click(screen.getByRole("option", { name: "全部数据集" }));
  await waitFor(() => expect(screen.getByLabelText("当前地址")).toHaveTextContent("asset_set="));
  expect(screen.getByRole("button", { name: "当前项目数据集" })).toHaveTextContent("全部数据集");
  const card = screen.getByRole("heading", { name: "免疫细胞浸润" }).closest("article")!;
  fireEvent.click(within(card).getByRole("button", { name: "添加输入" }));
  const dialog = await screen.findByRole("dialog", { name: /^导入数据：/ });
  expect(within(dialog).getByRole("button", { name: "准备上传的输入类型" })).toHaveTextContent("免疫细胞浸润");
  expect(within(dialog).getByText("将浸润结果表拖到此处（可选）")).toBeVisible();
  expect(within(dialog).getByText("上传样本指标表（逗号分隔、制表符分隔或表格文件）")).not.toBeVisible();
});

it("目录预览只按项目资产请求选定子表，保留原始编号", async () => {
  const request = vi.spyOn(apiClient, "get").mockImplementation(async (_url, query) => (query?.file ?
    { directory: true, files: [{ name: "001_TRA.csv", size: 8 }], columns: ["sample", "CDR3"], rows: [["001", "CASS"]] } :
    { directory: true, files: [{ name: "001_TRA.csv", size: 8 }], columns: [], rows: [] }) as never);
  render(<AssetInputPreview projectId="p" asset={{id:"a",asset_type:"pep",storage_path:"/private/pep",original_name:"克隆目录"} as ProjectAsset} />);
  fireEvent.click(await screen.findByRole("button", { name: "001_TRA.csv" }));
  expect(await screen.findByRole("cell", { name: "001" })).toBeInTheDocument();
  expect(request.mock.calls.at(-1)).toEqual(["/api/projects/p/assets/a/table-preview", { file: "001_TRA.csv", include_files: false }, {skipCache:true}]);
});

it("选择分组方案明确展示实际顺序和提交快照说明", () => {
  const setField = vi.fn();
  render(<GroupSpecSelect value={{group_spec_id:"s"}} setField={setField} loadingSpecs={false}
    groupSpecs={[{id:"s",project_id:"p",name:"患者优先",spec_json:{groups:["患者","健康"]}}]} />);
  expect(screen.getByText(/生效顺序：患者 → 健康/)).toBeInTheDocument();
  fireEvent.change(screen.getByRole("combobox"), {target:{value:""}});
  expect(setField).toHaveBeenCalledWith("group_spec_id", undefined);
});
