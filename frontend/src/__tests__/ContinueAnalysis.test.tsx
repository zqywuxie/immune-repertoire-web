import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { ContinueAnalysis } from "../features/results/ContinueAnalysis";
import { listPepCacheCandidates } from "../shared/api/scriptHub";
import type { JobResultsResponse } from "../shared/api/jobs";
vi.mock("../shared/api/scriptHub", () => ({ listPepCacheCandidates: vi.fn() }));
const list = vi.mocked(listPepCacheCandidates);
const result = { status: "completed", job: { id: "source-task", module: "pep-analysis", project_id: "project-1", payload: { asset_set: "第二批" } }, outputs: [], assets: [], result: {}, success: true } as unknown as JobResultsResponse;
const candidate = { id: "one", artifact_id: "source-task:vj:路径", path: "/results/one", cache_type: "vj_usage", job_id: "source-task", status: "available", label: "V/J 结果", available_for: ["umapin"] };
describe("结果继续分析", () => {
  beforeEach(() => vi.clearAllMocks());
  it("仅从本任务可用产物生成保留上下文的链接", async () => {
    list.mockResolvedValue({ success: true, candidates: [candidate, {...candidate, id: "other", job_id: "other-task", label: "其他任务"}, {...candidate, id: "missing", status: "missing", label: "缺失结果"}] });
    render(<ContinueAnalysis result={result} />);
    const link = await screen.findByRole("link", { name: "V/J 使用差异" });
    const url = new URL(link.getAttribute("href")!, "http://localhost");
    expect(url.pathname).toBe("/analysis/tools/vj-difference");
    expect(url.searchParams.get("project")).toBe("project-1");
    expect(url.searchParams.get("asset_set")).toBe("第二批");
    expect(url.searchParams.get("upstream_artifact")).toBe(candidate.artifact_id);
    expect(screen.getByRole("link", { name: "UMAP 特征降维" })).toBeInTheDocument();
    expect(screen.queryByText("其他任务")).not.toBeInTheDocument();
    expect(screen.queryByText("缺失结果")).not.toBeInTheDocument();
    expect(list).toHaveBeenCalledWith("project-1", undefined, "第二批");
  });
  it("失败任务不查询或展示下游入口", () => {
    render(<ContinueAnalysis result={{...result, status: "failed"}} />);
    expect(list).not.toHaveBeenCalled();
    expect(screen.queryByRole("region", { name: "继续分析" })).not.toBeInTheDocument();
  });
  it("切换到另一个任务后忽略旧请求", async () => {
    let resolveOld!: (value: {success: boolean; candidates: typeof candidate[]}) => void;
    list.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }));
    list.mockResolvedValue({ success: true, candidates: [] });
    const view = render(<ContinueAnalysis result={result} />);
    view.rerender(<ContinueAnalysis result={{...result, job: {...result.job, id: "next-task"}}} />);
    resolveOld({ success: true, candidates: [candidate] });
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
