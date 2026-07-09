import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { Stage2SourceInspection } from "../features/scripthub/stages/Stage2SourceInspection";
import { chooseRandomPepPreviewPath } from "../pages/analysis/ScriptHubWizard";

describe("Stage2SourceInspection", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders real Profile and PEP head5 preview tables", () => {
    render(
      <Stage2SourceInspection
        pepPaths={["/data/pep"]}
        profilePath="/data/profile.csv"
        transcriptomePath=""
        inspection={{
          samples: 2,
          sampleNames: ["S1", "S2"],
          chains: 2,
          chainLabels: ["TRA", "TRB"],
          pepFiles: 4,
          profileLoaded: true,
          transcriptomeLoaded: false,
          warnings: [],
          profileFields: ["sample", "Group", "Age"],
          groupFields: ["Group"],
          pepColumns: ["CDR3", "copy"],
          profilePreview: {
            path: "/data/profile.csv",
            columns: ["sample", "Group", "Age"],
            rows: [
              ["S1", "Control", 35],
              ["S2", "Treatment", 41],
            ],
            totalRows: 2,
          },
          pepPreview: {
            path: "/data/S1__TRA.csv",
            columns: ["CDR3", "copy"],
            rows: [
              ["CASSL", 12],
              ["CASSP", 7],
            ],
            totalRows: 2,
          },
        }}
        onInspect={vi.fn()}
      />,
    );

    expect(screen.getByText("Profile head5")).toBeInTheDocument();
    expect(screen.getByText("PEP head5")).toBeInTheDocument();
    expect(screen.getByText("Control")).toBeInTheDocument();
    expect(screen.getByText("CASSL")).toBeInTheDocument();
    expect(screen.queryByText("Profile Data Format")).not.toBeInTheDocument();
    expect(screen.queryByText("Column sample")).not.toBeInTheDocument();
  });

  it("uses the backend-selected random PEP file for the head5 preview", () => {
    const selectedPath = chooseRandomPepPreviewPath(
      { path: "/data/random/TRB.csv", filename: "TRB.csv" },
      [{ path: "/data/first/TRA.csv" }],
      ["/data/fallback"],
    );

    expect(selectedPath).toBe("/data/random/TRB.csv");
  });

  it("falls back to a random PEP candidate when the backend does not provide one", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.7);

    const selectedPath = chooseRandomPepPreviewPath(
      null,
      [{ path: "/data/A_TRA.csv" }, { path: "/data/B_TRB.csv" }, { path: "/data/C_TRG.csv" }],
      ["/data/fallback"],
    );

    expect(selectedPath).toBe("/data/C_TRG.csv");
  });
});
