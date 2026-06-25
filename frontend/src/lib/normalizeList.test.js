import { describe, it, expect } from "vitest";
import { normalizeList } from "./normalizeList";

describe("normalizeList", () => {
  it("passes a bare array through with null pagination", () => {
    expect(normalizeList([1, 2, 3])).toEqual({ items: [1, 2, 3], pagination: null });
  });

  it("unwraps the canonical {items, pagination} envelope", () => {
    const page = { total: 1, offset: 0, limit: 50, returned: 1 };
    expect(normalizeList({ items: [{ id: 1 }], pagination: page })).toEqual({
      items: [{ id: 1 }],
      pagination: page,
    });
  });

  it("unwraps domain-keyed envelopes", () => {
    expect(normalizeList({ work_centers: [{ id: 1 }] }).items).toEqual([{ id: 1 }]);
    expect(normalizeList({ products: [{ id: 2 }] }).items).toEqual([{ id: 2 }]);
    expect(normalizeList({ spools: [{ id: 3 }] }).items).toEqual([{ id: 3 }]);
  });

  it("honors an explicit key before the defaults", () => {
    expect(normalizeList({ rows: [{ id: 9 }] }, ["rows"]).items).toEqual([{ id: 9 }]);
  });

  it("prefers items over a domain key when both are present", () => {
    expect(normalizeList({ items: [1], products: [2] }).items).toEqual([1]);
  });

  it.each([
    ["null", null],
    ["undefined", undefined],
    ["empty object", {}],
    ["error string", "Internal Server Error"],
    ["StandardApiError body", { error: "NOT_FOUND", message: "nope", timestamp: "t" }],
    ["FastAPI 422 body", { detail: [{ loc: ["q"], msg: "bad" }] }],
    ["a number", 42],
    ["a non-array items value", { items: "oops" }],
  ])("returns an empty list (never throws) for %s", (_label, payload) => {
    const result = normalizeList(payload);
    expect(result).toEqual({ items: [], pagination: null });
    // The whole point: the result is always .map-able.
    expect(() => result.items.map((x) => x)).not.toThrow();
  });
});
