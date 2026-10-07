import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GoKeggConfig } from "../features/scripthub/modules/GoKeggConfig";
import { submitLegacyScriptHubJob } from "../shared/api/scriptHub";
const source = { projectId: "expression-project", assetSetId: "Set2", profilePath: "/data/profile.csv", transcriptomePath: "/data/expression.csv", pepPaths: [],
  sampleNames: ["unrelated-profile"], chains: [], profileFields: [], groupFields: [], pepColumns: [] };
const groups = { "01": ["tpm_01_001", "tpm_01_002", "tpm_01_003"], "02": ["tpm_02_001", "tpm_02_002", "tpm_02_003"] };
const inspected = { success: true, groups: Object.keys(groups), samples_by_value: groups, sample_count: 6,
  suggested_comparisons: [{ group1: "01", group2: "02" }] };
const candidate = { id: "deg-result", job_id: "source-job", status: "available", files: ["DEG_02_vs_01.csv"], metadata: {
  output_name: "来源表达分析", sample_count: 6, selected_expression_samples: Object.values(groups).flat(),
  comparisons: [{ group1: "02", group2: "01" }], significance_column: "significant_fdr", pvalue_threshold: 0.05, logfc_cutoff: 0 } };
const reply = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
function Harness({ value = {}, observe = vi.fn(), context = source }: { value?: Record<string, unknown>; observe?: (next: Record<string, unknown>) => void; context?: typeof source }) {
  const [current, setCurrent] = useState<Record<string, unknown>>(value);
  return <GoKeggConfig projectId={context.projectId} module="go-kegg-enrichment" groupSpecs={[]} loadingSpecs={false} sourceContext={context}
    value={current} onChange={next => { setCurrent(next); observe(next); }} />;
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function installFetch() {
  const mock = vi.fn(async (url: unknown, _init?: RequestInit) => reply(String(url).includes("/sources") ? { candidates: [candidate] }
    : String(url).endsWith("/inspect") ? inspected : { success: true, task_id: "enrichment-job" }));
  vi.stubGlobal("fetch", mock); return mock;
}
describe("表达样本与差异结果复用", () => {
  it("submits actual expression columns and permits zero cutoff", async () => {
    const fetchMock = installFetch(), observe = vi.fn(); render(<Harness observe={observe} />);
    fireEvent.click(await screen.findByRole("button", { name: "01 / tpm_01_003" }));
    fireEvent.click(screen.getByRole("button", { name: "02 / tpm_02_003" }));
    fireEvent.change(screen.getByLabelText("对数倍数变化阈值"), { target: { value: "0" } });
    const actual = observe.mock.calls.at(-1)?.[0];
    expect(actual.selected_expression_samples).toEqual(["tpm_01_001", "tpm_01_002", "tpm_02_001", "tpm_02_002"]);
    await submitLegacyScriptHubJob({ module: "go-kegg-enrichment", projectId: source.projectId, payload: { ...actual, asset_set: "Set2",
      selected_samples: ["unrelated-profile"], selected_group_values: { group: ["old"] }, selected_samples_by_group: { group: { old: ["unused"] } } } });
    const submitted = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(submitted).toMatchObject({ selected_expression_samples: actual.selected_expression_samples, logfc_cutoff: 0, asset_set: "Set2" });
    expect(submitted.selected_samples).toBeUndefined(); expect(submitted.selected_group_values).toBeUndefined();
    const inspectCall = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/inspect"));
    expect(JSON.parse(String(inspectCall?.[1]?.body))).toMatchObject({ project_id: source.projectId, asset_set: "Set2" });
    expect(screen.getByText(/全部所选样本参与归一化/)).toBeInTheDocument();
  });
  it("swaps expression comparison direction and removes excluded groups", async () => {
    installFetch(); const observe = vi.fn(); render(<Harness observe={observe} />);
    fireEvent.click(await screen.findByRole("button", { name: "交换 01_vs_02 的比较方向" }));
    expect(screen.getByRole("button", { name: "02_vs_01" })).toHaveAttribute("aria-pressed", "true");
    expect(observe.mock.calls.at(-1)?.[0].comparisons).toEqual(["02_vs_01"]);
    fireEvent.click(screen.getByRole("button", { name: "01 (3)" }));
    expect(observe.mock.calls.at(-1)?.[0].comparisons).toEqual([]);
  });
  it("shows immutable source conditions and strips hidden expression selections", async () => {
    const fetchMock = installFetch(), observe = vi.fn(); render(<Harness observe={observe} />);
    await screen.findByRole("button", { name: "01_vs_02" });
    fireEvent.change(screen.getByLabelText("输入方式"), { target: { value: "deg" } });
    const selector = await screen.findByLabelText("来源差异表达结果");
    await waitFor(() => expect(selector).not.toBeDisabled());
    fireEvent.change(selector, { target: { value: "deg-result" } });
    expect(screen.getByText("来源表达分析")).toBeInTheDocument();
    expect(screen.getByText(/比较方向：02 \/ 01/)).toBeInTheDocument();
    expect(screen.getByText(/来源筛选：BH-FDR；阈值：0.05；对数倍数变化阈值：0/)).toBeInTheDocument();
    expect(screen.queryByLabelText("对数倍数变化阈值")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("查看来源实际样本列"));
    expect(screen.getByText(Object.values(groups).flat().join("、"))).toBeInTheDocument();
    await submitLegacyScriptHubJob({ module: "go-kegg-enrichment", projectId: source.projectId,
      payload: { ...observe.mock.calls.at(-1)?.[0], asset_set: "Set2", selected_expression_samples: [], selected_expression_groups: [] } });
    const submitted = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(submitted).toMatchObject({ input_mode: "deg", upstream_artifact_id: "deg-result" });
    expect(submitted.selected_expression_samples).toBeUndefined(); expect(submitted.selected_expression_groups).toBeUndefined();
    expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/inspect"))).toHaveLength(1);
  });
  it("preserves edits and explicit empty comparisons when inspection finishes", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(done => { resolve = done; })));
    const observe = vi.fn(); render(<Harness observe={observe} value={{ comparisons: [], selected_expression_samples: ["tpm_01_001", "tpm_02_001"] }} />);
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "保留富集名称" } });
    await act(async () => resolve(reply(inspected)));
    expect(screen.getByLabelText("输出名称")).toHaveValue("保留富集名称");
    expect(screen.getByRole("button", { name: "01_vs_02" })).toHaveAttribute("aria-pressed", "false");
    expect(observe.mock.calls.at(-1)?.[0]).toMatchObject({ comparisons: [], selected_expression_samples: ["tpm_01_001", "tpm_02_001"] });
  });
  it("clears a previous source on dataset changes while retaining the output name", async () => {
    installFetch(); const observe = vi.fn();
    const view = render(<Harness observe={observe} value={{ input_mode: "deg", upstream_artifact_id: "deg-result", output_name: "我的富集" }} />);
    await screen.findByText("来源表达分析");
    view.rerender(<Harness observe={observe} context={{ ...source, assetSetId: "Set3" }} />);
    await waitFor(() => expect(observe.mock.calls.at(-1)?.[0].upstream_artifact_id).toBeUndefined());
    expect(screen.getByLabelText("输出名称")).toHaveValue("我的富集");
  });
});
