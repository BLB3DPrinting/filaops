/**
 * Live printer status for the printers page.
 *
 * When FilaOps PRO's FilaFarm is installed, AdminPrinters merges its live
 * telemetry over each Core printer row. PRO adds `state` and `state_label`
 * derived from the printer's own reports, for example "preparing" while it
 * heats and levels, "needs_clearing" after a job, or "error" with the code
 * ("Paused · 1200_1000_0002_0002"). Without PRO, or for a printer PRO doesn't
 * know, these fall back to Core's `status`.
 */

const STATE_WORDS = {
  needs_clearing: "needs clearing",
};

/**
 * Overlay PRO's live telemetry on Core's printer rows, matched by ID.
 *
 * Core returns numeric IDs and PRO returns strings, so they're matched as
 * strings, and Core's own `id` is kept: other parts of the page (e.g.
 * maintenance logs' `printer_id`) look printers up by the numeric ID.
 */
export function mergeLiveTelemetry(corePrinters, proPrinters) {
  const live = new Map((proPrinters || []).map((p) => [String(p.id), p]));
  return corePrinters.map((p) => {
    const telemetry = live.get(String(p.id));
    return telemetry ? { ...p, ...telemetry, id: p.id } : p;
  });
}

/** Key for status colours: Core's status, except that a live error is "error". */
export function statusKey(printer) {
  if (printer?.state === "error") return "error";
  return (printer?.status || "offline").toLowerCase();
}

/** Short state for badges: "preparing", "needs clearing", ... */
export function stateWord(printer) {
  if (printer?.state) return STATE_WORDS[printer.state] || printer.state;
  return statusKey(printer);
}

/** Full state text, e.g. "Printing 23%" or "Paused · 1200_1000_0002_0002". */
export function statusText(printer) {
  return printer?.state_label || stateWord(printer);
}

/** "0.6 mm hardened steel" from PRO's `nozzle`, or null. */
export function nozzleText(printer) {
  const nozzle = printer?.nozzle;
  if (!nozzle) return null;
  const size = Number(nozzle.diameter_mm);
  const parts = [];
  if (Number.isFinite(size) && size > 0) parts.push(`${size} mm`);
  if (nozzle.type) parts.push(String(nozzle.type).replace(/_/g, " "));
  return parts.length ? parts.join(" ") : null;
}
