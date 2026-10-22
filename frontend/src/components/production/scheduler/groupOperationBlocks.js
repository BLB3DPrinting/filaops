/**
 * Collapse a lane's operation blocks into drawable groups (print-batch S4).
 *
 * Operations booked together via resource_scheduling.schedule_operations_together
 * share one window on one machine, and the board payload gives every block a
 * `group_key` (lane + start + end). Blocks with the same key are ONE run, so the
 * board draws one block and lists its members instead of stacking N blocks.
 *
 * A block without a group_key (older payload) is a group of one, so the board
 * degrades to the old one-block-per-operation drawing.
 */

// Most urgent first: a group that has any running member reads as running.
const STATUS_PRIORITY = ["in_progress", "on_hold", "queued", "scheduled", "pending"];

function compareMembers(a, b) {
  return (
    (a.production_order_code || "").localeCompare(b.production_order_code || "") ||
    (a.sequence ?? 0) - (b.sequence ?? 0) ||
    a.id - b.id
  );
}

function groupStatus(members) {
  for (const status of STATUS_PRIORITY) {
    if (members.some((m) => m.status === status)) return status;
  }
  return members[0].status;
}

/**
 * @param {Array} operations lane.operations from GET /scheduling/board
 * @returns {Array<{key: string, members: Array, primary: object, status: string}>}
 *   in first-appearance order; `primary` is the first member (stable order:
 *   order code, sequence, id) and carries the shared start/end.
 */
export function groupOperationBlocks(operations = []) {
  const byKey = new Map();
  for (const op of operations) {
    const key = op.group_key ?? `op-${op.id}`;
    if (!byKey.has(key)) byKey.set(key, []);
    byKey.get(key).push(op);
  }
  return [...byKey.entries()].map(([key, members]) => {
    const sorted = [...members].sort(compareMembers);
    return { key, members: sorted, primary: sorted[0], status: groupStatus(sorted) };
  });
}

/** "PO-2026-0099 · Headphone Mount × 10" — one member, for labels and tooltips. */
export function describeMember(op) {
  const parts = [op.production_order_code, op.product_name].filter(Boolean);
  const label = parts.join(" · ");
  return op.quantity != null ? `${label} × ${op.quantity}` : label;
}
