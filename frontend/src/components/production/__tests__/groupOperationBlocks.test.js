/**
 * groupOperationBlocks (print-batch S4) — unit tests.
 *
 * Operations co-booked into one window carry the same backend group_key and
 * must collapse into a single drawable group that lists every member.
 */
import { describe, it, expect } from "vitest";
import {
  groupOperationBlocks,
  describeMember,
} from "../scheduler/groupOperationBlocks";

const KEY = "printer-3|2026-06-15T08:00:00|2026-06-15T09:00:00";

const op = (id, overrides = {}) => ({
  id,
  operation_code: "OP010",
  operation_name: "3D Print",
  sequence: 10,
  status: "queued",
  scheduled_start: "2026-06-15T08:00:00",
  scheduled_end: "2026-06-15T09:00:00",
  production_order_id: 100 + id,
  production_order_code: `PO-2026-00${id}`,
  product_name: `Part ${id}`,
  quantity: id,
  group_key: KEY,
  ...overrides,
});

describe("groupOperationBlocks", () => {
  it("collapses three co-booked members into one group listing all three", () => {
    const groups = groupOperationBlocks([op(1), op(2), op(3)]);

    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe(KEY);
    expect(groups[0].members.map((m) => m.id)).toEqual([1, 2, 3]);
    expect(groups[0].primary.id).toBe(1);
  });

  it("keeps blocks with different group keys as separate groups, in order", () => {
    const later = op(4, {
      group_key: "printer-3|2026-06-15T09:00:00|2026-06-15T10:00:00",
      scheduled_start: "2026-06-15T09:00:00",
      scheduled_end: "2026-06-15T10:00:00",
    });
    const groups = groupOperationBlocks([op(1), later, op(2)]);

    expect(groups.map((g) => g.members.map((m) => m.id))).toEqual([[1, 2], [4]]);
  });

  it("treats a block without a group_key as a group of one", () => {
    const groups = groupOperationBlocks([
      op(1, { group_key: undefined }),
      op(2, { group_key: undefined }),
    ]);

    expect(groups).toHaveLength(2);
    expect(groups.every((g) => g.members.length === 1)).toBe(true);
  });

  it("orders members by order code so the primary is deterministic", () => {
    const groups = groupOperationBlocks([op(3), op(1), op(2)]);

    expect(groups[0].members.map((m) => m.id)).toEqual([1, 2, 3]);
    expect(groups[0].primary.id).toBe(1);
  });

  it("shows a group as running when any member is running", () => {
    const groups = groupOperationBlocks([
      op(1),
      op(2, { status: "in_progress" }),
      op(3, { status: "on_hold" }),
    ]);

    expect(groups[0].status).toBe("in_progress");
  });

  it("returns an empty list for no operations", () => {
    expect(groupOperationBlocks([])).toEqual([]);
    expect(groupOperationBlocks()).toEqual([]);
  });
});

describe("describeMember", () => {
  it("lists order code, product and quantity", () => {
    expect(describeMember(op(2, { product_name: "Headphone Mount", quantity: 10 }))).toBe(
      "PO-2026-002 · Headphone Mount × 10"
    );
  });

  it("omits missing product and quantity", () => {
    expect(
      describeMember(op(2, { product_name: null, quantity: null }))
    ).toBe("PO-2026-002");
  });
});
