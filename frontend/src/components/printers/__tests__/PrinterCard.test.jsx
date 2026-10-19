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

describe("PrinterCard live FilaFarm state", () => {
  it("shows Core's status without PRO telemetry", () => {
    render(<PrinterCard printer={basePrinter} />);
    expect(screen.getByTestId("printer-state-badge")).toHaveTextContent("idle");
    expect(screen.getByTestId("printer-state-badge")).toHaveAttribute("aria-live", "polite");
    expect(screen.queryByTestId("printer-nozzle")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ams-slots")).not.toBeInTheDocument();
  });

  it("shows preparing instead of printing while the printer heats and levels", () => {
    render(
      <PrinterCard printer={{ ...basePrinter, status: "printing", state: "preparing", state_label: "Preparing" }} />
    );
    expect(screen.getByTestId("printer-state-badge")).toHaveTextContent("preparing");
  });

  it("shows needs clearing and the label after a job", () => {
    render(
      <PrinterCard printer={{ ...basePrinter, state: "needs_clearing", state_label: "Needs clearing" }} />
    );
    expect(screen.getByTestId("printer-state-badge")).toHaveTextContent("needs clearing");
    expect(screen.getByText("Needs clearing")).toBeInTheDocument();
  });

  it("shows the nozzle and every AMS slot", () => {
    render(
      <PrinterCard
        printer={{
          ...basePrinter,
          nozzle: { diameter_mm: 0.6, type: "hardened_steel" },
          ams_slots: [{ slot: 1, unit: 0, material: "PLA", color: "#FF6A13", remaining_pct: null, active: true }],
          ams_units: [{ id: 0, type: "ams_lite", env_sensors: false, humidity_pct: null, temp_c: null }],
        }}
      />
    );
    expect(screen.getByTestId("printer-nozzle")).toHaveTextContent("0.6 mm hardened steel nozzle");
    expect(screen.getByTestId("ams-slot-1")).toHaveTextContent("?");
  });

  it("shows a print error by its Bambu code, not the raw integer", () => {
    render(
      <PrinterCard
        printer={{
          ...basePrinter,
          status: "paused",
          state: "error",
          state_label: "Failed · 1200_8006",
          print_error: 0x12008006,
          print_error_code: "1200_8006",
        }}
      />
    );
    expect(screen.getByTestId("printer-state-badge")).toHaveTextContent("error");
    expect(screen.getByText("Print error 1200_8006")).toBeInTheDocument();
  });
});

describe("PrinterCard control in Bambu cloud mode", () => {
  const reason =
    "Bambu cloud mode: the printer only accepts signed commands. Turn on LAN-only mode and Developer mode on the printer to control it from FilaOps.";
  const printing = { ...basePrinter, status: "printing", state: "printing", hms_codes: ["05000500_00010007"] };

  it("disables Pause, Cancel and Clear Error with the reason when control isn't available", () => {
    render(
      <PrinterCard
        printer={{ ...printing, control_available: false, control_reason: reason }}
        onCommand={() => {}}
      />
    );
    for (const label of ["Pause", "Cancel", "Clear Error"]) {
      const button = screen.getByRole("button", { name: label });
      expect(button).toBeDisabled();
      expect(button.title).toBe(reason);
    }
    expect(screen.getByTestId("control-unavailable")).toHaveTextContent(reason);
    expect(screen.getByRole("button", { name: "Edit" })).toBeEnabled();
  });

  it("keeps the buttons enabled when control is available or unknown", () => {
    const { rerender } = render(
      <PrinterCard printer={{ ...printing, control_available: true }} onCommand={() => {}} />
    );
    expect(screen.getByRole("button", { name: "Pause" })).toBeEnabled();

    rerender(<PrinterCard printer={printing} onCommand={() => {}} />);
    expect(screen.getByRole("button", { name: "Pause" })).toBeEnabled();
    expect(screen.queryByTestId("control-unavailable")).not.toBeInTheDocument();
  });
});
