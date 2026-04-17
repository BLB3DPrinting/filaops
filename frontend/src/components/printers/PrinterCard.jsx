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
  // Coerce + guard — telemetry can arrive as string, null, or garbage;
  // never render NaN to users.
  const n = Number(minutes);
  if (!Number.isFinite(n) || n <= 0) return null;
  // Round first so fractional telemetry doesn't render as "1h 30.5m".
  // Integer division naturally carries a rounded-up 60 into the hour column.
  const total = Math.round(n);
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
  if (!amsSlots?.length) return { material: "Unknown", slot: "No AMS", color: null };
  // Backend now reports `active: true` on the slot Bambu has loaded (tray_now).
  // Fall back to the first slot only when nothing is authoritatively active;
  // in that case mark the slot label "(estimated)" so operators know it's a guess.
  const activeSlot = amsSlots.find((s) => s.active) || amsSlots[0];
  const slotLabel = `Slot ${activeSlot.slot ?? 1}`;
  const isEstimated = !activeSlot.active && amsSlots.length > 1;
  return {
    material: activeSlot.material || "Unknown",
    slot: isEstimated ? `${slotLabel} (estimated)` : slotLabel,
    color: activeSlot.color || null,
  };
}

// Bambu's public wiki error-code page. Their URL format groups hex as four
// 4-digit chunks joined by underscores ("0500_0500_0001_0007") while our
// backend emits two 8-digit chunks ("05000500_00010007"). Reformat so the
// link lands on the human-readable troubleshooting page instead of the raw
// catalog dump at e.bambulab.com/query.php.
function bambuErrorUrl(hmsCode) {
  if (!hmsCode) return null;
  const clean = String(hmsCode).replace(/[_-]/g, "").toLowerCase();
  if (clean.length !== 16) return null;
  const parts = [clean.slice(0, 4), clean.slice(4, 8), clean.slice(8, 12), clean.slice(12, 16)];
  return `https://wiki.bambulab.com/en/x1/troubleshooting/hmscode/${parts.join("_")}`;
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
  // Coerce + clamp — non-numeric telemetry (null/NaN/"--") must never leak into
  // width styles or aria-valuenow.
  const progressRaw = Number(printer.progress);
  const progress = Number.isFinite(progressRaw)
    ? Math.max(0, Math.min(100, progressRaw))
    : 0;
  const hasProgress = Number.isFinite(progressRaw);
  const eta = fmtEta(printer.remaining_minutes ?? printer.mc_remaining_time);
  const ams = getActiveAmsSlot(printer.ams_slots);

  // Surface HMI errors from Bambu MQTT telemetry. print_error is an integer
  // (0 = none); hms_codes is an array of "ATTR_CODE" hex strings. hms_descriptions
  // aligns 1:1 with hms_codes and carries the decoded message from Bambu's
  // catalog (backend-cached). Entries may be null on cache miss.
  const hmsCodes = Array.isArray(printer.hms_codes) ? printer.hms_codes : [];
  const hmsDescriptions = Array.isArray(printer.hms_descriptions)
    ? printer.hms_descriptions
    : [];
  const printError = Number(printer.print_error) || 0;
  const hasError = printError > 0 || hmsCodes.length > 0 || status === "error";
  const primaryHmsCode = hmsCodes[0] || null;
  const primaryHmsDescription = hmsDescriptions[0] || null;
  const primaryHmsWikiUrl = primaryHmsCode ? bambuErrorUrl(primaryHmsCode) : null;

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
  // Clear Error is offered whenever an HMI code is active, regardless of
  // status — the printer may be paused, failed, or idle-with-error.
  if (hasError && onCommand) {
    actions.push({
      label: "Clear Error",
      primary: false,
      onClick: () => onCommand(printer.id, "clear_error"),
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

  // Heartbeat text — an online idle printer should read "Connected" even if
  // it has a historic last_seen timestamp, so the idle check comes before the
  // last_seen fallback.
  const heartbeat = isPrinting
    ? "Live now"
    : status === "idle"
    ? "Connected"
    : printer.last_seen
    ? `Last seen ${new Date(printer.last_seen).toLocaleString()}`
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

      {/* HMI / print error banner. When the backend can resolve the HMS code
          against Bambu's catalog, the primary line is the decoded description
          with the code as a secondary label. On cache miss / offline the code
          itself becomes the primary line. "Look up" links to Bambu's wiki
          troubleshooting page using the four-chunk URL format. */}
      {hasError && (
        <div className="mb-5 rounded-2xl border border-red-500/40 bg-red-950/30 p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-xs uppercase tracking-[0.16em] text-red-300/90">
                Printer Error
              </div>
              <div className="mt-1 text-sm font-medium text-red-100">
                {primaryHmsDescription ||
                  (primaryHmsCode
                    ? `HMS ${primaryHmsCode}`
                    : printError
                    ? `Print error ${printError}`
                    : "Printer reported an error")}
              </div>
              {primaryHmsDescription && primaryHmsCode && (
                <div className="mt-1 font-mono text-xs text-red-300/70">
                  HMS {primaryHmsCode}
                </div>
              )}
              {hmsCodes.length > 1 && (
                <div className="mt-1 text-xs text-red-300/80">
                  +{hmsCodes.length - 1} additional code{hmsCodes.length > 2 ? "s" : ""}
                </div>
              )}
            </div>
            {primaryHmsWikiUrl && (
              <a
                href={primaryHmsWikiUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="shrink-0 rounded-lg border border-red-500/40 px-2.5 py-1 text-xs font-medium text-red-200 transition hover:border-red-400/60 hover:bg-red-500/10"
              >
                Look up ↗
              </a>
            )}
          </div>
        </div>
      )}

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
            {hasProgress && (
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

      {/* Metric tiles — the Filament tile shows a color swatch next to the
          material name when the AMS reports one (Bambu sends RGBA hex). */}
      <div className="grid grid-cols-2 gap-3">
        <Metric label="Nozzle" value={fmtTemp(printer.nozzle_temp)} />
        <Metric label="Bed" value={fmtTemp(printer.bed_temp)} />
        <Metric label="Filament" value={ams.material} swatchColor={ams.color} />
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

function Metric({ label, value, swatchColor }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/80 p-3">
      <div className="text-[11px] uppercase tracking-[0.16em] text-slate-500">
        {label}
      </div>
      <div className="mt-2 flex items-center gap-2 text-sm font-medium text-slate-100">
        {swatchColor && (
          <span
            aria-hidden="true"
            className="inline-block h-3.5 w-3.5 shrink-0 rounded-full border border-white/20 shadow-inner"
            style={{ backgroundColor: swatchColor }}
          />
        )}
        <span className="truncate">{value}</span>
      </div>
    </div>
  );
}
