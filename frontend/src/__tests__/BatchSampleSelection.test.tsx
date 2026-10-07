import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { PepAnalysisConfig } from "../features/scripthub/modules/PepAnalysisConfig";
import { submitLegacyScriptHubJob, submitAnalysisBatch } from "../shared/api/scriptHub";
import { GroupValueSamplePicker } from "../features/scripthub/modules/shared";

const sourceContext = { profilePath: "/data/profile.csv", pepPaths: ["/data/pep"], sampleNames: ["001"],
  chains: ["TRB"], profileFields: ["sample", "group", "batch"], groupFields: ["group", "batch"], pepColumns: [] };
const batchData = { success: true, values: ["A"], count: 1,
  samples_by_value: { A: ["甲::001", "乙::001"] },
  sample_labels: { "甲::001": "甲 / 001", "乙::001": "乙 / 001" },
  sample_ids: { "甲::001": "001", "乙::001": "001" } };
const response = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });

function Harness({ initial = {}, observe = vi.fn() }: { initial?: Record<string, unknown>; observe?: (value: Record<string, unknown>) => void }) {
  const [value, setValue] = useState<Record<string, unknown>>({ group_fields: ["group"], batch_field: "batch",
    selected_group_values: { group: ["A"] }, group_sample_identity: "batch_sample", ...initial });
  return <PepAnalysisConfig projectId="synthetic" module="pep-analysis" groupSpecs={[]} loadingSpecs={false}
    sourceContext={sourceContext} value={value} onChange={next => { setValue(next); observe(next); }} />;
}

describe("Batch sample selection", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("selects one of two same-ID samples in the same group", async () => {
    const fetchMock = vi.fn(async (_: unknown, init?: RequestInit) => response(JSON.parse(String(init?.body)).batch_field
      ? batchData : { success: true, values: ["A"], count: 1, samples_by_value: { A: ["001"] } }));
    vi.stubGlobal("fetch", fetchMock);
    const observe = vi.fn();
    render(<Harness observe={observe} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    expect(screen.getByRole("button", { name: "乙 / 001" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(first);
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ group_sample_identity: "batch_sample",
      selected_samples_by_group: { group: { A: ["乙::001"] } } }));
    expect(fetchMock.mock.calls.some(([, init]) => JSON.parse(String(init?.body)).batch_field === "batch")).toBe(true);
    fireEvent.change(screen.getByPlaceholderText("按关键词筛选样本"), { target: { value: "乙" } });
    expect(screen.queryByRole("button", { name: "甲 / 001" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "乙 / 001" })).toBeInTheDocument();
    const changes = observe.mock.calls.length;
    const filter = screen.getByLabelText("group = A 的样本：筛选样本");
    fireEvent.change(filter, { target: { value: "不存在的样本" } });
    expect(screen.getByRole("status")).toHaveTextContent("没有匹配的样本，已选范围保持不变");
    expect(screen.queryByRole("button", { name: "乙 / 001" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "仅保留筛选结果" })).toBeDisabled();
    expect(observe).toHaveBeenCalledTimes(changes);
    fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(filter).toHaveValue("");
    expect(screen.getByRole("button", { name: "甲 / 001" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "乙 / 001" })).toHaveAttribute("aria-pressed", "true");
    expect(observe).toHaveBeenCalledTimes(changes);
    expect(observe.mock.calls.at(-1)?.[0].selected_samples_by_group).toEqual({ group: { A: ["乙::001"] } });
  });

  it.each(["pep-analysis", "pgen-analysis", "topclone", "db-alignment", "mait-nkt", "ml-analysis", "umap"])("keeps batch identities out of raw filters for %s submissions", async (module) => {
    const fetchMock = vi.fn(async (_: unknown, _init?: RequestInit) => response({ success: true, task_id: "synthetic-job" }));
    vi.stubGlobal("fetch", fetchMock);
    const payload = { batch_field: "batch", group_sample_identity: "batch_sample",
      selected_samples_by_group: { group: { A: ["乙::001"] } } };
    await submitLegacyScriptHubJob({ module, projectId: "synthetic", payload });
    const single = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(single.group_sample_identity).toBe("batch_sample");
    expect(single.selected_samples_by_group).toEqual(payload.selected_samples_by_group);
    expect(single.selected_samples).toBeUndefined();
    await submitAnalysisBatch("synthetic", "Set2", "test", [{ module, payload }]);
    const batch = JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body));
    expect(batch.items[0].payload.selected_samples).toBeUndefined();
    expect(batch.items[0].payload.selected_samples_by_group).toEqual(payload.selected_samples_by_group);
    await submitLegacyScriptHubJob({ module, projectId: "synthetic", payload: {
      selected_samples_by_group: { group: { A: ["001"] } },
    } });
    expect(JSON.parse(String(fetchMock.mock.calls.at(-1)?.[1]?.body)).selected_samples).toEqual(["001"]);
  });

  it("does not erase saved choices while group data is still loading", async () => {
    let resolve!: (value: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(done => { resolve = done; })));
    const setField = vi.fn();
    render(<GroupValueSamplePicker sourceContext={sourceContext} fields={["group"]} batchField="batch" setField={setField}
      value={{ group_sample_identity: "batch_sample", selected_group_values: { group: ["A"] },
        selected_samples_by_group: { group: { A: ["乙::001"] } } }} />);
    expect(screen.getByText("正在读取分组…")).toBeInTheDocument();
    expect(setField).not.toHaveBeenCalled();
    await act(async () => resolve(response(batchData)));
    expect(await screen.findByRole("button", { name: "乙 / 001" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "甲 / 001" })).toHaveAttribute("aria-pressed", "false");
    expect(setField).not.toHaveBeenCalled();
  });

  it("translates saved raw-ID selections without changing their batch membership", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response(batchData)));
    const observe = vi.fn();
    render(<Harness observe={observe} initial={{ group_sample_identity: "sample", selected_samples_by_group: { group: { A: ["001"] } } }} />);
    await waitFor(() => expect(observe).toHaveBeenCalledWith(expect.objectContaining({
      group_sample_identity: "batch_sample", selected_samples_by_group: { group: { A: ["甲::001", "乙::001"] } },
    })));
  });

  it("clears batch choices and reloads plain IDs when the batch field changes", async () => {
    let resolvePlain!: (value: Response) => void;
    vi.stubGlobal("fetch", vi.fn(async (_: unknown, init?: RequestInit) => JSON.parse(String(init?.body)).batch_field
      ? response(batchData) : new Promise<Response>(done => { resolvePlain = done; })));
    const observe = vi.fn();
    render(<Harness observe={observe} />);
    await screen.findByRole("button", { name: "甲 / 001" });
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "" } });
    expect(observe).toHaveBeenCalledWith(expect.objectContaining({ group_sample_identity: "sample", selected_samples_by_group: undefined }));
    expect(screen.queryByRole("button", { name: "甲 / 001" })).not.toBeInTheDocument();
    await act(async () => resolvePlain(response({ success: true, values: ["A"], count: 1, samples_by_value: { A: ["001"] } })));
    await screen.findByRole("button", { name: "001" });
    await waitFor(() => expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({
      group_sample_identity: "sample", selected_samples_by_group: { group: { A: ["001"] } },
    })));
  });
});
