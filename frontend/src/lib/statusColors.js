// Shared status-to-badge-class mappings (static for Tailwind purge safety)
//
// DEPRECATED (UX epic #808): prefer the per-axis descriptor registry +
// <StatusBadge model field value /> in src/lib/statusDescriptors.js. These flat
// maps can't express multi-axis status (a sales order has 4 status axes) and
// drift per screen. Kept for the Tailwind-purge-safe class strings still used
// by un-migrated callers; migrate opportunistically per workbench.
//
// Each domain (sales orders, production, purchasing, etc.) has its own
// status vocabulary, but the visual palette is consistent: bg-X-500/20
// with text-X-400.  Domain-specific maps re-export or extend these base
// colors so every badge in the app looks uniform.

// ── Base colour tokens ──────────────────────────────────────────────
// Keyed by semantic colour name so domain maps stay readable.
export const BASE_COLORS = {
  gray: "bg-gray-500/20 text-gray-400",
  yellow: "bg-yellow-500/20 text-yellow-400",
  blue: "bg-blue-500/20 text-blue-400",
  purple: "bg-purple-500/20 text-purple-400",
  green: "bg-green-500/20 text-green-400",
  red: "bg-red-500/20 text-red-400",
  orange: "bg-orange-500/20 text-orange-400",
  cyan: "bg-cyan-500/20 text-cyan-400",
};

// ── Sales order statuses ────────────────────────────────────────────
export const SALES_ORDER_COLORS = {
  pending: BASE_COLORS.yellow,
  confirmed: BASE_COLORS.blue,
  in_production: BASE_COLORS.purple,
  ready_to_ship: BASE_COLORS.cyan,
  shipped: BASE_COLORS.green,
  completed: BASE_COLORS.green,
  cancelled: BASE_COLORS.red,
};

// ── Production order statuses ───────────────────────────────────────
export const PRODUCTION_ORDER_COLORS = {
  draft: BASE_COLORS.gray,
  released: BASE_COLORS.blue,
  in_progress: BASE_COLORS.purple,
  complete: BASE_COLORS.green,
  scrapped: BASE_COLORS.red,
  on_hold: BASE_COLORS.yellow,
  short: BASE_COLORS.orange,
  cancelled: BASE_COLORS.gray,
};

// ── Purchase order statuses ─────────────────────────────────────────
export const PURCHASE_ORDER_COLORS = {
  draft: BASE_COLORS.gray,
  ordered: BASE_COLORS.blue,
  shipped: BASE_COLORS.purple,
  received: BASE_COLORS.green,
  closed: "bg-green-700/20 text-green-300",
  cancelled: BASE_COLORS.red,
};

// ── Payment statuses ────────────────────────────────────────────────
export const PAYMENT_COLORS = {
  completed: BASE_COLORS.green,
  pending: BASE_COLORS.yellow,
  failed: BASE_COLORS.red,
  voided: BASE_COLORS.gray,
};

// ── Spool statuses ──────────────────────────────────────────────────
export const SPOOL_COLORS = {
  active: BASE_COLORS.green,
  empty: BASE_COLORS.gray,
  expired: BASE_COLORS.red,
  damaged: BASE_COLORS.orange,
};

// ── Printer statuses ────────────────────────────────────────────────
export const PRINTER_COLORS = {
  offline: BASE_COLORS.gray,
  idle: BASE_COLORS.green,
  printing: BASE_COLORS.blue,
  paused: BASE_COLORS.yellow,
  error: BASE_COLORS.red,
  maintenance: BASE_COLORS.orange,
};

// ── Production order badge configs (with labels) ────────────────────
// Used by StatusBadge components that need both class and display text.
export const PRODUCTION_ORDER_BADGE_CONFIGS = {
  draft: { bg: "bg-gray-500/20", text: "text-gray-400", label: "Draft" },
  released: { bg: "bg-blue-500/20", text: "text-blue-400", label: "Released" },
  in_progress: { bg: "bg-purple-500/20", text: "text-purple-400", label: "In Progress" },
  complete: { bg: "bg-green-500/20", text: "text-green-400", label: "Complete" },
  short: { bg: "bg-orange-500/20", text: "text-orange-400", label: "Short" },
  cancelled: { bg: "bg-red-500/20", text: "text-red-400", label: "Cancelled" },
};

// ── Helper ──────────────────────────────────────────────────────────
// Look up a status in a color map with a sensible fallback.
export function getStatusColor(colorMap, status, fallback) {
  return colorMap[status] || fallback || BASE_COLORS.gray;
}
