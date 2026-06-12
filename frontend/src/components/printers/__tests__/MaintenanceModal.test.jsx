/**
 * MaintenanceModal — SCHED-7 "Schedule Window" tab tests.
 *
 * Verifies the datetime-local seeding contract (toLocalInputValue local
 * wall time), the submit contract (new Date(local).toISOString()), and the
 * upcoming-window list's cancel/complete actions.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { toLocalInputValue } from "../../../utils/formatting";

const { mocks } = vi.hoisted(() => ({
  mocks: {
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
  },
}));

vi.mock("../../Toast", () => ({
  useToast: () => ({
    error: mocks.toastError,
    success: mocks.toastSuccess,
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock("../../Modal", () => ({
  default: ({ children }) => <div role="dialog">{children}</div>,
}));

import MaintenanceModal from "../MaintenanceModal";

const printers = [
  { id: 1, name: "Bambu A1 Bay 1", code: "PRT-001" },
  { id: 2, name: "Bambu P1S", code: "PRT-002" },
];

const WINDOWS = [
  {
    id: 5,
    printer_id: 1,
    resource_id: null,
    starts_at: "2026-06-16T03:00:00",
    ends_at: "2026-06-16T05:00:00",
    reason: "Belt swap",
    status: "scheduled",
    maintenance_log_id: null,
    created_by: "ops@blb3d.com",
    created_at: "2026-06-15T00:00:00",
  },
];

// Frozen clock so the datetime-local seeds are deterministic.
const FROZEN_NOW = new Date(2026, 5, 15, 10, 0, 0);

const jsonRes = (body) => ({ ok: true, json: async () => body });

/**
 * Find the last fetch call whose URL matches `re` (and, when given,
 * whose method matches); returns [url, opts]. The method filter matters
 * because a successful POST immediately triggers a list-refresh GET to
 * the same collection URL.
 */
