import { describe, it, expect } from "vitest";
import { getDescriptor, hasDescriptor, STATUS_DESCRIPTORS } from "./statusDescriptors";
import {
  SALES_ORDER_COLORS,
  PRODUCTION_ORDER_COLORS,
  PRODUCTION_ORDER_BADGE_CONFIGS,
  PURCHASE_ORDER_COLORS,
  PAYMENT_COLORS,
  SPOOL_COLORS,
  PRINTER_COLORS,
} from "./statusColors";

describe("getDescriptor", () => {
  it("reconciles the production-order complete/completed drift to one descriptor", () => {
    const complete = getDescriptor("production_order", "status", "complete");
    const completed = getDescriptor("production_order", "status", "completed");
    expect(complete).toEqual({ label: "Complete", tone: "success", terminal: true });
    expect(completed).toEqual(complete);
  });

  it("defines qc_status='conditional' (live value absent from the enum)", () => {
    expect(hasDescriptor("production_order", "qc_status", "conditional")).toBe(true);
    expect(getDescriptor("production_order", "qc_status", "conditional").tone).toBe("warning");
  });

  it("defines status='qc_hold' (live value absent from the enum)", () => {
    expect(hasDescriptor("production_order", "status", "qc_hold")).toBe(true);
  });

  it("maps payment_status='overdue' to a danger tone", () => {
    expect(getDescriptor("sales_order", "payment_status", "overdue")).toEqual({
      label: "Overdue",
      tone: "danger",
      terminal: false,
    });
  });

  it("the same string differs across axes (multi-axis)", () => {
    // 'completed' is terminal-green on a sales order...
    expect(getDescriptor("sales_order", "status", "completed").terminal).toBe(true);
    // ...while a production order's terminal value is 'complete'.
    expect(getDescriptor("production_order", "status", "complete").terminal).toBe(true);
  });

  it("falls back gracefully for an unknown value (title-cased, neutral, never throws)", () => {
    expect(getDescriptor("production_order", "status", "warp_drive")).toEqual({
      label: "Warp Drive",
      tone: "neutral",
      terminal: false,
    });
    expect(getDescriptor("unknown_model", "status", "anything").label).toBe("Anything");
  });

  it("does not treat inherited Object keys as registered descriptors", () => {
    // Plain bracket access would resolve __proto__/constructor/toString to
    // Object.prototype members; the lookup must use own-property checks.
    for (const evil of ["__proto__", "constructor", "toString", "hasOwnProperty"]) {
      expect(hasDescriptor("production_order", "status", evil)).toBe(false);
      const d = getDescriptor("production_order", "status", evil);
      expect(typeof d.label).toBe("string"); // never undefined
      expect(d.tone).toBe("neutral");
      // an inherited model/field key must not resolve either
      expect(hasDescriptor("toString", "status", "complete")).toBe(false);
      expect(hasDescriptor("production_order", "constructor", "complete")).toBe(false);
    }
  });

  it("returns a placeholder for null/undefined/empty value", () => {
    for (const v of [null, undefined, ""]) {
      expect(getDescriptor("sales_order", "status", v)).toEqual({
        label: "—",
        tone: "neutral",
        terminal: false,
      });
    }
  });
});

describe("descriptor registry coverage", () => {
  // Every value in the legacy color maps must have a registered descriptor, so
  // migrating a screen off statusColors never loses a status.
  it.each([
    ["sales_order", "status", SALES_ORDER_COLORS],
    ["production_order", "status", PRODUCTION_ORDER_COLORS],
    ["production_order", "status", PRODUCTION_ORDER_BADGE_CONFIGS],
    ["purchase_order", "status", PURCHASE_ORDER_COLORS],
    ["payment", "status", PAYMENT_COLORS],
    ["spool", "status", SPOOL_COLORS],
    ["printer", "status", PRINTER_COLORS],
  ])("%s.%s covers every legacy color-map value", (model, field, colorMap) => {
    for (const value of Object.keys(colorMap)) {
      expect(hasDescriptor(model, field, value)).toBe(true);
    }
  });

  it("only uses the 6 Badge tones across the whole registry", () => {
    const tones = new Set(["success", "warning", "danger", "info", "neutral", "purple"]);
    for (const fields of Object.values(STATUS_DESCRIPTORS)) {
      for (const values of Object.values(fields)) {
        for (const d of Object.values(values)) {
          expect(tones.has(d.tone)).toBe(true);
        }
      }
    }
  });
});

describe("terminal flags match the status_config.py transition tables", () => {
  // Hardcoded from backend/app/core/status_config.py terminal sets (empty
  // transition target). Guards against descriptor/state-machine drift.
  it.each([
    ["production_order", "status", "complete", true],
    ["production_order", "status", "cancelled", true],
    ["production_order", "status", "split", true],
    ["production_order", "status", "in_progress", false],
    ["production_order", "status", "short", false],
    ["sales_order", "status", "completed", true],
    ["sales_order", "status", "cancelled", true],
    ["sales_order", "status", "delivered", false],
    ["sales_order", "status", "shipped", false],
    ["production_order", "qc_status", "passed", true],
    ["production_order", "qc_status", "waived", true],
    ["production_order", "qc_status", "pending", false],
    ["production_order", "qc_status", "failed", false],
    ["production_order_operation", "status", "complete", true],
    ["production_order_operation", "status", "skipped", true],
    ["production_order_operation", "status", "running", false],
  ])("%s.%s=%s terminal=%s", (model, field, value, terminal) => {
    expect(getDescriptor(model, field, value).terminal).toBe(terminal);
  });
});
