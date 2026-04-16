/**
 * PrinterCard — Rich printer card for the fleet dashboard.
 *
 * Replaces the old inline-styled PrinterCardHUD with a Tailwind-based
 * design featuring metric tiles, job details, contextual actions, and
 * gradient borders for active printers. Consumes the merged printer
 * data from fetchPrinters() (Core + PRO telemetry overlay).
 *
 * Props:
 *   printer        — Merged printer object (Core fields + PRO telemetry when available)
 *   onEdit         — (printer) => void
 *   onCommand      — (printerId, command) => void | undefined (PRO fleet control)
 *   onTest         — (printer) => void
 *   testing        — boolean (is this printer currently being connection-tested)
 *   commandPending — boolean (is a fleet command currently in-flight for this printer)
 */
import { brandLabels } from "./constants";

const STATUS_STYLES = {
  printing:
    "bg-emerald-500/15 text-emerald-300 ring-1 ring-inset ring-emerald-400/30",
  idle: "bg-blue-500/15 text-blue-300 ring-1 ring-inset ring-blue-400/30",
  offline:
    "bg-slate-500/15 text-slate-300 ring-1 ring-inset ring-slate-400/20",
  maintenance:
    "bg-amber-500/15 text-amber-300 ring-1 ring-inset ring-amber-400/30",
  error: "bg-red-500/15 text-red-300 ring-1 ring-inset ring-red-400/30",
  paused:
    "bg-yellow-500/15 text-yellow-300 ring-1 ring-inset ring-yellow-400/30",
  unknown:
    "bg-slate-500/15 text-slate-400 ring-1 ring-inset ring-slate-400/20",
};

const PROGRESS_COLORS = {
  printing: "bg-emerald-400",
  paused: "bg-yellow-400",
  error: "bg-red-400",
};

function fmtTemp(value) {
  if (value == null || value === 0) return "—";
  return `${Math.round(value)}°C`;
}

