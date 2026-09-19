import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "../shared/components/StatusBadge";

describe("StatusBadge", () => {
  it("renders queued status", () => {
    render(<StatusBadge status="queued" />);
    expect(screen.getByText("等待中")).toBeInTheDocument();
  });

  it("renders running status", () => {
    render(<StatusBadge status="running" />);
    expect(screen.getByText("运行中")).toBeInTheDocument();
  });

  it("renders completed status", () => {
    render(<StatusBadge status="completed" />);
    expect(screen.getByText("已完成")).toBeInTheDocument();
  });

  it("renders failed status", () => {
    render(<StatusBadge status="failed" />);
    expect(screen.getByText("失败")).toBeInTheDocument();
  });

  it("renders unknown status without crash", () => {
    render(<StatusBadge status="unknown-status" />);
    expect(screen.getByText("unknown-status")).toBeInTheDocument();
  });
});
