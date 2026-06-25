import { describe, it, expect } from "vitest";
import { axisLabel, axisTone, severityTone, orderedLanes } from "../axisMeta";

describe("axisMeta", () => {
  it("labels and tones known axes; falls back gracefully for unknown", () => {
    expect(axisLabel("production")).toBe("Production");
    expect(axisTone("production")).toBe("purple");
    expect(axisLabel("weird_axis")).toBe("Weird Axis");
    expect(axisTone("weird_axis")).toBe("neutral");
  });

  it("maps severity to the F2 badge tones", () => {
    expect(severityTone("critical")).toBe("danger");
    expect(severityTone("high")).toBe("warning");
    expect(severityTone("medium")).toBe("info");
    expect(severityTone("low")).toBe("neutral");
    expect(severityTone("nonsense")).toBe("neutral");
  });

  it("orders lanes by AXIS_ORDER, unknown axes last", () => {
    // production (0) before payment (4); 'zzz' is unknown → last.
    const lanes = orderedLanes({ payment: [1], production: [2], zzz: [3] });
    expect(lanes.map(([axis]) => axis)).toEqual(["production", "payment", "zzz"]);
    // pairs preserve the original action arrays
    expect(lanes[0][1]).toEqual([2]);
  });

  it("returns [] for empty/falsy input", () => {
    expect(orderedLanes(null)).toEqual([]);
    expect(orderedLanes(undefined)).toEqual([]);
    expect(orderedLanes({})).toEqual([]);
  });
});
