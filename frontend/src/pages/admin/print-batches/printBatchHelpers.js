// Small helpers shared by the print-batch pages (FilaOps PRO, print batches S9).

export const BATCH_API = "/api/v1/pro/print-batches";

/** One row per part on the plate, with its planned copies. */
export function partsOnPlate(members) {
  const parts = new Map();
  for (const m of members || []) {
    const part = parts.get(m.product_id) || {
      product_id: m.product_id,
      name: m.name || m.sku || `Part ${m.product_id}`,
      planned: 0,
    };
    part.planned += m.quantity;
    parts.set(m.product_id, part);
  }
  return [...parts.values()];
}

/**
 * A Core printer's model as PRO's printer catalogue names it ("Bambu Lab
 * P1S" -> "P1S", "Bambu Lab X1 Carbon" -> "X1C"). PRO checks the name again.
 */
export function printerModelKey(model) {
  const name = String(model || "").replace(/^bambu\s*lab\s*/i, "").trim();
  return /^x1\s*carbon$/i.test(name) ? "X1C" : name;
}

/** "1h 5m" from minutes. */
export function formatMinutes(minutes) {
  if (minutes == null) return "—";
  const total = Math.round(Number(minutes));
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h}h ${m}m` : `${m}m`;
}

/** Tailwind classes for a batch status chip. */
export const STATUS_STYLES = {
  draft: "bg-gray-700 text-gray-200",
  composed: "bg-indigo-900/60 text-indigo-200",
  scheduled: "bg-blue-900/60 text-blue-200",
  running: "bg-amber-900/60 text-amber-200",
  printed: "bg-amber-900/60 text-amber-200",
  failed: "bg-red-900/60 text-red-200",
  complete: "bg-green-900/60 text-green-200",
  cancelled: "bg-gray-800 text-gray-400",
  broken: "bg-red-900/70 text-red-100",
};
