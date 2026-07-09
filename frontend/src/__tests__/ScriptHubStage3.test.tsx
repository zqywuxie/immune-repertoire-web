import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Stage3ModuleConfig } from "../features/scripthub/stages/Stage3ModuleConfig";

vi.mock("../features/jobs/forms", () => ({
  getFormComponent: () => null,
}));

describe("Stage3ModuleConfig", () => {
  it("does not show backend pending labels for unavailable ScriptHub modules", async () => {
    render(
      <Stage3ModuleConfig
        modules={[
          {
            key: "charts",
            label: "Charts",
            category: "Script Hub",
            status: "unavailable",
            ui_entry: "LegacyScriptHubForm",
          },
        ]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        onUpdate={vi.fn()}
      />,
    );

    expect(screen.getByText("Charts")).toBeInTheDocument();
    expect(screen.queryByText(/backend pending/i)).not.toBeInTheDocument();
  });

  it("uses only the provided ScriptHub catalog instead of requesting job modules", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(
      <Stage3ModuleConfig
        modules={[]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        onUpdate={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("No analysis modules available.")).toBeInTheDocument();
    });
    expect(fetchMock).not.toHaveBeenCalled();

    vi.unstubAllGlobals();
  });

  it("allows selecting the combined charts module when it is available", () => {
    const onUpdate = vi.fn();

    render(
      <Stage3ModuleConfig
        modules={[
          {
            key: "charts",
            label: "综合图表",
            category: "Script Hub",
            status: "available",
            ui_entry: "ChartsCombinedForm",
          },
        ]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        sourceContext={sourceContext({ pepPaths: ["E:/data/pep"] })}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.click(screen.getByText("综合图表"));
    expect(onUpdate).toHaveBeenCalledWith(["charts"], { charts: {} });
  });

  it("allows selecting multiple ScriptHub modules", () => {
    const onUpdate = vi.fn();

    const { rerender } = render(
      <Stage3ModuleConfig
        modules={[
          {
            key: "charts",
            label: "综合图表",
            category: "Script Hub",
            status: "available",
            ui_entry: "ChartsCombinedForm",
          },
          {
            key: "topclone",
            label: "TopClone",
            category: "Script Hub",
            status: "available",
            ui_entry: "ScriptHubTopCloneConfig",
          },
        ]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        sourceContext={sourceContext({ pepPaths: ["E:/data/pep"], profilePath: "E:/data/profile.csv" })}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.click(screen.getByText("综合图表"));
    expect(onUpdate).toHaveBeenLastCalledWith(["charts"], { charts: {} });

    rerender(
      <Stage3ModuleConfig
        modules={[
          {
            key: "charts",
            label: "综合图表",
            category: "Script Hub",
            status: "available",
            ui_entry: "ChartsCombinedForm",
          },
          {
            key: "topclone",
            label: "TopClone",
            category: "Script Hub",
            status: "available",
            ui_entry: "ScriptHubTopCloneConfig",
          },
        ]}
        projectId=""
        selectedModules={["charts"]}
        moduleConfigs={{ charts: {} }}
        sourceContext={sourceContext({ pepPaths: ["E:/data/pep"], profilePath: "E:/data/profile.csv" })}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.click(screen.getByText("TopClone"));
    expect(onUpdate).toHaveBeenLastCalledWith(["charts", "topclone"], { charts: {}, topclone: {} });
  });

  it("blocks modules when the selected asset set is missing required data", () => {
    const onUpdate = vi.fn();

    render(
      <Stage3ModuleConfig
        modules={[
          {
            key: "pgen-analysis",
            label: "Pgen 分析",
            category: "Script Hub",
            status: "available",
            ui_entry: "ScriptHubPgenAnalysisConfig",
          },
        ]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        sourceContext={sourceContext({ pepPaths: ["E:/data/pep"] })}
        onUpdate={onUpdate}
      />,
    );

    expect(screen.getByText("Missing Profile")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Pgen 分析"));
    expect(onUpdate).not.toHaveBeenCalled();
  });

  it("allows modules when all required asset types are present", () => {
    const onUpdate = vi.fn();

    render(
      <Stage3ModuleConfig
        modules={[
          {
            key: "pgen-analysis",
            label: "Pgen 分析",
            category: "Script Hub",
            status: "available",
            ui_entry: "ScriptHubPgenAnalysisConfig",
          },
        ]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        sourceContext={sourceContext({
          pepPaths: ["E:/data/pep"],
          profilePath: "E:/data/profile.csv",
        })}
        onUpdate={onUpdate}
      />,
    );

    fireEvent.click(screen.getByText("Pgen 分析"));
    expect(onUpdate).toHaveBeenCalledWith(["pgen-analysis"], { "pgen-analysis": {} });
  });

  it("allows MAIT/NKT with PEP data and no Profile requirement", () => {
    const onUpdate = vi.fn();

    render(
      <Stage3ModuleConfig
        modules={[
          {
            key: "mait-nkt",
            label: "MAIT/NKT",
            category: "Script Hub",
            status: "available",
            ui_entry: "ScriptHubMaitNktConfig",
          },
        ]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        sourceContext={sourceContext({ pepPaths: ["E:/data/pep"] })}
        onUpdate={onUpdate}
      />,
    );

    expect(screen.queryByText("Missing Profile")).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("MAIT/NKT"));
    expect(onUpdate).toHaveBeenCalledWith(["mait-nkt"], { "mait-nkt": {} });
  });

  it("blocks GO/KEGG until transcriptome data is selected", () => {
    const onUpdate = vi.fn();

    render(
      <Stage3ModuleConfig
        modules={[
          {
            key: "go-kegg-enrichment",
            label: "GO/KEGG",
            category: "Script Hub",
            status: "available",
            ui_entry: "ScriptHubGoKeggConfig",
          },
        ]}
        projectId=""
        selectedModules={[]}
        moduleConfigs={{}}
        sourceContext={sourceContext({ profilePath: "E:/data/profile.csv" })}
        onUpdate={onUpdate}
      />,
    );

    expect(screen.getByText("Missing Transcriptome")).toBeInTheDocument();
    fireEvent.click(screen.getByText("GO/KEGG"));
    expect(onUpdate).not.toHaveBeenCalled();
  });
});

function sourceContext(overrides: Partial<{
  pepPaths: string[];
  profilePath: string;
  transcriptomePath: string;
}> = {}) {
  return {
    projectId: "project-1",
    assetSetId: "Set1",
    pepPaths: overrides.pepPaths || [],
    profilePath: overrides.profilePath || "",
    transcriptomePath: overrides.transcriptomePath || "",
    sampleNames: ["S1"],
    chains: ["TRA"],
    profileFields: overrides.profilePath ? ["sample", "group"] : [],
    groupFields: overrides.profilePath ? ["group"] : [],
    pepColumns: overrides.pepPaths?.length ? ["cdr3", "count"] : [],
  };
}
