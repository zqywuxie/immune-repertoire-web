import { useState } from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ChartsCombinedForm } from "../features/jobs/forms/ChartsCombinedForm";

describe("ChartsCombinedForm", () => {
  it("lets users select samples and chains for combined charts", async () => {
    render(<Harness />);

    const sampleSelect = screen.getAllByRole("combobox")[0];
    fireEvent.change(sampleSelect, { target: { value: "S1" } });
    fireEvent.click(screen.getByText("Add"));

    await waitFor(() => {
      expect(screen.getByTestId("payload").textContent).toContain('"samples":["S1"]');
    });

    fireEvent.click(screen.getByText("TRA"));
    await waitFor(() => {
      expect(screen.getByTestId("payload").textContent).toContain('"selected_chains":["TRB"]');
    });
  });
});

function Harness() {
  const [value, setValue] = useState<Record<string, unknown>>({});
  return (
    <>
      <ChartsCombinedForm
        projectId="1"
        groupSpecs={[]}
        loadingSpecs={false}
        value={value}
        onChange={setValue}
        sourceContext={{
          projectId: "1",
          profilePath: "/data/profile.csv",
          pepPaths: ["/data/pep"],
          sampleNames: ["S1", "S2"],
          chains: ["TRA", "TRB"],
          profileFields: ["Sample", "Group"],
          groupFields: ["Group"],
          pepColumns: ["CDR3", "copy"],
        }}
      />
      <pre data-testid="payload">{JSON.stringify(value)}</pre>
    </>
  );
}