function fmtEta(minutes) {
  if (minutes == null || minutes <= 0) return null;
  // Round first so fractional telemetry doesn't render as "1h 30.5m".
  // Integer division naturally carries a rounded-up 60 into the hour column.
  const total = Math.round(minutes);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function stateLabel(status) {
  if (status === "offline") return "Not responding";
  if (status === "maintenance") return "Service attention needed";
  if (status === "error") return "Error — check printer";
  return "Ready";
}

function getActiveAmsSlot(amsSlots) {
  if (!amsSlots?.length) return { material: "Unknown", slot: "No AMS" };
  // TODO: BambuFleetManager should report the active slot index.
  // For now, show the first slot's material as a reasonable default.
  const active = amsSlots[0];
  return {
    material: active.material || "Unknown",
    slot: `Slot ${active.slot ?? 1}`,
  };
}

export default function PrinterCard({
  printer,
  onEdit,
  onCommand,
  onTest,
  testing,
  commandPending,
}) {
  const status = (printer.status || "offline").toLowerCase();
  const isActive = status === "printing" || status === "paused";
  const isPrinting = status === "printing";
  const progress = Math.max(0, Math.min(100, Number(printer.progress ?? 0)));
  const eta = fmtEta(printer.remaining_minutes ?? printer.mc_remaining_time);
  const ams = getActiveAmsSlot(printer.ams_slots);

  // Build contextual actions based on printer state.
  // While a command is in-flight for this printer, disable pause/resume/cancel
  // so a double-click can't fire duplicate requests.
  const actions = [];
  if (isPrinting && onCommand) {
    actions.push({
      label: "Pause",
      primary: true,
      onClick: () => onCommand(printer.id, "pause"),
      disabled: commandPending,
    });
  }
  if (status === "paused" && onCommand) {
    actions.push({
      label: "Resume",
      primary: true,
      onClick: () => onCommand(printer.id, "resume"),
      disabled: commandPending,
    });
  }
  if (isActive && onCommand) {
    actions.push({
      label: "Cancel",
      primary: false,
      onClick: () => onCommand(printer.id, "cancel"),
      disabled: commandPending,
    });
  }
  if (status === "offline") {
    // Disable Test when printer has no IP — there's nothing to probe.
    const hasIp = Boolean(printer.ip_address);
    actions.push({
      label: "Test",
      primary: true,
      onClick: () => onTest?.(printer),
      disabled: testing || !hasIp,
      title: hasIp ? undefined : "Add an IP address to test this printer",
    });
  }
  actions.push({ label: "Edit", primary: false, onClick: () => onEdit?.(printer) });

  // Heartbeat text
  const heartbeat = isPrinting
    ? "Live now"
    : printer.last_seen
    ? `Last seen ${new Date(printer.last_seen).toLocaleString()}`
    : status === "idle"
    ? "Connected"
    : "—";

  return (
    <article
      className={`rounded-[28px] border p-5 shadow-2xl shadow-black/20 transition hover:-translate-y-0.5 ${
        isPrinting
          ? "border-emerald-500/30 bg-gradient-to-br from-slate-900 via-slate-900 to-emerald-950/30"
          : status === "error"
          ? "border-red-500/30 bg-gradient-to-br from-slate-900 via-slate-900 to-red-950/20"
          : "border-slate-800 bg-slate-900/75"
      }`}
    >
      {/* Header: name + status badge */}
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">{printer.name}</h2>
          <div className="mt-1 text-sm text-slate-400">
            {brandLabels[printer.brand] || printer.brand} {printer.model}
            {printer.location && ` • ${printer.location}`}
          </div>
        </div>
        <span
          className={`shrink-0 rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${
            STATUS_STYLES[status] || STATUS_STYLES.unknown
          }`}
        >
          {status}
        </span>
      </div>

      {/* Job section — active job UI is driven by status (printing/paused), not by
          the presence of telemetry. Progress bar renders only when progress is reported. */}
      <div className="mb-5 rounded-2xl border border-slate-800/80 bg-slate-950/80 p-4">
        {isActive ? (
          <>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
                  Current Job
                </div>
                <div className="mt-1 text-sm font-medium text-white">
                  {printer.current_job || (isPrinting ? "Printing" : "Paused")}
                </div>
              </div>
              {eta && (
                <div className="text-right">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
                    ETA
                  </div>
                  <div className="mt-1 text-sm font-medium text-slate-200">
                    {eta}
                  </div>
                </div>
              )}
            </div>
            {printer.progress != null && (
              <div className="mt-4">
                <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
                  <span>Progress</span>
                  <span>{progress}%</span>
                </div>
                <div
                  className="h-2.5 rounded-full bg-slate-800"
                  role="progressbar"
                  aria-valuenow={progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className={`h-2.5 rounded-full transition-all duration-1000 ${
                      PROGRESS_COLORS[status] || "bg-slate-500"
                    }`}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs uppercase tracking-[0.16em] text-slate-500">
                  Current State
                </div>
                <div className="mt-1 text-sm font-medium text-white">
                  {stateLabel(status)}
                </div>
              </div>
              <div className="text-right text-sm text-slate-400">
                {heartbeat}
              </div>
            </div>
            <div className="mt-4 rounded-2xl border border-dashed border-slate-800 px-3 py-3 text-sm text-slate-400">
              No active print job.
            </div>
          </>
        )}
      </div>

      {/* Metric tiles */}
      <div className="grid grid-cols-2 gap-3">
        <Metric label="Nozzle" value={fmtTemp(printer.nozzle_temp)} />
        <Metric label="Bed" value={fmtTemp(printer.bed_temp)} />
        <Metric label="Filament" value={ams.material} />
        <Metric label="Feed" value={ams.slot} />
      </div>

      {/* Footer: heartbeat + actions */}
      <div className="mt-5 flex items-center justify-between gap-3 border-t border-slate-800 pt-4">
        <div className="text-sm text-slate-500">{heartbeat}</div>
        <div className="flex gap-2">
          {actions.map((action) => {
            // "Testing..." busy label only when actually probing — a Test button
            // disabled because IP is missing should still read "Test".
            const busyLabel = action.label === "Test" && testing ? "Testing..." : action.label;
            return (
              <button
                key={action.label}
                onClick={action.onClick}
                disabled={action.disabled}
                title={action.title}
                className={`rounded-xl px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
                  action.primary
                    ? "bg-white text-slate-950 hover:bg-slate-200"
                    : "border border-slate-700 bg-slate-900 text-slate-200 hover:border-slate-600 hover:bg-slate-800"
                }`}
              >
                {busyLabel}
              </button>
            );
          })}
        </div>
      </div>
    </article>
  );
}

function Metric({ label, value }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-3">
      <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
        {label}
      </div>
      <div className="mt-2 text-sm font-medium text-slate-100">{value}</div>
    </div>
  );
}
