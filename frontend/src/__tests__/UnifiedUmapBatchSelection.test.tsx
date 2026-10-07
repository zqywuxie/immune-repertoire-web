import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UmapConfig } from "../features/scripthub/modules/UmapConfig";
import { submitLegacyScriptHubJob } from "../shared/api/scriptHub";

const source = { projectId: "synthetic", assetSetId: "Set2", profilePath: "/data/profile.csv", pepPaths: [],
  sampleNames: ["001", "002"], chains: ["TRB"], profileFields: ["sample", "group", "batch", "signal", "noise"],
  groupFields: ["group", "batch"], pepColumns: [] };
const reply = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
const candidate = { id: "artifact", artifact_id: "artifact", path: "/results/df_VJ_all.csv", job_id: "source-job", status: "available" };
const inspected = { success: true, suggested_sample_column: "sample", suggested_group_column: "group",
  suggested_param_begin: "signal", suggested_param_over: "noise", vj_usage_available: true,
  vj_upstream_artifact_id: "artifact", vj_usage_path: candidate.path };
const groups = { success: true, values: ["A", "B"], samples_by_value: { A: ["甲::001", "乙::001"], B: ["乙::002"] },
  sample_labels: { "甲::001": "甲 / 001", "乙::001": "乙 / 001", "乙::002": "乙 / 002" },
  sample_ids: { "甲::001": "001", "乙::001": "001", "乙::002": "002" } };
const initial = { analysis_mode: "unified", configurations: ["profile"], group_field: "group", batch_field: "batch",
  group_sample_identity: "batch_sample", selected_group_values: { group: ["A", "B"] } };
function Harness({ value = initial, observe = vi.fn() }: { value?: Record<string, unknown>; observe?: (next: Record<string, unknown>) => void }) {
  const [current, setCurrent] = useState<Record<string, unknown>>(value);
  return <UmapConfig projectId="synthetic" module="umap" groupSpecs={[]} loadingSpecs={false} sourceContext={source}
    value={current} onChange={next => { setCurrent(next); observe(next); }} />;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
describe("Unified UMAP actual batch choices", () => {
  it("submits one batch identity and the selected feature artifact", async () => {
    const fetchMock = vi.fn(async (url: unknown, _init?: RequestInit) => reply(String(url).includes("pep-cache-candidates")
      ? { success: true, candidates: [candidate] } : String(url).endsWith("/inspect") ? inspected
      : String(url).endsWith("/jobs") ? { success: true, task_id: "synthetic-job" } : groups));
    vi.stubGlobal("fetch", fetchMock);
    const observe = vi.fn(); render(<Harness observe={observe} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(first);
    const combined = screen.getByLabelText("指标表 + V/J 使用结果");
    await waitFor(() => expect(combined).not.toBeDisabled());
    fireEvent.click(combined);
    expect(await screen.findByLabelText("选择前置分析结果")).toHaveValue("artifact");
    const payload = observe.mock.calls.at(-1)?.[0];
    expect(payload).toMatchObject({ group_sample_identity: "batch_sample", batch_field: "batch",
      selected_samples_by_group: { group: { A: ["乙::001"], B: ["乙::002"] } }, upstream_artifact_id: "artifact" });
    await submitLegacyScriptHubJob({ module: "umap", projectId: "synthetic",
      payload: { ...payload, profile_path: source.profilePath, asset_set: source.assetSetId } });
    const submitted = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(submitted.selected_samples).toBeUndefined();
    expect(submitted.vj_usage_path).toBeUndefined();
    expect(submitted.upstream_artifact_id).toBe("artifact");
    const request = fetchMock.mock.calls.find(([url, init]) => String(url).endsWith("/inspect") && JSON.parse(String(init?.body)).upstream_artifact_id);
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ asset_set: "Set2", upstream_artifact_id: "artifact" });
    expect(screen.queryByLabelText("p 值阈值")).not.toBeInTheDocument();
  });

  it("preserves edits made while source inspection is pending", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: unknown) => String(url).endsWith("/inspect")
      ? new Promise<Response>(done => { resolve = done; }) : Promise.resolve(reply(groups))));
    const observe = vi.fn(); render(<Harness observe={observe} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(first);
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "自定义投影" } });
    await act(async () => resolve(reply({ ...inspected, vj_upstream_artifact_id: undefined })));
    expect(screen.getByLabelText("输出名称")).toHaveValue("自定义投影");
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ output_name: "自定义投影",
      selected_samples_by_group: { group: { A: ["乙::001"], B: ["乙::002"] } } }));
  });

  it("clears saved group choices when the batch or grouping field changes", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: unknown) => reply(String(url).endsWith("/inspect")
      ? { ...inspected, vj_upstream_artifact_id: undefined } : groups)));
    const observe = vi.fn(); render(<Harness observe={observe} />);
    await screen.findByRole("button", { name: "乙 / 001" });
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "" } });
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ batch_field: "", group_sample_identity: "sample" }));
    expect(observe.mock.calls.at(-1)?.[0].selected_samples_by_group).toBeUndefined();
    fireEvent.change(screen.getByLabelText("分组字段"), { target: { value: "batch" } });
    expect(observe.mock.calls.at(-1)?.[0].selected_samples_by_group).toBeUndefined();
    expect(observe.mock.calls.at(-1)?.[0].selected_group_values).toBeUndefined();
  });
});
