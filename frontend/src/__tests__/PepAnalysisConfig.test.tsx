import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PepAnalysisConfig } from "../features/scripthub/modules/PepAnalysisConfig";

describe("PepAnalysisConfig", () => {
  it("lets users select a batch field for repeated sample IDs", () => {
    const onChange = vi.fn();
    render(
      <PepAnalysisConfig
        projectId="project-test"
        module="pep-analysis"
        groupSpecs={[]}
        loadingSpecs={false}
        sourceContext={{
          pepPaths: ["E:/data/pep/batch-a/TRB/S1__TRB.csv"],
          profilePath: "E:/data/Profile.csv",
          sampleNames: ["S1"],
          chains: ["TRB"],
          profileFields: ["sample", "group", "batch"],
          groupFields: ["group", "batch"],
          pepColumns: [],
        }}
        value={{}}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByLabelText("批次字段（可选）"), {
      target: { value: "batch" },
    });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ batch_field: "batch" }));
    expect(screen.getByText(/批次目录名需与指标表中的批次值一致/)).toBeTruthy();

    fireEvent.click(screen.getByText("12.clone_tracking.py"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      optional_steps: expect.arrayContaining(["9"]),
    }));

    fireEvent.click(screen.getByText("9.plot_CDR3_category_heatmap.py"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      optional_steps: expect.arrayContaining(["10"]),
    }));

    fireEvent.click(screen.getByText("10.Alignment_shared.py"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      optional_steps: expect.arrayContaining(["11"]),
    }));

    fireEvent.click(screen.getByText("8.VJ_statistication.py"));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      optional_steps: expect.arrayContaining(["12"]),
    }));
  });
});
