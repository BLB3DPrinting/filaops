import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import StatusBadge from "./StatusBadge";

describe("StatusBadge", () => {
  it("renders the descriptor label", () => {
    render(<StatusBadge model="production_order" field="status" value="complete" />);
    expect(screen.getByText("Complete")).toBeInTheDocument();
  });

  it("applies the descriptor tone to the Badge (danger → red)", () => {
    render(<StatusBadge model="sales_order" field="payment_status" value="overdue" />);
    expect(screen.getByText("Overdue").className).toContain("text-red-400");
  });

  it("defaults field to 'status' and renders complete/completed identically", () => {
    const { rerender } = render(<StatusBadge model="production_order" value="complete" />);
    expect(screen.getByText("Complete").className).toContain("text-green-400");
    rerender(<StatusBadge model="production_order" value="completed" />);
    expect(screen.getByText("Complete").className).toContain("text-green-400");
  });

  it("falls back to a neutral badge for an unknown status (never blank/crash)", () => {
    render(<StatusBadge model="production_order" field="status" value="warp_drive" />);
    expect(screen.getByText("Warp Drive").className).toContain("text-gray-400");
  });
});
