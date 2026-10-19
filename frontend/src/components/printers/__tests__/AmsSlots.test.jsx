import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import AmsSlots from "../AmsSlots";

const slots = [
  { slot: 1, unit: 0, tray: 0, material: "PLA", brand: null, color: "#FF6A13", remaining_pct: null, active: false },
  { slot: 2, unit: 0, tray: 1, material: "PETG", brand: "PETG HF", color: "#000000", remaining_pct: 80, active: true },
  { slot: 3, unit: 0, tray: 2, material: null, brand: null, color: null, remaining_pct: null, active: false },
];

describe("AmsSlots", () => {
  it("renders nothing without slots", () => {
    const { container } = render(<AmsSlots slots={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows every slot, with ? for an unknown amount and the active slot marked", () => {
    render(<AmsSlots slots={slots} units={[]} />);

    expect(screen.getByTestId("ams-slot-1")).toHaveTextContent("PLA");
    expect(screen.getByTestId("ams-slot-1")).toHaveTextContent("?");
    expect(screen.getByTestId("ams-slot-2")).toHaveTextContent("80%");
    expect(screen.getByTestId("ams-slot-2")).toHaveTextContent("Active");
    expect(screen.getByTestId("ams-slot-2").title).toBe("PETG HF");
    expect(screen.getByTestId("ams-slot-3")).toHaveTextContent("Empty");
  });

  it("shows humidity and temperature only for units with sensors", () => {
    const { rerender } = render(
      <AmsSlots slots={slots} units={[{ id: 0, type: "ams", env_sensors: true, humidity_pct: 35, temp_c: 29.0 }]} />
    );
    expect(screen.getByTestId("ams-env-0")).toHaveTextContent("35% RH · 29°C");

    rerender(
      <AmsSlots slots={slots} units={[{ id: 0, type: "ams_lite", env_sensors: false, humidity_pct: null, temp_c: null }]} />
    );
    expect(screen.queryByTestId("ams-env-0")).not.toBeInTheDocument();
  });

  it("groups slots by unit, deriving it from the slot number for older PRO data", () => {
    render(<AmsSlots slots={[{ slot: 1, material: "PLA" }, { slot: 5, material: "ABS" }]} />);

    expect(screen.getByText("AMS 1")).toBeInTheDocument();
    expect(screen.getByText("AMS 2")).toBeInTheDocument();
  });
});
