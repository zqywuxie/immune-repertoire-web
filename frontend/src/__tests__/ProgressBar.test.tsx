import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ProgressBar } from "../shared/components/ProgressBar";

describe("ProgressBar", () => {
  it("renders with correct aria attributes", () => {
    render(<ProgressBar value={50} max={100} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "50");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("clamps to 100%", () => {
    render(<ProgressBar value={150} max={100} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "150");
  });
});
