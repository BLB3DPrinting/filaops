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
// Industrial Workbench tokens (#846): consumed ONLY by the re-skinned
// ProductionOrderDetail page (verified) — the other maps in this file still
// serve un-migrated dark pages and keep the legacy palette.
export const PRODUCTION_ORDER_COLORS = {
  draft: "bg-[var(--paper-sunk)] text-[var(--ink-3)]",
  released: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
  scheduled: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
  in_progress: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
  complete: "bg-[var(--status-green-tint)] text-[var(--status-green)]",
  completed: "bg-[var(--status-green-tint)] text-[var(--status-green)]",
  closed: "bg-[var(--status-green-tint)] text-[var(--status-green)]",
  qc_hold: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
  scrapped: "bg-[var(--status-red-tint)] text-[var(--status-red)]",
  on_hold: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
  short: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
  cancelled: "bg-[var(--paper-sunk)] text-[var(--ink-4)]",
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
// Industrial Workbench tokens (#846): consumed ONLY by the re-skinned
// production components (ProductionQueueList, ProductionOrderModal) —
// verified before tokenizing, since the rest of this file still serves
// un-migrated dark pages. Mapping follows ProductionStatusCards:
// active-ish → amber, done → green, destroyed → red, inert → neutral.
export const PRODUCTION_ORDER_BADGE_CONFIGS = {
  draft: { bg: "bg-[var(--paper-sunk)]", text: "text-[var(--ink-3)]", label: "Draft" },
  released: { bg: "bg-[var(--status-amber-tint)]", text: "text-[var(--status-amber)]", label: "Released" },
  scheduled: { bg: "bg-[var(--status-amber-tint)]", text: "text-[var(--status-amber)]", label: "Scheduled" },
  in_progress: { bg: "bg-[var(--status-amber-tint)]", text: "text-[var(--status-amber)]", label: "In Progress" },
  complete: { bg: "bg-[var(--status-green-tint)]", text: "text-[var(--status-green)]", label: "Complete" },
  completed: { bg: "bg-[var(--status-green-tint)]", text: "text-[var(--status-green)]", label: "Complete" },
  closed: { bg: "bg-[var(--status-green-tint)]", text: "text-[var(--status-green)]", label: "Closed" },
  short: { bg: "bg-[var(--status-amber-tint)]", text: "text-[var(--status-amber)]", label: "Short" },
  qc_hold: { bg: "bg-[var(--status-amber-tint)]", text: "text-[var(--status-amber)]", label: "QC Hold" },
  on_hold: { bg: "bg-[var(--status-amber-tint)]", text: "text-[var(--status-amber)]", label: "On Hold" },
  scrapped: { bg: "bg-[var(--status-red-tint)]", text: "text-[var(--status-red)]", label: "Scrapped" },
  cancelled: { bg: "bg-[var(--status-red-tint)]", text: "text-[var(--status-red)]", label: "Cancelled" },
};

// ── Helper ──────────────────────────────────────────────────────────
// Look up a status in a color map with a sensible fallback.
export function getStatusColor(colorMap, status, fallback) {
  return colorMap[status] || fallback || BASE_COLORS.gray;
}
