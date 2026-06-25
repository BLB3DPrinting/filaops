/**
 * Multi-axis next-action contract (UX Foundation, epic #808).
 *
 * The Command Center is a thin aggregator over a single "next-action" shape that
 * any module emits. Status in FilaOps is multi-axis (a sales order can need
 * payment AND production AND fulfillment at once), so the contract is a LIST
 * keyed by axis — never one action per record.
 *
 * These adapters are pure PROJECTIONS over surfaces the backend already
 * computes (command-center /action-items, production /blocking-issues, and the
 * `can_*`/`is_*` order guards). They must NOT recompute readiness — otherwise a
 * cockpit badge and a detail panel could disagree, which is the disconnected-
 * pages problem this program exists to kill. No fetch here; given a payload they
 * return a deterministic NextAction[]. Malformed elements are skipped, never
 * thrown on.
 */

/** @typedef {'critical'|'high'|'medium'|'low'} Severity */
/** @typedef {{ type: string, id: number, code?: string }} ActionTarget */
/**
 * @typedef {Object} NextAction
 * @property {string} axis - 'payment'|'fulfillment'|'production'|'qc'|'supply'|'maintenance'|'other'
 * @property {string} label
 * @property {string} [reason]
 * @property {Severity} severity
 * @property {string} [verb] - a UI handler key (e.g. 'record_payment')
 * @property {string} [verbLabel] - human label for the action button (e.g. 'View PO')
 * @property {string} [href] - deep link
 * @property {ActionTarget} [target]
 * @property {boolean} enabled
 * @property {string} [disabledReason]
 */

// Command-center ActionItemType → cockpit lane axis.
const AXIS_BY_ACTION_TYPE = {
  blocked_po: "production",
  overrunning_op: "production",
  idle_resource: "production",
  overdue_so: "fulfillment",
  due_today_so: "fulfillment",
  maintenance_due: "maintenance",
};

// reference_type (blocking-issue resolution) → axis.
const AXIS_BY_REFERENCE_TYPE = {
  production_order: "production",
  purchase_order: "supply",
  sales_order: "fulfillment",
};

const SEVERITY_BY_PRIORITY = { 1: "critical", 2: "high", 3: "medium", 4: "low" };
const SEVERITY_RANK = { critical: 0, high: 1, medium: 2, low: 3 };
const severityRank = (s) => (SEVERITY_RANK[s] ?? 9);

const isObject = (x) => x != null && typeof x === "object";

/** Map a backend priority int (1=most urgent) to a severity; unknown → 'low'. */
export function severityFromPriority(priority) {
  return SEVERITY_BY_PRIORITY[priority] || "low";
}

/**
 * Project command-center ActionItems into NextActions (one per item).
 * Malformed (non-object) entries are skipped.
 * @param {Array} actionItems - ActionItem[] from /command-center/action-items
 * @returns {NextAction[]}
 */
export function fromActionItems(actionItems) {
  if (!Array.isArray(actionItems)) return [];
  return actionItems.flatMap((item) => {
    if (!isObject(item)) return [];
    const primary = (item.suggested_actions || [])[0] || {};
    const hasTarget = item.entity_type != null && item.entity_id != null;
    return [
      {
        axis: AXIS_BY_ACTION_TYPE[item.type] || "other",
        label: item.title || primary.label || "Action needed",
        reason: item.description || undefined,
        severity: severityFromPriority(item.priority),
        verb: primary.action_type || undefined,
        verbLabel: primary.label || undefined,
        href: primary.url || undefined,
        target: hasTarget
          ? { type: item.entity_type, id: item.entity_id, code: item.entity_code || undefined }
          : undefined,
        enabled: true,
      },
    ];
  });
}

/**
 * Project a ProductionOrderBlockingIssues payload's resolution_actions[].
 * Malformed (non-object) entries are skipped.
 * @param {Object} blockingIssues - { resolution_actions: ResolutionAction[] }
 * @returns {NextAction[]}
 */
export function fromResolutionActions(blockingIssues) {
  const actions = blockingIssues?.resolution_actions;
  if (!Array.isArray(actions)) return [];
  return actions.flatMap((a) => {
    if (!isObject(a)) return [];
    const hasTarget = a.reference_type != null && a.reference_id != null;
    return [
      {
        axis: AXIS_BY_REFERENCE_TYPE[a.reference_type] || "production",
        label: a.action,
        reason: a.impact || undefined,
        severity: severityFromPriority(a.priority),
        target: hasTarget ? { type: a.reference_type, id: a.reference_id } : undefined,
        enabled: true,
      },
    ];
  });
}

/**
 * Project a sales order's serialized guard booleans into NextActions, reading
 * each guard DEFENSIVELY (a guard that isn't serialized yet simply yields no
 * action — the projection never fabricates readiness).
 * @param {Object} order - a SalesOrderResponse-shaped object
 * @returns {NextAction[]}
 */
export function fromOrderGuards(order) {
  if (!isObject(order)) return [];
  const out = [];
  const target =
    order.id != null
      ? { type: "sales_order", id: order.id, code: order.order_number || undefined }
      : undefined;

  if (order.is_paid === false) {
    out.push({
      axis: "payment",
      label: "Collect payment",
      severity: order.payment_status === "overdue" ? "high" : "medium",
      verb: "record_payment",
      target,
      enabled: true,
    });
  }
  if (order.can_start_production === true) {
    out.push({
      axis: "production",
      label: "Start production",
      severity: "medium",
      verb: "start_production",
      target,
      enabled: true,
    });
  }
  if (order.is_ready_to_ship === true) {
    out.push({
      axis: "fulfillment",
      label: "Ship order",
      severity: "high",
      verb: "ship",
      target,
      enabled: true,
    });
  }
  return out;
}

const dedupeKey = (a) =>
  `${a.axis}|${a.target?.type || ""}|${a.target?.id ?? ""}|${a.verb || a.label}`;

/**
 * Merge NextAction lists into an axis-keyed map. De-duplicates across sources,
 * keeping the HIGHEST-severity action for a given key (a later `critical` is not
 * dropped behind an earlier `low`), and sorts each lane by severity. Malformed
 * entries are skipped. This is what the Command Center renders as lanes.
 * @param {...NextAction[]} lists
 * @returns {Record<string, NextAction[]>}
 */
export function mergeByAxis(...lists) {
  const best = new Map(); // dedupeKey → highest-severity action seen
  for (const list of lists) {
    for (const action of list || []) {
      if (!isObject(action)) continue;
      const key = dedupeKey(action);
      const existing = best.get(key);
      // strict < keeps the first-seen entry on a severity tie
      if (!existing || severityRank(action.severity) < severityRank(existing.severity)) {
        best.set(key, action);
      }
    }
  }
  const byAxis = {};
  for (const action of best.values()) {
    if (!byAxis[action.axis]) byAxis[action.axis] = [];
    byAxis[action.axis].push(action);
  }
  for (const axis of Object.keys(byAxis)) {
    byAxis[axis].sort((x, y) => severityRank(x.severity) - severityRank(y.severity));
  }
  return byAxis;
}
