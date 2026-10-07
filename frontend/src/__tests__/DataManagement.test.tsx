import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AssetTable } from "../features/assets/AssetTable";
import { AssetUpload } from "../features/assets/AssetUpload";
import { apiClient } from "../shared/api/client";
import * as projects from "../shared/api/projects";
import type { ProjectAsset } from "../shared/types/domain";

beforeEach(() => { vi.spyOn(projects,"listProjectDatasets").mockResolvedValue({datasets:[]}); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); apiClient.invalidateCache(); });
const assets = [{ id: "a1", project_id: "p1", asset_type: "profile", original_name: "甲.csv", storage_path: "/tmp/甲.csv", size: 10, metadata: { asset_set: "甲" } },
  { id: "a2", project_id: "p1", asset_type: "profile", original_name: "乙.csv", storage_path: "/tmp/乙.csv", size: 10, metadata: { asset_set: "乙" } }] as ProjectAsset[];

describe("数据管理的真实操作边界", () => {
  it("批量删除先确认，部分失败保留失败项和原因", async () => {
    const request = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ success: true }) }).mockResolvedValueOnce({ ok: false, json: async () => ({ message: "文件仍被任务引用" }) });
    vi.stubGlobal("fetch", request);
    render(<AssetTable projectId="p1" assets={assets} loading={false} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "选择当前列表全部文件" }));
    fireEvent.click(screen.getByRole("button", { name: "删除所选" }));
    expect(request).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "确认删除 2 个文件" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(screen.getByText(/乙.csv：文件仍被任务引用/)).toBeInTheDocument());
    expect(screen.getByRole("checkbox", { name: "选择 甲.csv" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "选择 乙.csv" })).toBeChecked();
    expect(screen.getByRole("button", { name: "重试未删除项" })).toBeInTheDocument();
  });

  it("切换项目后清空选择，不能删除上一项目的文件", () => {
    const { rerender } = render(<AssetTable projectId="p1" assets={assets} loading={false} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "选择 甲.csv" }));
    expect(screen.getByRole("button", { name: "删除所选" })).toBeInTheDocument();
    rerender(<AssetTable projectId="p2" assets={assets} loading={false} />);
    expect(screen.queryByRole("button", { name: "删除所选" })).not.toBeInTheDocument();
  });

  it("修改归属只提交业务字段，失败显示原因并保留内容", async () => {
    const request = vi.fn().mockResolvedValue({ ok: false, json: async () => ({ message: "该版本被任务引用" }) });
    vi.stubGlobal("fetch", request);
    render(<AssetTable projectId="p1" assets={assets} loading={false} />);
    fireEvent.click(screen.getByRole("button",{name:"更多操作：甲.csv"}));
 fireEvent.click(screen.getByRole("button", { name: "修改 甲.csv 的数据集归属" }));
    fireEvent.change(screen.getByRole("textbox", { name: "数据集名称" }), { target: { value: "新数据集" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(screen.getByText("该版本被任务引用")).toBeInTheDocument());
    expect(screen.getByRole("textbox", { name: "数据集名称" })).toHaveValue("新数据集");
    expect(JSON.parse(request.mock.calls[0][1].body)).toEqual({ metadata_json: { asset_set: "新数据集" } });
  });

  it("完整输入查询读取后续页且限定输入，不被结果挤占", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValueOnce({ assets: assets.slice(0, 1), pagination: { total_pages: 2 } })
      .mockResolvedValueOnce({ assets: assets.slice(1), pagination: { total_pages: 2 } });
    const response = await projects.listProjectAssets("p1", { inputsOnly: true, allPages: true });
    expect(response.assets.map(asset => asset.id)).toEqual(["a1", "a2"]);
    expect(get.mock.calls.map(call => call[1])).toEqual([expect.objectContaining({ inputs_only: true, page: 1, page_size: 200 }), expect.objectContaining({ inputs_only: true, page: 2, page_size: 200 })]);
  });

  it("多类型上传部分失败后只重试失败文件", async () => {
    vi.spyOn(projects, "listProjectAssets").mockResolvedValue({ assets: [] });
    const upload = vi.spyOn(projects, "uploadProjectAssets").mockResolvedValueOnce({ assets: [assets[0]] }).mockRejectedValueOnce(new Error("表达矩阵上传失败"))
      .mockResolvedValueOnce({ assets: [assets[1]] });
    render(<AssetUpload projectId="p1" onSuccess={vi.fn()} />);
    const profile = new File(["sample,value\n001,1"], "指标.csv");
    const expression = new File(["gene,001\nTP53,1"], "表达.csv");
    fireEvent.change(screen.getByLabelText("上传样本指标表（逗号分隔、制表符分隔或表格文件）", { selector: "input" }), { target: { files: [profile] } });
    fireEvent.change(screen.getByLabelText("将表达矩阵拖到此处（可选）", { selector: "input" }), { target: { files: [expression] } });
    await waitFor(()=>expect(screen.getByRole("button", {name:/保存数据/})).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /保存数据/ }));
    await waitFor(() => expect(screen.getByRole("button", { name: /保存数据/ })).toBeEnabled());
    expect(upload).toHaveBeenCalledTimes(2);
    expect(screen.getByText(/表达矩阵上传失败/)).toBeInTheDocument();
    await waitFor(()=>expect(screen.getByRole("button", {name:/保存数据/})).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: /保存数据/ }));
    await waitFor(() => expect(upload).toHaveBeenCalledTimes(3));
    expect(upload.mock.calls.map(call => call[1].assetType)).toEqual(["profile", "transcriptome", "transcriptome"]);
    expect(upload.mock.calls[2][1].files[0]).toBe(expression);
  });
});

it("删除同名文件前可核对当前和历史版本的精确身份", () => {
  const current = {...assets[0], original_name:"同名.csv", metadata:{asset_set:"甲",content_version:"版本甲",validation:{status:"valid"}}};
  const historical = {...assets[0], id:"history-id", original_name:"同名.csv", metadata:{asset_set:"甲",content_version:"版本乙",superseded:true,validation:{status:"valid"}}};
  render(<AssetTable projectId="p1" assets={[current,historical]} loading={false}/>);
  fireEvent.click(screen.getByRole("checkbox", {name:"选择当前列表全部文件"}));
  fireEvent.click(screen.getByRole("button", {name:"删除所选"}));
  const dialog = within(screen.getByRole("dialog", {name:"确认删除 2 个文件"}));
  expect(dialog.getByText("当前版本")).toBeVisible();
  expect(dialog.getByText("历史版本")).toBeVisible();
  expect(dialog.getByText(/版本甲.*a1/)).toBeVisible();
  expect(dialog.getByText(/版本乙.*history-id/)).toBeVisible();
});
