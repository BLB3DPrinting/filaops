import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MemoryRouter } from "react-router-dom";
import NextActionLane from "../NextActionLane";

const renderLane = (props) =>
  render(
    <MemoryRouter>
      <NextActionLane {...props} />
    </MemoryRouter>
  );

describe("NextActionLane", () => {
  it("renders the axis label, count, and a card per action", () => {
    renderLane({
      axis: "production",
      actions: [
        { axis: "production", label: "A", severity: "critical", enabled: true },
        { axis: "production", label: "B", severity: "low", enabled: true },
      ],
    });
    expect(screen.getByText("Production")).toBeTruthy(); // axis badge
    expect(screen.getByText("2")).toBeTruthy(); // count
    expect(screen.getAllByTestId("next-action-card")).toHaveLength(2);
  });

  it("shows an empty-state line (not a collapse) when the lane has no actions", () => {
    renderLane({ axis: "payment", actions: [] });
    expect(screen.getByText("Payment")).toBeTruthy();
    expect(screen.getByText(/Nothing needs attention/)).toBeTruthy();
    expect(screen.queryByTestId("next-action-card")).toBeNull();
  });

  it("tolerates a non-array actions prop", () => {
    renderLane({ axis: "supply", actions: undefined });
    expect(screen.getByText("Supply")).toBeTruthy();
    expect(screen.getByText("0")).toBeTruthy();
  });
});
