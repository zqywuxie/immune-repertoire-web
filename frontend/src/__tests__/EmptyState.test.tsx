import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Database } from "lucide-react";
import { EmptyState } from "../shared/components/EmptyState";

describe("EmptyState", () => {
  it("renders title and description", () => {
    render(
      <MemoryRouter>
        <EmptyState icon={Database} title="No Data" description="Nothing here." />
      </MemoryRouter>
    );
    expect(screen.getByText("No Data")).toBeInTheDocument();
    expect(screen.getByText("Nothing here.")).toBeInTheDocument();
  });

  it("renders action button when provided", () => {
    render(
      <MemoryRouter>
        <EmptyState
          icon={Database}
          title="No Data"
          action={{ label: "Go Home", to: "/" }}
        />
      </MemoryRouter>
    );
    expect(screen.getByText("Go Home")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("does not render button when no action", () => {
    render(
      <MemoryRouter>
        <EmptyState icon={Database} title="No Data" />
      </MemoryRouter>
    );
    expect(screen.queryByRole("button")).toBeNull();
  });
});
