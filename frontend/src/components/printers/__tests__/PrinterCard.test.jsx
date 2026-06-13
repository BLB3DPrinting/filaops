/**
 * PrinterCard — SCHED-7 upcoming maintenance-window badge tests.
 *
 * The card is a pure component (no hooks), so no harness mocks are needed.
 */
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import PrinterCard from "../PrinterCard";

const basePrinter = {
  id: 1,
  name: "Bambu A1 Bay 1",
  code: "PRT-001",
  brand: "bambulab",
  model: "A1",
  status: "idle",
};

describe("PrinterCard maintenance-window badge (SCHED-7)", () => {
  it("renders no window badge when upcomingMaintenanceWindow is absent", () => {
    render(<PrinterCard printer={basePrinter} />);
    expect(
      screen.queryByTestId("maintenance-window-badge")
    ).not.toBeInTheDocument();
  });

  it("shows 'Maint Scheduled' for a scheduled window with times + reason in the tooltip", () => {
    render(
      <PrinterCard
        printer={basePrinter}
        upcomingMaintenanceWindow={{
          id: 5,
          starts_at: "2026-06-16T03:00:00",
          ends_at: "2026-06-16T05:00:00",
          reason: "Belt swap",
          status: "scheduled",
        }}
      />
    );
    const badge = screen.getByTestId("maintenance-window-badge");
    expect(badge).toHaveTextContent("Maint Scheduled");
    expect(badge.title).toContain("Belt swap");
    expect(badge.title).toMatch(/Maintenance window .+ → .+/);
  });

  it("shows 'In Maintenance' when the window is in progress", () => {
    render(
      <PrinterCard
        printer={{ ...basePrinter, status: "maintenance" }}
        upcomingMaintenanceWindow={{
          id: 6,
          starts_at: "2026-06-15T08:00:00",
          ends_at: "2026-06-15T12:00:00",
          reason: null,
          status: "in_progress",
        }}
      />
    );
    expect(screen.getByTestId("maintenance-window-badge")).toHaveTextContent(
      "In Maintenance"
    );
  });

  it("window badge coexists with the SCHED-4 due-soon badge", () => {
    render(
      <PrinterCard
        printer={basePrinter}
        maintenanceDueSoon
        upcomingMaintenanceWindow={{
          id: 7,
          starts_at: "2026-06-16T03:00:00",
          ends_at: "2026-06-16T05:00:00",
          reason: "Nozzle change",
          status: "scheduled",
        }}
      />
    );
    expect(screen.getByTestId("maintenance-due-badge")).toBeInTheDocument();
    expect(screen.getByTestId("maintenance-window-badge")).toBeInTheDocument();
  });
});
