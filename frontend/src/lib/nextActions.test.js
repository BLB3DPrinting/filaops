import { describe, it, expect } from "vitest";
import {
  severityFromPriority,
  fromActionItems,
  fromResolutionActions,
  fromOrderGuards,
  mergeByAxis,
} from "./nextActions";

describe("severityFromPriority", () => {
  it("maps backend priority ints to severities", () => {
    expect(severityFromPriority(1)).toBe("critical");
    expect(severityFromPriority(2)).toBe("high");
    expect(severityFromPriority(3)).toBe("medium");
    expect(severityFromPriority(4)).toBe("low");
    expect(severityFromPriority(99)).toBe("low");
  });
});

describe("fromActionItems", () => {
  const item = (type, priority, extra = {}) => ({
    id: `${type}_1`,
    type,
    priority,
    title: `${type} title`,
    description: `${type} desc`,
    entity_type: "production_order",
    entity_id: 7,
    entity_code: "WO-7",
    suggested_actions: [{ label: "Go", url: "/admin/production/7", action_type: "navigate" }],
    ...extra,
  });

  it("maps each ActionItemType to the correct axis", () => {
    const out = fromActionItems([
      item("blocked_po", 1),
      item("overrunning_op", 3),
      item("idle_resource", 4),
      item("overdue_so", 1),
      item("due_today_so", 2),
      item("maintenance_due", 2),
    ]);
    expect(out.map((a) => a.axis)).toEqual([
      "production",
      "production",
      "production",
      "fulfillment",
      "fulfillment",
      "maintenance",
    ]);
  });

  it("projects label/severity/href/target from the item + primary suggested action", () => {
    const [a] = fromActionItems([item("blocked_po", 1)]);
    expect(a).toMatchObject({
      axis: "production",
      label: "blocked_po title",
      reason: "blocked_po desc",
      severity: "critical",
      verb: "navigate",
      href: "/admin/production/7",
      target: { type: "production_order", id: 7, code: "WO-7" },
      enabled: true,
    });
  });

  it("tolerates missing suggested_actions and unknown types", () => {
    const out = fromActionItems([
      { id: "x", type: "mystery", priority: 2, title: "Hmm", entity_type: "thing", entity_id: 1 },
    ]);
    expect(out[0].axis).toBe("other");
    expect(out[0].href).toBeUndefined();
    expect(out[0].target).toEqual({ type: "thing", id: 1, code: undefined });
  });

  it("returns [] for non-array input", () => {
    expect(fromActionItems(null)).toEqual([]);
    expect(fromActionItems(undefined)).toEqual([]);
    expect(fromActionItems({})).toEqual([]);
  });

  it("skips malformed (null/non-object) array elements without throwing", () => {
    const out = fromActionItems([null, item("blocked_po", 1), "junk", undefined, 42]);
    expect(out).toHaveLength(1);
    expect(out[0].axis).toBe("production");
  });
});

describe("fromResolutionActions", () => {
  it("projects resolution_actions with axis from reference_type and severity from priority", () => {
    const out = fromResolutionActions({
      resolution_actions: [
        { priority: 1, action: "Order PLA", impact: "unblocks 2 WOs", reference_type: "purchase_order", reference_id: 5 },
        { priority: 3, action: "Reassign printer", impact: "", reference_type: "production_order", reference_id: 9 },
      ],
    });
    expect(out[0]).toMatchObject({
      axis: "supply",
      label: "Order PLA",
      reason: "unblocks 2 WOs",
      severity: "critical",
      target: { type: "purchase_order", id: 5 },
    });
    expect(out[1].axis).toBe("production");
    expect(out[1].severity).toBe("medium");
  });

  it("returns [] when there are no resolution actions", () => {
    expect(fromResolutionActions(null)).toEqual([]);
    expect(fromResolutionActions({})).toEqual([]);
    expect(fromResolutionActions({ resolution_actions: "nope" })).toEqual([]);
  });

  it("skips malformed resolution-action elements without throwing", () => {
    const out = fromResolutionActions({
      resolution_actions: [null, { priority: 2, action: "Do it", reference_type: "production_order", reference_id: 1 }, 7],
    });
    expect(out).toHaveLength(1);
    expect(out[0].label).toBe("Do it");
  });
});

describe("fromOrderGuards", () => {
  it("emits a payment action when unpaid (overdue → high)", () => {
    const out = fromOrderGuards({ id: 3, order_number: "SO-3", is_paid: false, payment_status: "overdue" });
    expect(out).toEqual([
      {
        axis: "payment",
        label: "Collect payment",
        severity: "high",
        verb: "record_payment",
        target: { type: "sales_order", id: 3, code: "SO-3" },
        enabled: true,
      },
    ]);
  });

  it("emits production + fulfillment actions from the guards (multi-axis)", () => {
    const out = fromOrderGuards({
      id: 4,
      is_paid: true,
      can_start_production: true,
      is_ready_to_ship: true,
    });
    expect(out.map((a) => a.axis).sort()).toEqual(["fulfillment", "production"]);
  });

  it("emits nothing when guards are absent (projection never fabricates readiness)", () => {
    expect(fromOrderGuards({ id: 1 })).toEqual([]);
    expect(fromOrderGuards(null)).toEqual([]);
    expect(fromOrderGuards("nope")).toEqual([]);
  });
});

describe("mergeByAxis", () => {
  it("groups actions by axis, sorting each lane by severity", () => {
    const grouped = mergeByAxis(
      [{ axis: "production", label: "B", severity: "low", enabled: true }],
      [{ axis: "production", label: "A", severity: "critical", enabled: true }],
      [{ axis: "payment", label: "Pay", severity: "high", enabled: true }]
    );
    expect(Object.keys(grouped).sort()).toEqual(["payment", "production"]);
    expect(grouped.production.map((a) => a.label)).toEqual(["A", "B"]); // critical before low
  });

  it("dedupes identical actions across sources", () => {
    const a = { axis: "payment", label: "Collect payment", verb: "record_payment", target: { type: "sales_order", id: 3 }, severity: "high", enabled: true };
    const grouped = mergeByAxis([a], [{ ...a }]);
    expect(grouped.payment).toHaveLength(1);
  });

  it("keeps the highest-severity action when a key is duplicated", () => {
    const base = { axis: "production", label: "Start", verb: "start_production", target: { type: "sales_order", id: 5 }, enabled: true };
    // low arrives first, critical later with the same dedupe key
    const grouped = mergeByAxis([{ ...base, severity: "low" }], [{ ...base, severity: "critical" }]);
    expect(grouped.production).toHaveLength(1);
    expect(grouped.production[0].severity).toBe("critical");
  });

  it("skips malformed entries without throwing", () => {
    const grouped = mergeByAxis([null, { axis: "payment", label: "Pay", severity: "high", enabled: true }, "junk"]);
    expect(grouped.payment).toHaveLength(1);
  });

  it("a sales order needing payment + production surfaces on two axes", () => {
    const grouped = mergeByAxis(
      fromOrderGuards({ id: 9, is_paid: false, payment_status: "pending", can_start_production: true })
    );
    expect(Object.keys(grouped).sort()).toEqual(["payment", "production"]);
  });
});
