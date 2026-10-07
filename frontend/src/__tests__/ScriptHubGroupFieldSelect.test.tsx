import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { GroupFieldSelect } from "../features/scripthub/modules/shared";
import { ProfileConfig } from "../features/scripthub/modules/ProfileConfig";
import { TopCloneConfig } from "../features/scripthub/modules/TopCloneConfig";

describe("ScriptHub group field controls", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("loads and displays groups after a group field is selected", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      success: true,
      file_path: "/data/profile.csv",
      column: "Disease",
      values: ["Control", "Tumor"],
      count: 2,
    }), { status: 200, headers: { "content-type": "application/json" } })));

    render(
      <GroupFieldSelect
        value="Disease"
        sourceContext={{
          profilePath: "/data/profile.csv",
          pepPaths: [],
          sampleNames: [],
          chains: [],
          profileFields: ["Sample", "Disease", "Batch"],
          groupFields: ["Disease", "Batch"],
          pepColumns: [],
        }}
        onChange={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Control")).toBeInTheDocument();
      expect(screen.getByText("Tumor")).toBeInTheDocument();
    });
  });

  it("uses Group Type Fields for profile grouping and writes custom group order", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/profile/inspect")) {
        return new Response(JSON.stringify({
          success: true,
          suggested_param_begin: "ScoreA",
          suggested_param_over: "ScoreB",
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      if (url.includes("/boxplot/group-values")) {
        return new Response(JSON.stringify({
          success: true,
          file_path: "/data/profile.csv",
          column: "Disease",
          values: ["Control", "Tumor"],
          count: 2,
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response(JSON.stringify({ success: true }), { status: 200, headers: { "content-type": "application/json" } });
    }));

    const onChange = vi.fn();
    function Harness() {
      const [value, setValue] = useState<Record<string, unknown>>({
        grouptype_fields: ["Disease"],
        param_begin: "ScoreA",
        param_over: "ScoreB",
      });
      return (
        <ProfileConfig
          projectId="project-1"
          module="profile"
          groupSpecs={[]}
          loadingSpecs={false}
          sourceContext={{
            profilePath: "/data/profile.csv",
            pepPaths: [],
            sampleNames: [],
            chains: [],
            profileFields: ["sample", "Disease", "ScoreA", "ScoreB"],
            groupFields: ["Disease"],
            pepColumns: [],
          }}
          value={value}
          onChange={(next) => {
            setValue(next);
            onChange(next);
          }}
        />
      );
    }

    render(<Harness />);

    expect(screen.queryByText("分组起始列")).not.toBeInTheDocument();
    expect(screen.queryByText("分组结束列")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Control")).toBeInTheDocument();
      expect(screen.getByText("Tumor")).toBeInTheDocument();
    });

    fireEvent.dragStart(screen.getByTestId("group-order-row-Disease-Tumor"));
    fireEvent.dragOver(screen.getByTestId("group-order-row-Disease-Control"));
    fireEvent.drop(screen.getByTestId("group-order-row-Disease-Control"));

    await waitFor(() => {
      expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
        grouptype_fields: ["Disease"],
        group_order: JSON.stringify({ Disease: "Tumor,Control" }),
      }));
    });
  });

  it("shows composition inputs and the selected subclass measure", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/profile/inspect")) {
        return new Response(JSON.stringify({
          success: true,
          composition_columns: {
            reads: { chains: ["TRA_Percent", "TRB_Percent"], subclass_columns: ["IGHM_percent_by_reads"] },
            clone: { chains: ["TRA_Percent", "TRB_Percent"], subclass_columns: ["IGHM_percent_by_clone"] },
          },
        }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response(JSON.stringify({ success: true, values: ["Control", "Tumor"], count: 2 }), {
        status: 200, headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const onChange = vi.fn();
    render(
      <ProfileConfig
        projectId="project-1"
        module="profile"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          profilePath: "/data/profile.csv", pepPaths: [], sampleNames: [], chains: [],
          profileFields: ["sample", "Disease", "TRA_Percent", "TRB_Percent", "IGHM_percent_by_reads", "IGHM_percent_by_clone"],
          groupFields: ["Disease"], pepColumns: [],
        }}
        value={{ analysis_type: "composition", group_column: "Disease", grouptype_fields: ["Disease"], subclass_measure: "reads" }}
        onChange={onChange}
      />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes("/profile/inspect"))).toBe(true);
    await waitFor(() => {
      expect(screen.getByText(/可生成受体链图/)).toHaveTextContent("TRA_Percent");
      expect(screen.getByText(/可生成亚类图/)).toHaveTextContent("IgM");
    });
    fireEvent.change(screen.getByLabelText("亚类百分比口径"), { target: { value: "clone" } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ subclass_measure: "clone" }));
  });

  it("shows only detected CSR measures and explains the statistical outputs", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
      success: true,
      values: ["Control", "Tumor"],
      count: 2,
    }), { status: 200, headers: { "content-type": "application/json" } })));
    const onChange = vi.fn();
    render(
      <ProfileConfig
        projectId="project-1"
        module="profile"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          profilePath: "/data/profile.csv", pepPaths: [], sampleNames: [], chains: [],
          profileFields: ["sample", "Disease", "IGHM-IGHD_CSR_ratio", "IGHM-IGHA_CSR0"],
          groupFields: ["Disease"], pepColumns: [],
        }}
        value={{ analysis_type: "csr", group_column: "Disease", grouptype_fields: ["Disease"], csr_measure: "auto" }}
        onChange={onChange}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/已检测统计口径/)).toHaveTextContent("CSR_ratio、CSR0");
    });
    const measure = screen.getByLabelText("CSR 指标口径");
    expect(Array.from((measure as HTMLSelectElement).options).map((option) => option.value)).toEqual(["auto", "CSR_ratio", "CSR0"]);
    expect(screen.getByText(/双侧 Mann–Whitney 检验/)).toBeInTheDocument();
    fireEvent.change(measure, { target: { value: "CSR0" } });
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ csr_measure: "CSR0" }));
  });

  it("presents IGH subclass TopClone as a sample-level analysis with its denominator", async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ success: true, values: ["A", "B"], count: 2 }), {
      status: 200, headers: { "content-type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);
    const onChange = vi.fn();
    render(
      <TopCloneConfig
        projectId="project-1"
        module="topclone"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          profilePath: "/data/profile.csv", pepPaths: ["/data/IGH"],
          sampleNames: ["A1", "A2", "B1", "B2"], chains: ["IGH"],
          profileFields: ["sample", "Disease"], groupFields: ["Disease"], pepColumns: ["c_call", "CDR3(pep)", "copy"],
        }}
        value={{ analysis_type: "igh_subclass_topclone", group_field: "Disease" }}
        onChange={onChange}
      />,
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(screen.getByText("IGH 免疫球蛋白亚类优势克隆")).toBeInTheDocument();
    expect(screen.getByText(/该亚类总 copy/)).toBeInTheDocument();
    expect(screen.getByText(/双侧 Mann–Whitney 检验/)).toBeInTheDocument();
    expect(screen.queryByText("分析模式")).not.toBeInTheDocument();
  });
});
