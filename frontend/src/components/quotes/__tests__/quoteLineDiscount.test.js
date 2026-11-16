import { describe, it, expect } from "vitest";
import { formatSignedMoney, isDiscountLine, toDiscountPrice } from "../quoteLineDiscount";

describe("isDiscountLine", () => {
  it("is true for a fee line with a negative price", () => {
    expect(isDiscountLine({ line_type: "service", unit_price: "-5.00" })).toBe(true);
  });

  it("is false for a normal fee line", () => {
    expect(isDiscountLine({ line_type: "service", unit_price: "75.00" })).toBe(false);
  });

  it("is false for product lines", () => {
    expect(isDiscountLine({ line_type: "product", unit_price: "20.00" })).toBe(false);
  });
});

describe("toDiscountPrice", () => {
  it("stores the amount off as a negative price", () => {
    expect(toDiscountPrice("5.00")).toBe(-5);
  });

  it("does not double-negate an amount typed with a minus sign", () => {
    expect(toDiscountPrice("-5")).toBe(-5);
  });

  it("returns NaN for non-numeric input", () => {
    expect(Number.isNaN(toDiscountPrice("abc"))).toBe(true);
  });
});

describe("formatSignedMoney", () => {
  it("puts the minus sign before the currency symbol", () => {
    expect(formatSignedMoney(-5)).toBe("-$5.00");
  });

  it("formats positive amounts as before", () => {
    expect(formatSignedMoney(12.5)).toBe("$12.50");
  });
});
