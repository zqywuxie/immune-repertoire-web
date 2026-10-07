import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { PgenAnalysisConfig } from "../features/scripthub/modules/PgenAnalysisConfig";

const { inspectScriptHubModuleMock, readGroupMock } = vi.hoisted(() => ({
  inspectScriptHubModuleMock: vi.fn(),
  readGroupMock: vi.fn(),
}));



const sourceContext = { profilePath: "/data/profile.csv", pepPaths: ["/data/pep"], sampleNames: ["001"],
  chains: ["TRA"], profileFields: ["sample", "编号", "group", "batch"], groupFields: ["group", "batch"], pepColumns: [] };
function Harness({ initial = {}, observe = vi.fn() }: { initial?: Record<string, unknown>; observe?: (value: Record<string, unknown>) => void }) {
  const [value, setValue] = useState<Record<string, unknown>>(initial);
  return <PgenAnalysisConfig projectId="synthetic" module="pgen-analysis" groupSpecs={[]} loadingSpecs={false}
    sourceContext={sourceContext} value={value} onChange={next => { setValue(next); observe(next); }} />;
}

describe("PgenAnalysisConfig", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (input: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body));
      const data = String(input).includes("/pgen-analysis/inspect")
        ? await inspectScriptHubModuleMock(body)
        : await readGroupMock(body.file_path, body.column, body.batch_field, body.sample_col);
      return new Response(JSON.stringify(data), { status: 200, headers: { "content-type": "application/json" } });
    }));
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); inspectScriptHubModuleMock.mockReset(); readGroupMock.mockReset(); });
  it("exposes an optional batch field and explains that all selected PEP files are used", async () => {
    inspectScriptHubModuleMock.mockResolvedValue({
      success: true,
      runnable_chains: ["TRA"],
      sample_column_candidates: ["sample"],
      distribution_category_candidates: ["group", "batch"],
      sample_conflicts: [{ sample: "S1", chain: "TRA" }],
      sonnia: { available: true, message: "已就绪" },
    });
    const onChange = vi.fn();
    render(
      <PgenAnalysisConfig
        projectId="project-test"
        module="pgen-analysis"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          pepPaths: ["E:/data/pep/a.csv", "E:/data/pep/b.csv"],
          profilePath: "E:/data/Profile.csv",
          sampleNames: ["S1"],
          chains: ["TRA"],
          profileFields: ["sample", "group", "batch"],
          groupFields: ["group", "batch"],
          pepColumns: [],
        }}
        value={{}}
        onChange={onChange}
      />,
    );
    await screen.findByText("已就绪");

    fireEvent.change(screen.getByLabelText("批次字段（可选）"), {
      target: { value: "batch" },
    });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ batch_field: "batch" }));
    expect(screen.getByText(/全部 PEP 文件/)).toBeTruthy();
  });

  it("passes the chosen sample column and selects batches independently", async () => {
    inspectScriptHubModuleMock.mockResolvedValue({ success: true, sample_column_candidates: ["sample", "编号"],
      runnable_chains: ["TRA"], sonnia: { available: true, message: "已就绪" } });
    readGroupMock.mockImplementation(async (_path: string, _field: string, batch?: string) => ({ success: true, values: ["A"], count: 1,
      samples_by_value: { A: batch ? ["甲::001", "乙::001"] : ["001"] },
      sample_labels: { "甲::001": "甲 / 001", "乙::001": "乙 / 001" }, sample_ids: { "甲::001": "001", "乙::001": "001" } }));
    const observe = vi.fn();
    render(<Harness observe={observe} initial={{ sample_col: "编号", batch_field: "batch", distribution_category_col: "group",
      selected_group_values: { group: ["A"] }, group_sample_identity: "batch_sample",
      selected_samples_by_group: { group: { A: ["乙::001"] } } }} />);
    expect(await screen.findByRole("button", { name: "甲 / 001" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "乙 / 001" })).toHaveAttribute("aria-pressed", "true");
    expect(readGroupMock).toHaveBeenCalledWith("/data/profile.csv", "group", "batch", "编号");
    fireEvent.click(screen.getByRole("button", { name: "甲 / 001" }));
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ group_sample_identity: "batch_sample",
      selected_samples_by_group: { group: { A: ["甲::001", "乙::001"] } } }));
    fireEvent.change(screen.getByLabelText("样本列"), { target: { value: "sample" } });
    expect(observe).toHaveBeenCalledWith(expect.objectContaining({ sample_col: "sample", selected_samples_by_group: undefined }));
    await waitFor(() => expect(readGroupMock).toHaveBeenCalledWith("/data/profile.csv", "group", "batch", "sample"));
  });

  it("keeps user edits when slow input inspection finishes", async () => {
    let resolveInspect!: (value: unknown) => void;
    inspectScriptHubModuleMock.mockImplementation(() => new Promise(done => { resolveInspect = done; }));
    readGroupMock.mockResolvedValue({ success: true, values: ["A"], count: 1, samples_by_value: { A: ["001"] } });
    const observe = vi.fn();
    render(<Harness observe={observe} />);
    fireEvent.change(screen.getByLabelText("输出名称"), { target: { value: "用户已修改" } });
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "batch" } });
    fireEvent.change(screen.getByLabelText("分布分类列"), { target: { value: "group" } });
    await act(async () => resolveInspect({ success: true, runnable_chains: ["TRA"], sample_column_candidates: ["sample"],
      distribution_category_candidates: ["batch"], sonnia: { available: true, message: "检查已完成" } }));
    expect(await screen.findByText("检查已完成")).toBeInTheDocument();
    expect(screen.getByLabelText("输出名称")).toHaveValue("用户已修改");
    expect(screen.getByLabelText("批次字段（可选）")).toHaveValue("batch");
    expect(screen.getByLabelText("分布分类列")).toHaveValue("group");
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ output_name: "用户已修改", batch_field: "batch",
      distribution_category_col: "group" }));
  });

});
