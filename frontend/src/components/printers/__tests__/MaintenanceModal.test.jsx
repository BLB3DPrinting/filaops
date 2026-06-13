/**
 * MaintenanceModal — SCHED-7 "Schedule Window" tab tests.
 *
 * Verifies the datetime-local seeding contract (toLocalInputValue local
 * wall time), the submit contract (new Date(local).toISOString()), and the
 * upcoming-window list's cancel/complete actions.
 *
 * API access goes through a mocked useApi (CR #733 — the component uses
 * the shared client, never raw fetch). The mock returns a STABLE object:
 * the real hook memoizes a module-level singleton, and an unstable mock
 * would retrigger every effect keyed on `api`.
 */
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { toLocalInputValue } from "../../../utils/formatting";

const { mocks } = vi.hoisted(() => ({
  mocks: {
    toastError: vi.fn(),
    toastSuccess: vi.fn(),
    apiGet: vi.fn(),
    apiPost: vi.fn(),
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

// Stable object — created once at mock-definition time, same reference on
// every useApi() call (mirrors the real hook's memoized singleton).
vi.mock("../../../hooks/useApi", () => {
  const api = {
    get: mocks.apiGet,
    post: mocks.apiPost,
    put: vi.fn(),
    patch: vi.fn(),
    del: vi.fn(),
  };
  return { useApi: () => api };
});

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

/**
 * Find the last api.post call whose path matches `re`; returns
 * [path, payload]. The filter matters because a successful POST
 * immediately triggers a list-refresh GET via api.get.
 */
function lastPostMatching(re) {
  const calls = mocks.apiPost.mock.calls;
  for (let i = calls.length - 1; i >= 0; i--) {
    if (re.test(String(calls[i][0]))) return calls[i];
  }
  return null;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(FROZEN_NOW);
  mocks.toastError.mockReset();
  mocks.toastSuccess.mockReset();
  mocks.apiGet.mockReset();
  mocks.apiPost.mockReset();
  mocks.apiGet.mockImplementation(async () => ({
    items: WINDOWS,
    total: WINDOWS.length,
  }));
  mocks.apiPost.mockImplementation(async (path) => {
    if (/\/api\/v1\/maintenance-windows\/\d+\/(cancel|complete)$/.test(path)) {
      return { ...WINDOWS[0], status: "cancelled" };
    }
    if (path === "/api/v1/maintenance-windows") {
      return { id: 9, status: "scheduled" };
    }
    return {};
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
    expect(mocks.apiGet).not.toHaveBeenCalled();
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

    const [path, payload] =
      lastPostMatching(/\/api\/v1\/maintenance-windows$/) || [];
    expect(path).toBe("/api/v1/maintenance-windows");
    expect(payload.printer_id).toBe(1);
    // The submit contract: new Date(localValue).toISOString()
    expect(payload.starts_at).toBe(new Date("2026-06-16T08:00").toISOString());
    expect(payload.ends_at).toBe(new Date("2026-06-16T12:30").toISOString());
    expect(payload.reason).toBe("Quarterly service");
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
    expect(mocks.apiPost).not.toHaveBeenCalled();
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
    const [path] = lastPostMatching(/\/5\/cancel$/);
    expect(path).toBe("/api/v1/maintenance-windows/5/cancel");
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
    const [path] = lastPostMatching(/\/5\/complete$/);
    expect(path).toBe("/api/v1/maintenance-windows/5/complete");
    expect(onWindowsChanged).toHaveBeenCalled();
  });

  it("surfaces a backend overlap rejection as a toast error", async () => {
    // The shared client throws ApiError with message = response detail
    mocks.apiGet.mockImplementation(async () => ({ items: [], total: 0 }));
    mocks.apiPost.mockImplementation(async () => {
      throw Object.assign(
        new Error("Overlaps existing maintenance window #5"),
        { name: "ApiError", status: 400 }
      );
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
