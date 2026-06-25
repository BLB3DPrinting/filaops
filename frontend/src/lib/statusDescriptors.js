/**
 * Per-axis status descriptors (UX Foundation, epic #808).
 *
 * FilaOps status is MULTI-AXIS: a SalesOrder carries status / payment_status /
 * fulfillment_status / mrp_status; a ProductionOrder carries status + qc_status.
 * The same string can mean different things on different axes (`completed` is
 * terminal on a sales order but a production order's terminal value is
 * `complete`). A single flat status→color map can't express that, which is why
 * ~33 ad-hoc maps drifted apart.
 *
 * This registry is keyed by (model, field) → value → { label, tone, terminal }.
 * `tone` is one of the 6 Badge variants (success/warning/danger/info/neutral/
 * purple). `terminal` marks end-states (validated against status_config.py).
 *
 * Reconciliations baked in:
 *  - ProductionOrder.status canonical is `complete` (PR-0); the `completed`
 *    spelling (legacy rows / the sales-order convention) aliases to the SAME
 *    descriptor so both render identically.
 *  - `qc_hold` is a live ProductionOrder.status written by record_qc_inspection
 *    but absent from the ProductionOrderStatus enum — registered here.
 *  - `conditional` is a live qc_status accepted by the service but absent from
 *    the QCStatus enum — registered here.
 */

/** @typedef {'success'|'warning'|'danger'|'info'|'neutral'|'purple'} Tone */
/** @typedef {{ label: string, tone: Tone, terminal: boolean }} StatusDescriptor */

// Registry: model → field → value → { label, tone, terminal? }. A missing
// `terminal` means false (normalized in getDescriptor).
export const STATUS_DESCRIPTORS = {
  sales_order: {
    status: {
      pending_confirmation: { label: "Pending Confirmation", tone: "warning" },
      draft: { label: "Draft", tone: "neutral" },
      pending: { label: "Pending", tone: "warning" },
      confirmed: { label: "Confirmed", tone: "info" },
      in_production: { label: "In Production", tone: "purple" },
      ready_to_ship: { label: "Ready to Ship", tone: "info" },
      shipped: { label: "Shipped", tone: "success" },
      delivered: { label: "Delivered", tone: "success" },
      completed: { label: "Completed", tone: "success", terminal: true },
      cancelled: { label: "Cancelled", tone: "danger", terminal: true },
      on_hold: { label: "On Hold", tone: "warning" },
    },
    payment_status: {
      pending: { label: "Unpaid", tone: "warning" },
      partial: { label: "Partial", tone: "warning" },
      paid: { label: "Paid", tone: "success", terminal: true },
      refunded: { label: "Refunded", tone: "neutral", terminal: true },
      overdue: { label: "Overdue", tone: "danger" },
    },
    fulfillment_status: {
      pending: { label: "Pending", tone: "warning" },
      ready: { label: "Ready", tone: "info" },
      short_closed: { label: "Short-Closed", tone: "neutral", terminal: true },
      shipped: { label: "Shipped", tone: "success", terminal: true },
    },
    // mrp_status is currently never written (dead axis); seeded minimally so a
    // future value renders gracefully rather than blank.
    mrp_status: {
      pending: { label: "MRP Pending", tone: "warning" },
      planned: { label: "Planned", tone: "info" },
    },
  },

  production_order: {
    status: {
      draft: { label: "Draft", tone: "neutral" },
      released: { label: "Released", tone: "info" },
      in_progress: { label: "In Progress", tone: "purple" },
      on_hold: { label: "On Hold", tone: "warning" },
      short: { label: "Short", tone: "warning" },
      complete: { label: "Complete", tone: "success", terminal: true },
      // alias of `complete` (legacy / sales-order spelling) — see PR-0.
      completed: { label: "Complete", tone: "success", terminal: true },
      qc_hold: { label: "QC Hold", tone: "warning" },
      scrapped: { label: "Scrapped", tone: "danger", terminal: true },
      cancelled: { label: "Cancelled", tone: "danger", terminal: true },
      split: { label: "Split", tone: "neutral", terminal: true },
    },
    qc_status: {
      not_required: { label: "Not Required", tone: "neutral", terminal: true },
      pending: { label: "QC Pending", tone: "warning" },
      passed: { label: "Passed", tone: "success", terminal: true },
      failed: { label: "Failed", tone: "danger" },
      waived: { label: "Waived", tone: "info", terminal: true },
      conditional: { label: "Conditional", tone: "warning" },
    },
  },

  production_order_operation: {
    status: {
      pending: { label: "Pending", tone: "neutral" },
      queued: { label: "Queued", tone: "info" },
      running: { label: "Running", tone: "purple" },
      complete: { label: "Complete", tone: "success", terminal: true },
      skipped: { label: "Skipped", tone: "neutral", terminal: true },
    },
  },

  purchase_order: {
    status: {
      draft: { label: "Draft", tone: "neutral" },
      ordered: { label: "Ordered", tone: "info" },
      shipped: { label: "Shipped", tone: "purple" },
      received: { label: "Received", tone: "success", terminal: true },
      closed: { label: "Closed", tone: "success", terminal: true },
      cancelled: { label: "Cancelled", tone: "danger", terminal: true },
    },
  },

  payment: {
    status: {
      pending: { label: "Pending", tone: "warning" },
      completed: { label: "Completed", tone: "success", terminal: true },
      failed: { label: "Failed", tone: "danger" },
      voided: { label: "Voided", tone: "neutral", terminal: true },
    },
  },

  spool: {
    status: {
      active: { label: "Active", tone: "success" },
      empty: { label: "Empty", tone: "neutral", terminal: true },
      expired: { label: "Expired", tone: "danger" },
      damaged: { label: "Damaged", tone: "warning" },
    },
  },

  printer: {
    status: {
      offline: { label: "Offline", tone: "neutral" },
      idle: { label: "Idle", tone: "success" },
      printing: { label: "Printing", tone: "info" },
      paused: { label: "Paused", tone: "warning" },
      error: { label: "Error", tone: "danger" },
      maintenance: { label: "Maintenance", tone: "warning" },
    },
  },
};

/** Title-case an unknown status value: `partially_shipped` → `Partially Shipped`. */
function titleCase(value) {
  return String(value)
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

/**
 * Resolve the display descriptor for a status value on a given axis.
 *
 * Never throws. An unregistered value falls back to a title-cased label with a
 * neutral tone, so a new backend status renders gracefully instead of blank.
 *
 * @param {string} model - e.g. 'production_order'
 * @param {string} field - the status axis, e.g. 'status' | 'qc_status'
 * @param {string|null|undefined} value
 * @returns {StatusDescriptor}
 */
export function getDescriptor(model, field, value) {
  if (value === null || value === undefined || value === "") {
    return { label: "—", tone: "neutral", terminal: false };
  }
  const entry = STATUS_DESCRIPTORS[model]?.[field]?.[value];
  if (entry) {
    return { label: entry.label, tone: entry.tone, terminal: !!entry.terminal };
  }
  return { label: titleCase(value), tone: "neutral", terminal: false };
}

/** True if (model, field, value) has a registered descriptor (not a fallback). */
export function hasDescriptor(model, field, value) {
  return Boolean(STATUS_DESCRIPTORS[model]?.[field]?.[value]);
}

export default getDescriptor;
