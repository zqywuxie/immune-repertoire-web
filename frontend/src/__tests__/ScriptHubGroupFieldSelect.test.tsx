import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { GroupFieldSelect } from "../features/scripthub/modules/shared";
import { ProfileConfig } from "../features/scripthub/modules/ProfileConfig";

describe("ScriptHub group field controls", () => {
  afterEach(() => {
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

    expect(screen.queryByText("Group Begin Column")).not.toBeInTheDocument();
    expect(screen.queryByText("Group End Column")).not.toBeInTheDocument();

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
});
