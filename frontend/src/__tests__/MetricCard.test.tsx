import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Boxes } from "lucide-react";
import { MetricCard } from "../shared/components/MetricCard";

describe("MetricCard", () => {
  it("renders value and label", () => {
    render(<MetricCard icon={Boxes} label="Projects" value={42} />);
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Projects")).toBeInTheDocument();
  });

  it("formats large numbers with locale", () => {
    render(<MetricCard icon={Boxes} label="Items" value={1234567} />);
    expect(screen.getByText("1,234,567")).toBeInTheDocument();
  });

  it("accepts custom color", () => {
    render(<MetricCard icon={Boxes} label="Test" value={1} color="#ff0000" />);
    const icon = document.querySelector(".lucide-boxes");
    expect(icon).toBeInTheDocument();
  });

  it("renders zero correctly", () => {
    render(<MetricCard icon={Boxes} label="Empty" value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});
