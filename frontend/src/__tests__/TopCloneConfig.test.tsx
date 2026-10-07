import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TopCloneConfig } from "../features/scripthub/modules/TopCloneConfig";

describe("TopClone batch matching", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  it("submits the selected Profile batch field for trace mode", () => {
    const onChange = vi.fn();
    render(
      <TopCloneConfig
        projectId="project-test"
        module="topclone"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          pepPaths: [],
          sampleNames: ["S01"],
          chains: ["TRA"],
          profileFields: ["sample", "group", "batch"],
          groupFields: ["group", "batch"],
          pepColumns: [],
        }}
        value={{ mode: "trace" }}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("批次字段（可选）"), {
      target: { value: "batch" },
    });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ batch_field: "batch" }));
    expect(screen.getByText(/PEP 文件所在批次目录名需与该列取值一致/)).toBeTruthy();
  });

  it("shows the batch selector for IGH subclass analysis", () => {
    const onChange = vi.fn();
    render(
      <TopCloneConfig
        projectId="project-test"
        module="topclone"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          pepPaths: [],
          sampleNames: ["S01"],
          chains: ["IGH"],
          profileFields: ["sample", "group", "batch"],
          groupFields: ["group", "batch"],
          pepColumns: [],
        }}
        value={{ analysis_type: "igh_subclass_topclone" }}
        onChange={onChange}
      />,
    );

    expect(screen.getByLabelText("批次字段（可选）")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), {
      target: { value: "batch" },
    });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ batch_field: "batch" }));
  });
});

const source = { pepPaths: ["/data/pep"], profilePath: "/data/profile.csv", sampleNames: ["001"],
  chains: ["TRA"], profileFields: ["sample", "group", "batch"], groupFields: ["group", "batch"], pepColumns: [] };
function Harness({ mode, observe }: { mode: string; observe: (value: Record<string, unknown>) => void }) {
  const [value, setValue] = useState<Record<string, unknown>>({ mode, group_field: "group", batch_field: "batch",
    group_sample_identity: "batch_sample", selected_group_values: { group: ["A"] } });
  return <TopCloneConfig projectId="synthetic" module="topclone" groupSpecs={[]} loadingSpecs={false}
    sourceContext={source} value={value} onChange={next => { setValue(next); observe(next); }} />;
}
describe("TopClone effective parameters", () => {
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
  it.each(["trace", "per_sample"])("selects one batch atomically in %s mode", async mode => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ success: true, values: ["A"],
      samples_by_value: { A: ["甲::001", "乙::001"] }, sample_labels: { "甲::001": "甲 / 001", "乙::001": "乙 / 001" },
      sample_ids: { "甲::001": "001", "乙::001": "001" } }), { status: 200, headers: { "content-type": "application/json" } })));
    const observe = vi.fn(); render(<Harness mode={mode} observe={observe} />);
    const first = await screen.findByRole("button", { name: "甲 / 001" });
    await waitFor(() => expect(first).toHaveAttribute("aria-pressed", "true"));
    fireEvent.click(first);
    expect(observe).toHaveBeenLastCalledWith(expect.objectContaining({ group_sample_identity: "batch_sample",
      selected_samples_by_group: { group: { A: ["乙::001"] } } }));
    if (mode === "trace") {
      expect(screen.queryByLabelText("排名前几位")).not.toBeInTheDocument();
      expect(screen.getByText(/固定计算前 10、20、50、100 位/)).toBeInTheDocument();
      fireEvent.change(screen.getByRole("combobox", { name: "分析模式" }), { target: { value: "per_sample" } });
      expect(screen.getByLabelText("排名前几位")).toBeInTheDocument();
      expect(screen.queryByLabelText("p 值阈值")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "乙 / 001" })).toHaveAttribute("aria-pressed", "true");
      fireEvent.change(screen.getByRole("combobox", { name: "分析模式" }), { target: { value: "trace" } });
      expect(screen.queryByLabelText("排名前几位")).not.toBeInTheDocument();
    } else {
      expect(screen.getByLabelText("排名前几位")).toBeInTheDocument();
      expect(screen.queryByLabelText("分组顺序")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("p 值阈值")).not.toBeInTheDocument();
    }
    fireEvent.change(screen.getByLabelText("批次字段（可选）"), { target: { value: "" } });
    expect(observe).toHaveBeenCalledWith(expect.objectContaining({ group_sample_identity: "sample", selected_samples_by_group: undefined }));
  });
});
