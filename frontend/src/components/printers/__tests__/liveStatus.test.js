import { describe, it, expect } from "vitest";
import { mergeLiveTelemetry, nozzleText, stateWord, statusKey, statusText } from "../liveStatus";

describe("mergeLiveTelemetry", () => {
  it("overlays PRO telemetry but keeps Core's numeric id", () => {
    const merged = mergeLiveTelemetry(
      [{ id: 1, name: "Leonardo", status: "offline" }, { id: 2, name: "Raphael", status: "offline" }],
      [{ id: "1", status: "printing", state: "preparing" }]
    );

    expect(merged[0]).toEqual({ id: 1, name: "Leonardo", status: "printing", state: "preparing" });
    expect(merged[1]).toEqual({ id: 2, name: "Raphael", status: "offline" });
    // Maintenance logs look printers up by the numeric id
    expect(merged.find((p) => p.id === 1)?.name).toBe("Leonardo");
  });

  it("leaves Core's rows alone without PRO data", () => {
    const core = [{ id: 1, status: "idle" }];
    expect(mergeLiveTelemetry(core, undefined)).toEqual(core);
  });
});

describe("liveStatus", () => {
  it("falls back to Core's status without PRO telemetry", () => {
    const printer = { status: "Offline" };
    expect(statusKey(printer)).toBe("offline");
    expect(stateWord(printer)).toBe("offline");
    expect(statusText(printer)).toBe("offline");
  });

  it("uses PRO's live state and label when present", () => {
    const printer = { status: "printing", state: "preparing", state_label: "Preparing" };
    expect(statusKey(printer)).toBe("printing");
    expect(stateWord(printer)).toBe("preparing");
    expect(statusText(printer)).toBe("Preparing");
  });

  it("colours a live error red even when Core's status says paused", () => {
    const printer = { status: "paused", state: "error", state_label: "Paused · 1200_1000_0002_0002" };
    expect(statusKey(printer)).toBe("error");
    expect(statusText(printer)).toBe("Paused · 1200_1000_0002_0002");
  });

  it("spells out needs clearing", () => {
    expect(stateWord({ status: "idle", state: "needs_clearing" })).toBe("needs clearing");
  });

  it("formats the nozzle", () => {
    expect(nozzleText({ nozzle: { diameter_mm: 0.6, type: "hardened_steel" } })).toBe("0.6 mm hardened steel");
    expect(nozzleText({ nozzle: { diameter_mm: null, type: "" } })).toBeNull();
    expect(nozzleText({})).toBeNull();
  });
});
