import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PepCacheCardSelector } from "../features/scripthub/modules/shared";
import { listPepCacheCandidates } from "../shared/api/scriptHub";
import type { PepCacheCandidate } from "../shared/api/scriptHub";

vi.mock("../shared/api/scriptHub", () => ({ listPepCacheCandidates: vi.fn(), readScriptHubGroupValues: vi.fn() }));
const list = vi.mocked(listPepCacheCandidates);
const sourceContext = {
  projectId: "project-1", assetSetId: "第二批", profilePath: "", pepPaths: [],
  sampleNames: [], chains: [], profileFields: [], groupFields: [], pepColumns: [],
};
const first: PepCacheCandidate = {
  id: "legacy-card-1", artifact_id: "task:usage:one", path: "/output/one", cache_type: "usage",
  status: "available", label: "第一份结果", asset_set: "第二批",
};
const second: PepCacheCandidate = { ...first, id: "legacy-card-2", artifact_id: "task:usage:two", path: "/output/two", label: "第二份结果" };

describe("前置分析结果选择", () => {
  beforeEach(() => vi.clearAllMocks());

  it("按数据集加载并通过产物标识恢复已选结果", async () => {
    list.mockResolvedValue({ success: true, candidates: [first, second] });
    const onSelect = vi.fn();
    render(<PepCacheCardSelector sourceContext={sourceContext} cacheType="volcano" value={second.artifact_id} onSelect={onSelect} />);
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue(second.id));
    expect(list).toHaveBeenCalledWith("project-1", "volcano", "第二批");
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByText("来源数据集：第二批")).toBeInTheDocument();
  });

  it("多个结果不自动选择，不允许选择缺失结果", async () => {
    const missing = { ...first, id: "missing", status: "missing", label: "旧结果", reason: "结果文件已缺失" };
    list.mockResolvedValue({ success: true, candidates: [first, second, missing] });
    const onSelect = vi.fn();
    render(<PepCacheCardSelector sourceContext={sourceContext} cacheType="volcano" onSelect={onSelect} />);
    const select = await screen.findByRole("combobox");
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole("option", { name: /结果文件已缺失/ })).toBeDisabled();
    fireEvent.change(select, { target: { value: "missing" } });
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.change(select, { target: { value: second.id } });
    expect(onSelect).toHaveBeenCalledWith(second);
  });

  it("唯一可用结果可预选", async () => {
    list.mockResolvedValue({ success: true, candidates: [first] });
    const onSelect = vi.fn();
    render(<PepCacheCardSelector sourceContext={sourceContext} cacheType="volcano" onSelect={onSelect} />);
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(first));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
