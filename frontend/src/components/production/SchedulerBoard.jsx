/**
 * SchedulerBoard — the Scheduler (Gantt) view for AdminProduction (SCHED-5).
 *
 * Machine lanes × time axis. Day / Week / Month windows, date navigation,
 * scheduled-operation blocks (click → OperationSchedulerModal in edit mode),
 * running operations highlighted, maintenance/offline lanes tinted, and an
 * Unscheduled Orders work queue whose items open the scheduler modal for
 * their first unscheduled operation.
 *
 * READ-ONLY by design: no drag-and-drop in v1 (deferred per plan v3).
 *
 * Data: GET /api/v1/scheduling/board?start_date&end_date — one call returns
 * all lanes (machine Resources + Printers; operations may be scheduled on
 * either) plus the unscheduled queue. See scheduling.py::get_scheduler_board.
 *
 * Props:
 *   onScheduleOperation(operation, productionOrder) — open the scheduler
 *     modal (parent owns the modal instance so Queue view can share it).
 *   refreshSignal — increment to force a refetch (parent bumps it after the
 *     modal schedules/reschedules something).
 */
import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { useApi } from "../../hooks/useApi";
import { parseDateTime } from "../../utils/formatting";

/**
 * Local midnight N days after the given date. Uses calendar arithmetic
 * (Date handles month/year rollover) — NOT millisecond math, which lands
 * an hour off on DST transition days (23h/25h days).
 */
function addDays(d, n) {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
}

/** Window [start, end) for the given anchor date + view mode, local time. */
export function getWindow(anchor, viewMode) {
  const d = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate());
  if (viewMode === "day") {
    return { start: d, end: addDays(d, 1) };
  }
  if (viewMode === "week") {
    // Monday-start week
    const dow = (d.getDay() + 6) % 7;
    const monday = addDays(d, -dow);
    return { start: monday, end: addDays(monday, 7) };
  }
  // month
  const first = new Date(d.getFullYear(), d.getMonth(), 1);
  const next = new Date(d.getFullYear(), d.getMonth() + 1, 1);
  return { start: first, end: next };
}

/** Percent position of time t inside [start, end], clamped to [0, 100]. */
export function pctOf(t, start, end) {
  const span = end.getTime() - start.getTime();
  if (span <= 0) return 0;
  const raw = ((t.getTime() - start.getTime()) / span) * 100;
  return Math.max(0, Math.min(100, raw));
}

/** Tick marks for the window: { pct, label } */
export function getTicks(start, end, viewMode) {
  const ticks = [];
  if (viewMode === "day") {
    for (let h = 0; h < 24; h += 2) {
      const t = new Date(start.getTime() + h * 3600 * 1000);
      const label =
        h === 0 ? "12 AM" : h < 12 ? `${h} AM` : h === 12 ? "12 PM" : `${h - 12} PM`;
      ticks.push({ pct: pctOf(t, start, end), label });
    }
    return ticks;
  }
  // Walk day-by-day with calendar arithmetic so each tick lands on local
  // midnight even across DST transitions.
  const labelEveryFor = (days) => (viewMode === "week" ? 1 : days > 20 ? 5 : 2);
  const totalDays = Math.round(
    (end.getTime() - start.getTime()) / (24 * 3600 * 1000)
  );
  const labelEvery = labelEveryFor(totalDays);
  for (let i = 0, t = start; t < end; i++, t = addDays(start, i)) {
    const label =
      i % labelEvery === 0
        ? t.toLocaleDateString(undefined, {
            weekday: viewMode === "week" ? "short" : undefined,
            month: "numeric",
            day: "numeric",
          })
        : "";
    ticks.push({ pct: pctOf(t, start, end), label });
  }
  return ticks;
}

const BLOCK_STYLES = {
  in_progress: "bg-green-600/80 border-green-400 text-white",
  queued: "bg-blue-600/70 border-blue-400 text-white",
  scheduled: "bg-blue-600/70 border-blue-400 text-white",
  pending: "bg-gray-600/70 border-gray-500 text-gray-200",
  on_hold: "bg-amber-600/70 border-amber-400 text-white",
};