function lastFetchMatching(re, method) {
  const calls = globalThis.fetch.mock.calls;
  for (let i = calls.length - 1; i >= 0; i--) {
    const [url, opts] = calls[i];
    if (re.test(String(url)) && (!method || opts?.method === method)) {
      return calls[i];
    }
  }
  return null;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(FROZEN_NOW);
  mocks.toastError.mockReset();
  mocks.toastSuccess.mockReset();
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const u = String(url);
    if (/\/api\/v1\/maintenance-windows\/\d+\/(cancel|complete)$/.test(u)) {
      return jsonRes({ ...WINDOWS[0], status: "cancelled" });
    }
    if (u.includes("/api/v1/maintenance-windows")) {
      if (opts.method === "POST") {
        return jsonRes({ id: 9, status: "scheduled" });
      }
      return jsonRes({ items: WINDOWS, total: WINDOWS.length });
    }
    return jsonRes({});
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("MaintenanceModal schedule-window tab (SCHED-7)", () => {
  it("defaults to the Log Maintenance tab", () => {
    render(
      <MaintenanceModal printers={printers} onClose={vi.fn()} onSave={vi.fn()} />
    );
    expect(
      screen.getByRole("heading", { name: "Log Maintenance" })
    ).toBeInTheDocument();
    // No window list fetched in log mode
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("seeds the window start/end inputs with local wall time via toLocalInputValue", async () => {
    render(
      <MaintenanceModal
        printers={printers}
        initialMode="schedule"
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );

    // Seeds MUST be the toLocalInputValue rendering of the frozen clock —
    // local wall time, never toISOString().slice() (which shifts by the
    // runner's UTC offset).
    expect(screen.getByLabelText("Window start")).toHaveValue(
      toLocalInputValue(FROZEN_NOW)
    );
    expect(screen.getByLabelText("Window end")).toHaveValue(
      toLocalInputValue(new Date(FROZEN_NOW.getTime() + 60 * 60 * 1000))
    );
  });

  it("submits the window as UTC ISO strings derived from the local inputs", async () => {
    render(
      <MaintenanceModal
        printers={printers}
        initialMode="schedule"
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );

    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Window start"), {
      target: { value: "2026-06-16T08:00" },
    });
    fireEvent.change(screen.getByLabelText("Window end"), {
      target: { value: "2026-06-16T12:30" },
    });
    fireEvent.change(screen.getByPlaceholderText(/Hotend swap/), {
      target: { value: "Quarterly service" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Schedule Window" }));

    await waitFor(() => {
      expect(mocks.toastSuccess).toHaveBeenCalledWith(
        "Maintenance window scheduled"
      );
    });

    const [url, opts] = lastFetchMatching(/maintenance-windows$/, "POST") || [];
    expect(url).toMatch(/\/api\/v1\/maintenance-windows$/);
    expect(opts.method).toBe("POST");
    const body = JSON.parse(opts.body);
    expect(body.printer_id).toBe(1);
    // The submit contract: new Date(localValue).toISOString()
    expect(body.starts_at).toBe(new Date("2026-06-16T08:00").toISOString());
    expect(body.ends_at).toBe(new Date("2026-06-16T12:30").toISOString());
    expect(body.reason).toBe("Quarterly service");
  });

  it("rejects an end time at or before the start time client-side", async () => {
    render(
      <MaintenanceModal
        printers={printers}
        initialMode="schedule"
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Window end"), {
      target: { value: toLocalInputValue(new Date(FROZEN_NOW.getTime() - 3600000)) },
    });
    fireEvent.click(screen.getByRole("button", { name: "Schedule Window" }));

    await waitFor(() => {
      expect(mocks.toastError).toHaveBeenCalledWith(
        "End time must be after start time"
      );
    });
    expect(lastFetchMatching(/maintenance-windows$/)?.[1]?.method).not.toBe(
      "POST"
    );
  });

  it("lists upcoming windows with printer name, times, and reason", async () => {
    render(
      <MaintenanceModal
        printers={printers}
        initialMode="schedule"
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    const row = await screen.findByTestId("maintenance-window-5");
    expect(row).toHaveTextContent("Bambu A1 Bay 1 (PRT-001)");
    expect(row).toHaveTextContent("Belt swap");
    expect(row).toHaveTextContent("Scheduled");
  });

  it("cancel posts to /{id}/cancel and notifies onWindowsChanged", async () => {
    const onWindowsChanged = vi.fn();
    render(
      <MaintenanceModal
        printers={printers}
        initialMode="schedule"
        onClose={vi.fn()}
        onSave={vi.fn()}
        onWindowsChanged={onWindowsChanged}
      />
    );
    const row = await screen.findByTestId("maintenance-window-5");
    fireEvent.click(within(row).getByRole("button", { name: "Cancel" }));

    await waitFor(() => {
      expect(mocks.toastSuccess).toHaveBeenCalledWith(
        "Maintenance window cancelled"
      );
    });
    const [url, opts] = lastFetchMatching(/\/5\/cancel$/);
    expect(url).toMatch(/\/api\/v1\/maintenance-windows\/5\/cancel$/);
    expect(opts.method).toBe("POST");
    expect(onWindowsChanged).toHaveBeenCalled();
  });

  it("complete posts to /{id}/complete (server writes the MaintenanceLog)", async () => {
    const onWindowsChanged = vi.fn();
    render(
      <MaintenanceModal
        printers={printers}
        initialMode="schedule"
        onClose={vi.fn()}
        onSave={vi.fn()}
        onWindowsChanged={onWindowsChanged}
      />
    );
    const row = await screen.findByTestId("maintenance-window-5");
    fireEvent.click(within(row).getByRole("button", { name: "Complete" }));

    await waitFor(() => {
      expect(mocks.toastSuccess).toHaveBeenCalledWith(
        "Maintenance window completed"
      );
    });
    const [url, opts] = lastFetchMatching(/\/5\/complete$/);
    expect(url).toMatch(/\/api\/v1\/maintenance-windows\/5\/complete$/);
    expect(opts.method).toBe("POST");
    expect(onWindowsChanged).toHaveBeenCalled();
  });

  it("surfaces a backend overlap rejection as a toast error", async () => {
    globalThis.fetch.mockImplementation(async (url, opts = {}) => {
      const u = String(url);
      if (u.includes("/api/v1/maintenance-windows") && opts.method === "POST") {
        return {
          ok: false,
          json: async () => ({
            detail: "Overlaps existing maintenance window #5",
          }),
        };
      }
      return jsonRes({ items: [], total: 0 });
    });

    render(
      <MaintenanceModal
        printers={printers}
        initialMode="schedule"
        onClose={vi.fn()}
        onSave={vi.fn()}
      />
    );
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: "1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Schedule Window" }));

    await waitFor(() => {
      expect(mocks.toastError).toHaveBeenCalledWith(
        "Overlaps existing maintenance window #5"
      );
    });
  });
});
