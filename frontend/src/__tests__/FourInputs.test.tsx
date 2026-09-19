import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { buildAssetSets } from "../features/assets/assetSets";
import { AssetUpload } from "../features/assets/AssetUpload";
import { uploadProjectAssets } from "../shared/api/projects";
vi.mock("../shared/api/projects", () => ({
  listProjectAssets: vi.fn().mockResolvedValue({ assets: [] }),
  uploadProjectAssets: vi.fn().mockResolvedValue({ assets: [{ id: "saved" }] }),
}));
describe("四类项目输入", () => {
  it("保留旧样本表标识并隔离浸润数据集", () => {
    const assets = [
      { id: "p", asset_type: "datapoint", storage_path: "/a/sample.csv", metadata: { asset_set: "Set1" } },
      { id: "c", asset_type: "cibersort", storage_path: "/a/cells.csv", metadata: { asset_set: "Set1" } },
      { id: "d", asset_type: "deconvolution", storage_path: "/b/cells.csv", metadata: { asset_set: "Set2" } },
      { id: "r", asset_type: "processed_result", storage_path: "/a/result.csv", metadata: { asset_set: "Set1" } },
    ];
    const sets = buildAssetSets(assets as any);
    expect(sets).toHaveLength(2);
    expect(sets[0].profilePath).toBe("/a/sample.csv");
    expect(sets[0].deconvolutionPath).toBe("/a/cells.csv");
    expect(sets[0].assets).toHaveLength(2);
    expect(sets[1].deconvolutionPath).toBe("/b/cells.csv");
  });
  it("将浸润文件独立上传为项目数据并保留数据集", async () => {
    const { container } = render(<AssetUpload projectId="p1" onSuccess={() => {}} />);
    const inputs = container.querySelectorAll('input[type="file"]');
    expect(inputs).toHaveLength(4);
    const file = new File(["sample,B cells\ns1,0.2"], "cells.csv", { type: "text/csv" });
    fireEvent.change(inputs[3], { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "保存数据" }));
    await waitFor(() => expect(uploadProjectAssets).toHaveBeenCalledWith("p1", expect.objectContaining({
      assetType: "deconvolution", files: [file], assetSet: "Set1",
    })));
  });
});
