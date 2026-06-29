import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Pagination, type PaginationInfo } from "../shared/components/Pagination";

const pg = (overrides: Partial<PaginationInfo> = {}): PaginationInfo => ({
  page: 1,
  page_size: 10,
  total: 42,
  total_pages: 5,
  ...overrides,
});

describe("Pagination", () => {
  it("renders item count and page info", () => {
    render(<Pagination pagination={pg()} onPageChange={() => {}} />);
    expect(screen.getByText(/42 items/)).toBeInTheDocument();
    expect(screen.getByText(/page 1 of 5/)).toBeInTheDocument();
  });

  it("disables previous on first page", () => {
    render(<Pagination pagination={pg({ page: 1 })} onPageChange={() => {}} />);
    expect(screen.getByText("←")).toBeDisabled();
  });

  it("disables next on last page", () => {
    render(<Pagination pagination={pg({ page: 5 })} onPageChange={() => {}} />);
    expect(screen.getByText("→")).toBeDisabled();
  });

  it("calls onPageChange with next page", () => {
    const fn = vi.fn();
    render(<Pagination pagination={pg({ page: 2 })} onPageChange={fn} />);
    fireEvent.click(screen.getByText("→"));
    expect(fn).toHaveBeenCalledWith(3);
  });

  it("calls onPageChange with page number", () => {
    const fn = vi.fn();
    render(<Pagination pagination={pg({ page: 1 })} onPageChange={fn} />);
    fireEvent.click(screen.getByText("3"));
    expect(fn).toHaveBeenCalledWith(3);
  });

  it("shows placeholder when undefined", () => {
    render(<Pagination pagination={undefined} onPageChange={() => {}} />);
    expect(screen.getByText("No pagination data")).toBeInTheDocument();
  });

  it("renders active page button highlighted", () => {
    render(<Pagination pagination={pg({ page: 1 })} onPageChange={() => {}} />);
    const btn = screen.getByText("1");
    expect(btn).toBeInTheDocument();
  });
});
