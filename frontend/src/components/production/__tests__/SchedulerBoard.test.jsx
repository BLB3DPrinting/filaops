/**
 * SchedulerBoard (SCHED-5) — unit tests.
 *
 * Pure helpers (getWindow / pctOf / getTicks) are tested directly;
 * the component is tested against a mocked /scheduling/board payload.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import SchedulerBoard, { getWindow, pctOf, getTicks } from "../SchedulerBoard";

const mocks = vi.hoisted(() => {
  const get = vi.fn();
  // Stable object — the real useApi is useMemo'd, so the mock must be
  // referentially stable too or fetchBoard's deps churn every render.
  return { get, api: { get } };
});

vi.mock("../../../hooks/useApi", () => ({
  useApi: () => mocks.api,
}));

// The component anchors to "today" via new Date() at mount, so the clock is
// FROZEN to a fixed instant (10 AM local on 2026-06-15) in beforeEach —
// otherwise a suite that crosses midnight would shift the day window out
// from under the mocked block timestamps. shouldAdvanceTime keeps
// waitFor/findBy working under fake timers.
const FROZEN_NOW = new Date(2026, 5, 15, 10, 0, 0);
const dayStart = new Date(2026, 5, 15);
const at = (h) => new Date(dayStart.getTime() + h * 3600 * 1000).toISOString();

const BOARD = {
  start: dayStart.toISOString(),
  end: new Date(dayStart.getTime() + 24 * 3600 * 1000).toISOString(),
  lanes: [
    {
      key: "resource-1",
      kind: "resource",
      id: 1,
      code: "FDM-01",
      name: "Bambu P1S #1",
      status: "available",
      work_center_code: "FDM-POOL",
      utilization_percent: 25.0,
      operations: [
        {
          id: 11,
          operation_code: "OP010",
          operation_name: "3D Print",
          sequence: 10,
          status: "queued",
          scheduled_start: at(2),
          scheduled_end: at(8),
          planned_setup_minutes: "0",
          planned_run_minutes: "360",
          production_order_id: 100,
          production_order_code: "PO-2026-0099",
          production_order_status: "released",
          product_name: "Headphone Mount",
          quantity: 10,
        },
      ],
    },
    {
      key: "printer-2",
      kind: "printer",
      id: 2,
      code: "PRT-A1",
      name: "Bambu A1",
      status: "maintenance",
      work_center_code: null,
      utilization_percent: 0,
      operations: [],
    },
  ],
  unscheduled: [
    {
      production_order_id: 200,
      production_order_code: "PO-2026-0100",
      production_order_status: "released",
      product_name: "Cable Organizer",
      quantity: 20,
      priority: 2,
      due_date: null,
      unscheduled_operation_count: 2,
      first_unscheduled_operation: {
        id: 21,
        operation_code: "OP010",
        operation_name: "3D Print",
        sequence: 10,
        status: "pending",
        planned_setup_minutes: "0",
        planned_run_minutes: "120",
      },
    },
  ],
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(FROZEN_NOW);
  mocks.get.mockReset();
  mocks.get.mockResolvedValue(BOARD);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("helpers", () => {
  it("getWindow day mode spans exactly the anchor day", () => {
    const anchor = new Date(2026, 5, 15, 14, 30);
    const { start, end } = getWindow(anchor, "day");
    expect(start.getHours()).toBe(0);
    expect(end.getTime() - start.getTime()).toBe(24 * 3600 * 1000);
  });

  it("getWindow week mode starts Monday", () => {
    // 2026-06-17 is a Wednesday
    const { start, end } = getWindow(new Date(2026, 5, 17), "week");
    expect(start.getDay()).toBe(1); // Monday
    expect((end.getTime() - start.getTime()) / 86400000).toBe(7);
  });

  it("getWindow month mode spans the calendar month", () => {
    const { start, end } = getWindow(new Date(2026, 5, 17), "month");
    expect(start.getDate()).toBe(1);
    expect(start.getMonth()).toBe(5);
    expect(end.getMonth()).toBe(6);
  });

  it("getWindow day mode ends at local midnight across DST transitions", () => {
    // US spring-forward 2026-03-08: the day is 23h long. Millisecond math
    // (start + 24h) would land at 01:00 on 3/9; calendar math must land
    // at exactly 00:00 local regardless of the runner's timezone.
    const { end } = getWindow(new Date(2026, 2, 8), "day");
    expect(end.getHours()).toBe(0);
    expect(end.getDate()).toBe(9);
    // And fall-back (2026-11-01, 25h day) must too.
    const fall = getWindow(new Date(2026, 10, 1), "day");
    expect(fall.end.getHours()).toBe(0);
    expect(fall.end.getDate()).toBe(2);
  });

  it("pctOf clamps to [0, 100]", () => {
    const s = new Date(2026, 0, 1);
    const e = new Date(2026, 0, 2);
    expect(pctOf(new Date(2025, 11, 31), s, e)).toBe(0);
    expect(pctOf(new Date(2026, 0, 3), s, e)).toBe(100);
    expect(pctOf(new Date(2026, 0, 1, 12), s, e)).toBe(50);
  });

  it("getTicks day mode yields 12 two-hour ticks", () => {
    const { start, end } = getWindow(new Date(2026, 5, 15), "day");
    const ticks = getTicks(start, end, "day");
    expect(ticks).toHaveLength(12);
    expect(ticks[0].label).toBe("12 AM");
    expect(ticks[6].label).toBe("12 PM");
  });
});

describe("SchedulerBoard", () => {
  it("renders title, controls, lanes, and machine column", async () => {
    render(<SchedulerBoard onScheduleOperation={vi.fn()} />);

    expect(
      screen.getByRole("heading", { name: "Production Scheduler" })
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("FDM-01")).toBeInTheDocument();
    });

    // E2E contract: table with Machine header, date input, Today button,
    // view-mode select containing "Day View"
    expect(screen.getByText("Machine")).toBeInTheDocument();
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByLabelText("View mode")).toHaveValue("day");
    expect(screen.getByText("Day View")).toBeInTheDocument();
    expect(document.querySelector('input[type="date"]')).toBeTruthy();

    // Lane status text + maintenance lane present
    expect(screen.getByText("available")).toBeInTheDocument();
    expect(screen.getByText("maintenance")).toBeInTheDocument();
  });

  it("renders operation blocks positioned within the lane", async () => {
    render(<SchedulerBoard onScheduleOperation={vi.fn()} />);
    const block = await screen.findByTestId("gantt-block-11");
    expect(block).toHaveTextContent("PO-2026-0099");
    // 2h→8h on a 24h axis = left 8.33%, width 25%
    expect(parseFloat(block.style.left)).toBeCloseTo(8.33, 1);
    expect(parseFloat(block.style.width)).toBeCloseTo(25, 1);
  });

  it("clicking a block opens the scheduler modal in edit mode payload", async () => {
    const onSchedule = vi.fn();
    render(<SchedulerBoard onScheduleOperation={onSchedule} />);
    const block = await screen.findByTestId("gantt-block-11");
    fireEvent.click(block);

    expect(onSchedule).toHaveBeenCalledTimes(1);
    const [op, po] = onSchedule.mock.calls[0];
    expect(op.id).toBe(11);
    expect(op.scheduled_start).toBe(BOARD.lanes[0].operations[0].scheduled_start);
    expect(op.status).toBe("queued");
    expect(po).toEqual({ id: 100, code: "PO-2026-0099" });
  });

  it("renders the unscheduled queue and schedules its first op on click", async () => {
    const onSchedule = vi.fn();
    render(<SchedulerBoard onScheduleOperation={onSchedule} />);

    expect(await screen.findByText("Unscheduled Orders")).toBeInTheDocument();
    expect(screen.getByText("PO-2026-0100")).toBeInTheDocument();
    expect(screen.getByText(/2 ops to schedule/)).toBeInTheDocument();

    fireEvent.click(screen.getByTitle(/Auto-schedule/));
    const [op, po] = onSchedule.mock.calls[0];
    expect(op.id).toBe(21);
    expect(po).toEqual({ id: 200, code: "PO-2026-0100" });
  });

  it("switching view mode refetches with a wider window", async () => {
    render(<SchedulerBoard onScheduleOperation={vi.fn()} />);
    await screen.findByText("FDM-01");
    const callsBefore = mocks.get.mock.calls.length;

    fireEvent.change(screen.getByLabelText("View mode"), {
      target: { value: "week" },
    });

    await waitFor(() => {
      expect(mocks.get.mock.calls.length).toBeGreaterThan(callsBefore);
    });
    const lastUrl = mocks.get.mock.calls.at(-1)[0];
    const params = new URLSearchParams(lastUrl.split("?")[1]);
    const span =
      new Date(params.get("end_date")) - new Date(params.get("start_date"));
    expect(span).toBe(7 * 24 * 3600 * 1000);
  });

  it("refetches when refreshSignal bumps", async () => {
    const { rerender } = render(
      <SchedulerBoard onScheduleOperation={vi.fn()} refreshSignal={0} />
    );
    await screen.findByText("FDM-01");
    const callsBefore = mocks.get.mock.calls.length;

    rerender(<SchedulerBoard onScheduleOperation={vi.fn()} refreshSignal={1} />);
    await waitFor(() => {
      expect(mocks.get.mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("shows the error banner when the fetch fails", async () => {
    mocks.get.mockRejectedValueOnce(new Error("boom"));
    render(<SchedulerBoard onScheduleOperation={vi.fn()} />);
    expect(await screen.findByText("boom")).toBeInTheDocument();
  });
});