const LANE_STATUS_STYLES = {
  maintenance: "text-amber-400",
  offline: "text-gray-500",
  busy: "text-green-400",
  printing: "text-green-400",
  available: "text-blue-300",
  idle: "text-blue-300",
};

function toLocalDateInput(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function OperationBlock({ op, windowStart, windowEnd, onClick }) {
  // Backend sends naive-UTC timestamps; parseDateTime appends 'Z' so the
  // block lands at the right LOCAL position (same convention as formatTime).
  const start = parseDateTime(op.scheduled_start);
  const end = parseDateTime(op.scheduled_end);
  const left = pctOf(start, windowStart, windowEnd);
  const right = pctOf(end, windowStart, windowEnd);
  const width = Math.max(right - left, 0.6);
  const style = BLOCK_STYLES[op.status] || BLOCK_STYLES.pending;

  const fmt = (d) =>
    d.toLocaleString(undefined, {
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });

  return (
    <button
      type="button"
      data-testid={`gantt-block-${op.id}`}
      onClick={onClick}
      title={`${op.production_order_code} · ${op.operation_name || op.operation_code}\n${
        op.product_name || ""
      }\n${fmt(start)} → ${fmt(end)} · ${op.status.replace(/_/g, " ")}`}
      className={`absolute top-1.5 bottom-1.5 rounded border px-1 overflow-hidden text-left transition-opacity hover:opacity-80 focus:outline-none focus:ring-1 focus:ring-white/60 ${style}`}
      style={{ left: `${left}%`, width: `${width}%` }}
    >
      <span className="block text-[10px] font-medium leading-tight truncate">
        {op.production_order_code}
      </span>
      <span className="block text-[9px] opacity-80 leading-tight truncate">
        {op.operation_name || op.operation_code}
      </span>
    </button>
  );
}

// SCHED-7: shared stripe pattern for maintenance blocks (amber diagonal).
const MAINTENANCE_STRIPES =
  "repeating-linear-gradient(135deg, rgba(245, 158, 11, 0.28) 0 6px, rgba(245, 158, 11, 0.08) 6px 12px)";

function MaintenanceWindowBlock({ win, windowStart, windowEnd }) {
  // Same naive-UTC convention as OperationBlock.
  const start = parseDateTime(win.starts_at);
  const end = parseDateTime(win.ends_at);
  const left = pctOf(start, windowStart, windowEnd);
  const right = pctOf(end, windowStart, windowEnd);
  const width = Math.max(right - left, 0.6);

  const fmt = (d) =>
    d.toLocaleString(undefined, {
      month: "numeric",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });

  return (
    <div
      data-testid={`gantt-window-${win.id}`}
      title={`Maintenance — ${win.reason || "scheduled downtime"}\n${fmt(start)} → ${fmt(
        end
      )} · ${win.status.replace(/_/g, " ")}`}
      className={`absolute top-0 bottom-0 rounded-sm border-x border-amber-500/50 ${
        win.status === "completed" ? "opacity-40" : ""
      }`}
      style={{
        left: `${left}%`,
        width: `${width}%`,
        backgroundImage: MAINTENANCE_STRIPES,
      }}
    />
  );
}

export default function SchedulerBoard({ onScheduleOperation, refreshSignal = 0 }) {
  const api = useApi();
  const [viewMode, setViewMode] = useState("day");
  const [anchor, setAnchor] = useState(() => new Date());
  const [board, setBoard] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const { start, end } = useMemo(() => getWindow(anchor, viewMode), [anchor, viewMode]);

  // Guards against out-of-order responses: rapid view/date changes can have
  // several /board requests in flight, and only the latest may paint.
  const fetchSeq = useRef(0);

  const fetchBoard = useCallback(async () => {
    const seq = ++fetchSeq.current;
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        start_date: start.toISOString(),
        end_date: end.toISOString(),
      });
      const data = await api.get(`/api/v1/scheduling/board?${params}`);
      if (seq !== fetchSeq.current) return; // stale response — a newer fetch won
      setBoard(data);
    } catch (err) {
      if (seq !== fetchSeq.current) return;
      setError(err.message || "Failed to load schedule");
    } finally {
      if (seq === fetchSeq.current) setLoading(false);
    }
  }, [api, start, end]);

  useEffect(() => {
    fetchBoard();
  }, [fetchBoard, refreshSignal]);

  const ticks = useMemo(() => getTicks(start, end, viewMode), [start, end, viewMode]);

  const now = new Date();
  const nowPct = now >= start && now <= end ? pctOf(now, start, end) : null;

  const shift = (dir) => {
    if (viewMode === "day") {
      setAnchor((a) => addDays(a, dir));
    } else if (viewMode === "week") {
      setAnchor((a) => addDays(a, dir * 7));
    } else {
      setAnchor((a) => new Date(a.getFullYear(), a.getMonth() + dir, 1));
    }
  };

  const handleBlockClick = (op) => {
    // The modal derives edit-mode from the op's status/scheduled_start.
    onScheduleOperation?.(
      {
        id: op.id,
        operation_code: op.operation_code,
        operation_name: op.operation_name,
        sequence: op.sequence,
        status: op.status,
        scheduled_start: op.scheduled_start,
        scheduled_end: op.scheduled_end,
        planned_setup_minutes: op.planned_setup_minutes,
        planned_run_minutes: op.planned_run_minutes,
      },
      { id: op.production_order_id, code: op.production_order_code }
    );
  };

  const handleUnscheduledClick = (item) => {
    onScheduleOperation?.(item.first_unscheduled_operation, {
      id: item.production_order_id,
      code: item.production_order_code,
    });
  };

  const lanes = board?.lanes || [];
  const unscheduled = board?.unscheduled || [];

  return (
    <div className="space-y-4" data-testid="scheduler-board">
      {/* Header: title + controls */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <h2 className="text-xl font-semibold text-white">Production Scheduler</h2>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={viewMode}
            onChange={(e) => setViewMode(e.target.value)}
            className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-3 py-1.5"
            aria-label="View mode"
          >
            <option value="day">Day View</option>
            <option value="week">Week View</option>
            <option value="month">Month View</option>
          </select>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => shift(-1)}
              className="px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:text-white text-sm"
              aria-label="Previous"
            >
              ‹
            </button>
            <input
              type="date"
              value={toLocalDateInput(anchor)}
              onChange={(e) => {
                const [y, m, d] = e.target.value.split("-").map(Number);
                if (y && m && d) setAnchor(new Date(y, m - 1, d));
              }}
              className="bg-gray-800 border border-gray-700 text-white text-sm rounded-lg px-2 py-1.5"
            />
            <button
              type="button"
              onClick={() => shift(1)}
              className="px-2 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:text-white text-sm"
              aria-label="Next"
            >
              ›
            </button>
          </div>
          <button
            type="button"
            onClick={() => setAnchor(new Date())}
            className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-gray-300 hover:text-white text-sm"
          >
            Today
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-blue-600/70 border border-blue-400" />
          Scheduled
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-green-600/80 border border-green-400" />
          Running
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-amber-600/70 border border-amber-400" />
          On hold
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="w-3 h-3 rounded-sm border border-amber-500/50"
            style={{ backgroundImage: MAINTENANCE_STRIPES }}
          />
          Maintenance
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-0.5 h-3 bg-red-500" />
          Now
        </span>
      </div>

      {error && (
        <div className="p-3 bg-red-900/20 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Gantt table */}
        <div className="xl:col-span-3 bg-gray-900 border border-gray-800 rounded-xl overflow-x-auto">
          {loading && !board ? (
            <div className="h-48 flex items-center justify-center">
              <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
            </div>
          ) : lanes.length === 0 ? (
            <div className="p-8 text-center text-gray-500 text-sm">
              No machines found. Add printers or machine work-center resources to
              see the schedule.
            </div>
          ) : (
            <table className="w-full min-w-[640px]">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left p-3 text-xs font-semibold text-gray-400 uppercase tracking-wider w-44">
                    Machine
                  </th>
                  <th className="p-0 relative h-8">
                    {/* Time axis labels */}
                    <div className="absolute inset-0">
                      {ticks.map((t, i) => (
                        <span
                          key={i}
                          className="absolute top-1/2 -translate-y-1/2 text-[10px] font-normal text-gray-500 whitespace-nowrap"
                          style={{ left: `${t.pct}%` }}
                        >
                          {t.label}
                        </span>
                      ))}
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                {lanes.map((lane) => {
                  const laneStatus =
                    LANE_STATUS_STYLES[lane.status] || "text-gray-400";
                  const laneTint =
                    lane.status === "maintenance"
                      ? "bg-amber-950/20"
                      : lane.status === "offline"
                      ? "bg-gray-950/40"
                      : "";
                  return (
                    <tr
                      key={lane.key}
                      className={`border-b border-gray-800/60 ${laneTint}`}
                      data-testid={`gantt-lane-${lane.key}`}
                    >
                      <td className="p-3 align-middle">
                        <div className="text-sm text-white font-medium truncate">
                          {lane.code}
                        </div>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs capitalize ${laneStatus}`}>
                            {lane.status}
                          </span>
                          {lane.work_center_code && (
                            <span className="text-[10px] text-gray-600">
                              {lane.work_center_code}
                            </span>
                          )}
                        </div>
                        {/* Utilization bar */}
                        <div
                          className="mt-1.5 h-1 bg-gray-800 rounded overflow-hidden"
                          title={`${lane.utilization_percent}% booked in window`}
                        >
                          <div
                            className={`h-full ${
                              lane.utilization_percent > 85
                                ? "bg-red-500/80"
                                : lane.utilization_percent > 60
                                ? "bg-amber-500/80"
                                : "bg-blue-500/70"
                            }`}
                            style={{ width: `${lane.utilization_percent}%` }}
                          />
                        </div>
                      </td>
                      <td className="p-0 relative h-14">
                        {/* Vertical gridlines */}
                        {ticks.map((t, i) => (
                          <div
                            key={i}
                            className="absolute top-0 bottom-0 w-px bg-gray-800/70"
                            style={{ left: `${t.pct}%` }}
                          />
                        ))}
                        {/* Now line */}
                        {nowPct !== null && (
                          <div
                            className="absolute top-0 bottom-0 w-0.5 bg-red-500/80 z-10 pointer-events-none"
                            style={{ left: `${nowPct}%` }}
                            data-testid="now-line"
                          />
                        )}
                        {/* Maintenance window blocks (SCHED-7) — render
                            BEFORE operation blocks so ops paint above and
                            stay clickable; windows are non-operational
                            background blocks (no click-through). */}
                        {(lane.windows || []).map((win) => (
                          <MaintenanceWindowBlock
                            key={`win-${win.id}`}
                            win={win}
                            windowStart={start}
                            windowEnd={end}
                          />
                        ))}
                        {/* Operation blocks */}
                        {lane.operations.map((op) => (
                          <OperationBlock
                            key={op.id}
                            op={op}
                            windowStart={start}
                            windowEnd={end}
                            onClick={() => handleBlockClick(op)}
                          />
                        ))}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Unscheduled orders work queue */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-sm font-semibold text-white mb-3">
            Unscheduled Orders
            {unscheduled.length > 0 && (
              <span className="ml-2 px-2 py-0.5 bg-amber-500/20 text-amber-400 text-xs rounded-full">
                {unscheduled.length}
              </span>
            )}
          </h3>
          {unscheduled.length === 0 ? (
            <p className="text-xs text-gray-500">
              Everything released is on the board. Nice.
            </p>
          ) : (
            <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1">
              {unscheduled.map((item) => (
                <div
                  key={item.production_order_id}
                  className="bg-gray-800 rounded-lg p-2.5 flex items-start justify-between gap-2"
                  data-testid={`unscheduled-${item.production_order_code}`}
                >
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-white truncate">
                      {item.production_order_code}
                    </div>
                    <div className="text-[11px] text-gray-400 truncate">
                      {item.product_name}
                    </div>
                    <div className="text-[10px] text-gray-500">
                      Qty {item.quantity}
                      {item.due_date &&
                        ` · due ${new Date(item.due_date).toLocaleDateString()}`}
                      {` · ${item.unscheduled_operation_count} op${
                        item.unscheduled_operation_count === 1 ? "" : "s"
                      } to schedule`}
                    </div>
                  </div>
                  <button
                    type="button"
                    title="Auto-schedule — pick a slot for the next operation"
                    onClick={() => handleUnscheduledClick(item)}
                    className="shrink-0 px-2 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded transition-colors"
                  >
                    ⚡ Schedule
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
