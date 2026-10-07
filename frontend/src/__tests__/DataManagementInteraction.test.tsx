import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { AssetTable } from "../features/assets/AssetTable";
import { ProjectInputSamples } from "../features/assets/ProjectInputSamples";
import { Pagination } from "../shared/components/Pagination";
import { apiClient } from "../shared/api/client";
import type { ProjectAsset } from "../shared/types/domain";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); apiClient.invalidateCache(); });
const files: ProjectAsset[] = [{ id: "a", project_id: "p", asset_type: "profile", original_name: "成功.csv", storage_path: "/tmp/a", size: 1 },
  { id: "b", project_id: "p", asset_type: "profile", original_name: "保留.csv", storage_path: "/tmp/b", size: 1 }];

it("删除部分失败后，刷新加载期间仍保留失败项供重试", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ success: true }) }).mockResolvedValueOnce({ ok: false, json: async () => ({ message: "文件被引用" }) }));
  const { rerender } = render(<AssetTable projectId="p" assets={files} loading={false} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "选择当前列表全部文件" }));
  fireEvent.click(screen.getByRole("button", { name: "删除所选" }));
  fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
  await screen.findByText("保留.csv：文件被引用");
  rerender(<AssetTable projectId="p" assets={[]} loading />);
  expect(screen.getByRole("button", { name: "重试未删除项" })).toBeInTheDocument();
  rerender(<AssetTable projectId="p" assets={files.slice(1)} loading={false} />);
  expect(screen.getByRole("checkbox", { name: "选择 保留.csv" })).toBeChecked();
});

it("输入样本可显式补录，失败保留表单，保存原始编号及数据集", async () => {
  const coverage = { samples: [{ sample_id: "001", asset_set: "科研", coverage: { profile: [{ asset_id: "a", name: "指标.csv", status: "valid" }] }, needs_version_selection: false }],
    unresolved: [], note: "保留原始编号", pagination: { page: 1, page_size: 50, total: 1, total_pages: 1 } };
  vi.spyOn(apiClient, "get").mockImplementation(async url => (String(url).includes("/registration") ? { sample: null, project_name: "项目" } : coverage) as never);
  const save = vi.spyOn(apiClient, "post").mockRejectedValueOnce(new Error("暂时保存失败")).mockResolvedValueOnce({ sample: {} });
  render(<MemoryRouter initialEntries={["/management/projects/p?tab=samples&asset_set=科研"]}><ProjectInputSamples projectId="p" revision={0} /></MemoryRouter>);
  fireEvent.click(await screen.findByRole("button", { name: "补充样本 001 的登记信息" }));
  await screen.findByRole("dialog", { name: "补充样本信息" });
  fireEvent.change(screen.getByRole("textbox", { name: "疾病" }), { target: { value: "疾病说明" } });
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("暂时保存失败");
  expect(screen.getByRole("textbox", { name: "疾病" })).toHaveValue("疾病说明");
  expect(save.mock.calls[0][1]).toEqual(expect.objectContaining({ sample_id: "001", asset_set: "科研", fields: expect.objectContaining({ illness: "疾病说明" }) }));
  fireEvent.click(screen.getByRole("button", { name: "保存" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("大量分页只展示有限导航，仍可到达尾页", () => {
  const navigate = vi.fn();
  render(<Pagination pagination={{ page: 2500, page_size: 50, total: 250000, total_pages: 5000 }} onPageChange={navigate} />);
  expect(screen.getAllByRole("button").length).toBeLessThanOrEqual(9);
  fireEvent.click(screen.getByRole("button", { name: "第 5000 页" }));
  expect(navigate).toHaveBeenCalledWith(5000);
});
