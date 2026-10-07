import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MaitNktConfig } from "../features/scripthub/modules/MaitNktConfig";

const source = { projectId: "synthetic", assetSetId: "Set2", pepPaths: ["/data/pep"], profilePath: "/data/profile.csv",
  sampleNames: ["001"], chains: ["TRA"], profileFields: ["sample", "group", "batch"], groupFields: ["group", "batch"], pepColumns: [] };
const candidate = { id: "artifact", artifact_id: "artifact", path: "/results/Pep_shared/TRA.csv", job_id: "source-job",
  cache_type: "tra_shared", usage_type: "TRA shared", group_fields: ["group"], status: "available", label: "受体 α 链结果" };
const batchData = { success: true, values: ["A"], samples_by_value: { A: ["甲::001", "乙::001"] },
  sample_labels: { "甲::001": "甲 / 001", "乙::001": "乙 / 001" }, sample_ids: { "甲::001": "001", "乙::001": "001" } };
const response = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
const inspected = { success: true, resolved_tra_path: candidate.path, sample_count: 2, sample_columns: ["甲::001", "乙::001"] };
function Harness({ initial = {}, observe = vi.fn() }: { initial?: Record<string, unknown>; observe?: (value: Record<string, unknown>) => void }) {
  const [value, setValue] = useState<Record<string, unknown>>(initial);
  return <MaitNktConfig projectId="synthetic" module="mait-nkt" groupSpecs={[]} loadingSpecs={false}
    sourceContext={source} value={value} onChange={next => { setValue(next); observe(next); }} />;
}
const saved = { tra_source: "pep_analysis", upstream_artifact_id: "artifact", source_job_id: "source-job",
  group_field: "group", batch_field: "batch", group_sample_identity: "batch_sample", selected_group_values: { group: ["A"] } };

describe("MAIT/NKT upstream interaction", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  it("defaults to an upstream artifact and inspects its identity without a raw path", async () => {
    const fetched = vi.fn(async (url: unknown, _init?: RequestInit) => response(String(url).includes("pep-cache-candidates")
      ? { success: true, candidates: [candidate] } : String(url).endsWith("/inspect") ? inspected : batchData));
    vi.stubGlobal("fetch", fetched);
    const observe = vi.fn(); render(<Harness observe={observe} />);
    expect(await screen.findByText(/已匹配 2 个受体 α 链样本/)).toBeInTheDocument();
    expect(screen.getByLabelText("受体 α 链数据来源")).toHaveValue("pep_analysis");
    expect(screen.queryByLabelText("受体 α 链数据路径")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("p 值阈值")).not.toBeInTheDocument();
    expect(screen.queryByText("tra_shared")).not.toBeInTheDocument();
    expect(screen.getAllByText("受体 α 链共享矩阵").length).toBeGreaterThan(0);
    expect(observe).toHaveBeenCalledWith(expect.objectContaining({ upstream_artifact_id: "artifact", group_field: "group" }));
    const request = fetched.mock.calls.find(([url]) => String(url).endsWith("/inspect"));
    expect(JSON.parse(String(request?.[1]?.body))).toMatchObject({ upstream_artifact_id: "artifact", project_id: "synthetic", asset_set: "Set2" });
    expect(JSON.parse(String(request?.[1]?.body)).tra_path).toBeUndefined();
  });
  it("keeps same-ID batches independent and clears old choices after a batch change", async () => {
    const fetched = vi.fn(async (url: unknown, init?: RequestInit) => response(String(url).includes("pep-cache-candidates")
      ? { success: true, candidates: [candidate] } : String(url).endsWith("/inspect") ? inspected
      : JSON.parse(String(init?.body)).batch_field ? batchData : { success: true, values: ["A"], samples_by_value: { A: ["001"] } }));
    vi.stubGlobal("fetch", fetched);
    const observe = vi.fn(); render(<Harness observe={observe} initial={saved} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(first);
    expect(observe).toHaveBeenCalledWith(expect.objectContaining({ group_sample_identity: "batch_sample", selected_samples_by_group: { group: { A: ["乙::001"] } } }));
    const inspectRequests = fetched.mock.calls.filter(([url]) => String(url).endsWith("/inspect"));
    expect(JSON.parse(String(inspectRequests.at(-1)?.[1]?.body))).toMatchObject({ group_field: "group", batch_field: "batch" });
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "" } });
    expect(observe).toHaveBeenCalledWith(expect.objectContaining({ group_sample_identity: "sample", selected_samples_by_group: undefined, mait_nkt_inspect_ok: false }));
  });
  it("preserves edited output and sample choices when a slow inspection returns", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn(async (url: unknown) => String(url).includes("pep-cache-candidates")
      ? response({ success: true, candidates: [candidate] }) : String(url).endsWith("/inspect")
        ? new Promise<Response>(done => { resolve = done; }) : response(batchData)));
    const observe = vi.fn(); render(<Harness observe={observe} initial={saved} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "用户已填写" } });
    fireEvent.click(first);
    await act(async () => resolve(response(inspected)));
    await waitFor(() => expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ output_name: "用户已填写", mait_nkt_inspect_ok: true,
      selected_samples_by_group: { group: { A: ["乙::001"] } } })));
  });
  it("clears artifact identity and inspection state when switching to a manual table", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: unknown) => response(String(url).includes("pep-cache-candidates")
      ? { success: true, candidates: [candidate] } : String(url).endsWith("/inspect") ? inspected : batchData)));
    const observe = vi.fn(); render(<Harness observe={observe} initial={saved} />);
    await screen.findByText(/已匹配 2 个受体 α 链样本/);
    fireEvent.change(screen.getByLabelText("受体 α 链数据来源"), { target: { value: "upload" } });
    expect(await screen.findByLabelText("受体 α 链数据路径")).toHaveValue("");
    await waitFor(() => expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ tra_source: "upload",
      upstream_artifact_id: undefined, tra_path: undefined, source_job_id: undefined,
      mait_nkt_inspect_ok: false, resolved_tra_path: undefined })));
    expect(screen.getByLabelText("受体 α 链数据来源")).toHaveValue("upload");
  });
});
