/**
 * Tests for toLocalInputValue (SCHED-TZ).
 *
 * The UTC/local double-shift bug is INVISIBLE when the test runner's
 * timezone is UTC (local === UTC, so the broken toISOString().slice path
 * produces the same string as the correct local path). We pin a non-UTC
 * timezone via process.env.TZ at the very top of this file — before any
 * import that could construct a Date — so the TZ-dependent assertions
 * actually exercise the offset. CI (Linux) honors TZ; some Windows local
 * runs ignore it, so TZ-dependent tests are skipped (not silently passed)
 * when the pin did not take effect.
 */
globalThis.process.env.TZ = "America/New_York";

import { describe, it, expect } from "vitest";
import { toLocalInputValue, parseDateTime } from "../formatting";

// Verify the TZ pin actually took effect on this runner.
// Jan 1 in America/New_York is EST = UTC-5 → getTimezoneOffset() === 300.
const TZ_PINNED = new Date(2026, 0, 1).getTimezoneOffset() === 300;
if (!TZ_PINNED) {
  console.warn(
    "[toLocalInputValue.test] process.env.TZ pin ignored by this platform — " +
      "skipping TZ-dependent assertions (they run in CI on Linux).",
  );
}

describe("toLocalInputValue — timezone-independent", () => {
  it("round-trips a local Date object to the same wall time in ANY timezone", () => {
    // Date constructed from local wall-clock fields must come back verbatim.
    expect(toLocalInputValue(new Date(2026, 5, 12, 14, 42))).toBe(
      "2026-06-12T14:42",
    );
  });

  it("zero-pads months, days, hours, and minutes", () => {
    expect(toLocalInputValue(new Date(2026, 0, 5, 9, 5))).toBe(
      "2026-01-05T09:05",
    );
  });

  it("returns '' for null, undefined, and empty string", () => {
    expect(toLocalInputValue(null)).toBe("");
    expect(toLocalInputValue(undefined)).toBe("");
    expect(toLocalInputValue("")).toBe("");
  });

  it("returns '' for an unparseable string", () => {
    expect(toLocalInputValue("not-a-date")).toBe("");
  });

  it("naive-UTC string lands at the correct local time (computed via parseDateTime)", () => {
    // TZ-agnostic: build the expected local wall time from the same
    // parseDateTime the implementation uses, with independent formatting.
    const naive = "2026-06-12T18:45:00";
    const d = parseDateTime(naive);
    const pad = (n) => String(n).padStart(2, "0");
    const expected = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    expect(toLocalInputValue(naive)).toBe(expected);
  });

  it("submit round-trip preserves the UTC instant: new Date(value).toISOString() === original", () => {
    // The submit path does `new Date(datetimeLocalValue).toISOString()`.
    // Feeding it toLocalInputValue of a naive-UTC server string must yield
    // the exact same UTC instant — in ANY timezone. This is the invariant
    // the old toISOString().slice(0, 16) seeding violated.
    const value = toLocalInputValue("2026-06-12T18:45:00"); // naive UTC
    expect(new Date(value).toISOString()).toBe("2026-06-12T18:45:00.000Z");
  });
});

describe("toLocalInputValue — TZ-dependent (America/New_York)", () => {
  it.skipIf(!TZ_PINNED)(
    "naive-UTC server string shifts to Eastern wall time (18:45 UTC → 14:45 EDT)",
    () => {
      expect(toLocalInputValue("2026-06-12T18:45:00")).toBe(
        "2026-06-12T14:45",
      );
    },
  );

  it.skipIf(!TZ_PINNED)(
    "'Z'-suffixed UTC string shifts to Eastern wall time",
    () => {
      expect(toLocalInputValue("2026-06-12T18:45:00Z")).toBe(
        "2026-06-12T14:45",
      );
    },
  );

  it.skipIf(!TZ_PINNED)(
    "winter (EST, UTC-5) instant shifts by 5 hours",
    () => {
      expect(toLocalInputValue("2026-01-15T18:45:00")).toBe(
        "2026-01-15T13:45",
      );
    },
  );

  it.skipIf(!TZ_PINNED)(
    "regression: result differs from the broken toISOString().slice(0, 16) seeding",
    () => {
      const d = parseDateTime("2026-06-12T18:45:00");
      const broken = d.toISOString().slice(0, 16); // "2026-06-12T18:45" — UTC wall time
      expect(toLocalInputValue("2026-06-12T18:45:00")).not.toBe(broken);
    },
  );
});
