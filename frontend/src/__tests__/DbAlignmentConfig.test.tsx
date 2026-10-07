import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DbAlignmentConfig } from "../features/scripthub/modules/DbAlignmentConfig";

const source = { pepPaths: ["/data/pep/001__TRA.csv"], profilePath: "/data/profile.csv", sampleNames: ["001"],
  chains: ["TRA"], profileFields: ["sample", "group", "batch"], groupFields: ["group", "batch"], pepColumns: ["CDR3(pep)", "copy", "custom"] };
const response = (data: unknown) => new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
const inspected = { success: true, preview_columns: ["CDR3(pep)", "copy", "custom"], resolved_field_mapping: { cdr3_column: "CDR3(pep)", copy_column: "copy" },
  reference_sources: [{ name: "VDJdb", available: true }, { name: "McPAS-TCR", available: true }, { name: "IEDB", available: false }] };
function Harness({ initial = {}, observe = vi.fn(), pepColumns = source.pepColumns }: { initial?: Record<string, unknown>; observe?: (value: Record<string, unknown>) => void; pepColumns?: string[] }) {
  const [value, setValue] = useState<Record<string, unknown>>({ ...initial });
  return <DbAlignmentConfig projectId="synthetic" module="db-alignment" groupSpecs={[]} loadingSpecs={false}
    sourceContext={{ ...source, pepColumns }} value={value} onChange={next => { setValue(next); observe(next); }} />;
}
describe("Database alignment effective selection", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  it("warns about missing IEDB and hides the unused threshold setting", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => response(inspected)));
    render(<Harness pepColumns={[]} />);
    expect(await screen.findByText(/IEDB 命中暂不可用/)).toBeInTheDocument();
    expect(screen.getByText(/Combined 指标仅合并 VDJdb 与 McPAS-TCR/)).toBeInTheDocument();
    expect(screen.queryByLabelText("p 值阈值")).not.toBeInTheDocument();
    const sequence = screen.getByLabelText("CDR3 序列列");
    expect(sequence).toHaveValue("CDR3(pep)");
    expect(sequence.querySelectorAll("option").length).toBeGreaterThan(2);
  });
  it("selects same-ID batches separately and includes batch in inspection", async () => {
    const fetched = vi.fn(async (url: unknown, init?: RequestInit) => response(String(url).endsWith("/inspect") ? inspected : {
      success: true, values: ["A"], samples_by_value: { A: ["甲::001", "乙::001"] },
      sample_labels: { "甲::001": "甲 / 001", "乙::001": "乙 / 001" }, sample_ids: { "甲::001": "001", "乙::001": "001" } }));
    vi.stubGlobal("fetch", fetched);
    const observe = vi.fn(); render(<Harness observe={observe} initial={{ categories: ["group"], batch_field: "batch",
      selected_group_values: { group: ["A"] }, group_sample_identity: "batch_sample" }} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(first);
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ group_sample_identity: "batch_sample", selected_samples_by_group: { group: { A: ["乙::001"] } } }));
    expect(fetched.mock.calls.some(([url, init]) => String(url).endsWith("/inspect") && JSON.parse(String(init?.body)).batch_field === "batch")).toBe(true);
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "" } });
    expect(observe).toHaveBeenCalledWith(expect.objectContaining({ group_sample_identity: "sample", selected_samples_by_group: undefined }));
  });
  it("fills only missing field mappings after slow inspection", async () => {
    let resolve!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn((url: unknown) => String(url).endsWith("/inspect")
      ? new Promise<Response>(done => { resolve = done; }) : Promise.resolve(response({ success: true, values: [] }))));
    const observe = vi.fn(); render(<Harness observe={observe} initial={{ field_mapping: {} }} />);
    await waitFor(() => expect(resolve).toBeTypeOf("function"));
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "用户已填写" } });
    fireEvent.change(screen.getByLabelText("CDR3 序列列"), { target: { value: "custom" } });
    await act(async () => resolve(response(inspected)));
    await waitFor(() => expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ output_name: "用户已填写",
      field_mapping: { cdr3_column: "custom", copy_column: "copy" } })));
  });
});
