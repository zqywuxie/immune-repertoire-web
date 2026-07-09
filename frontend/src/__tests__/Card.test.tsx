import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Card } from "../shared/components/Card";

describe("Card", () => {
  it("renders children", () => {
    render(<Card>Hello World</Card>);
    expect(screen.getByText("Hello World")).toBeInTheDocument();
  });

  it("has button role when clickable", () => {
    render(<Card onClick={() => {}}>Click me</Card>);
    expect(screen.getByRole("button")).toBeInTheDocument();
  });

  it("does not have button role when not clickable", () => {
    render(<Card>Static card</Card>);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
