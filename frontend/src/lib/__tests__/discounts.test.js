import { describe, it, expect } from "vitest";
import {
  discountCents,
  discountError,
  discountPayload,
  estimateQuoteTotals,
  lineDiscountText,
  savedDiscountFields,
  savedLineGross,
  savedSummaryRows,
  roundHalfUp,
  taxCents,
  toCents,
} from "../discounts";

describe("estimateQuoteTotals", () => {
  it("matches the golden quote: 2 x $42.56, 10% off, 7% tax", () => {
    const t = estimateQuoteTotals({
      lines: [{ line_type: "product", quantity: 2, unit_price: "42.56" }],
      discountType: "percent",
      discountValue: 10,
      taxRate: 0.07,
    });
    expect(t.itemsGross).toBe(85.12);
    expect(t.discountAmount).toBe(8.51);
    expect(t.subtotal).toBe(76.61);
    expect(t.taxAmount).toBe(5.36);
    expect(t.total).toBe(81.97);
  });

  it("applies line discounts before the quote discount", () => {
    const t = estimateQuoteTotals({
      lines: [{ line_type: "product", quantity: 1, unit_price: "100", discount_type: "amount", discount_value: "20" }],
      discountType: "percent",
      discountValue: 10,
    });
    expect(t.lines[0]).toEqual({ gross: 100, discount: 20, net: 80 });
    expect(t.discountAmount).toBe(8);
    expect(t.subtotal).toBe(72);
  });

  it("is a plain sum without discounts", () => {
    const t = estimateQuoteTotals({
      lines: [{ quantity: 3, unit_price: "19.99" }, { quantity: 1, unit_price: "0.01" }],
    });
    expect(t.subtotal).toBe(59.98);
    expect(t.lineDiscounts).toBe(0);
    expect(t.discountAmount).toBe(0);
  });
});

describe("discount helpers", () => {
  it("rounds percent discounts half up and caps amounts", () => {
    expect(discountCents(25, "percent", 10)).toBe(3);
    expect(discountCents(500, "amount", "7.50")).toBe(500);
    expect(discountCents(500, "", "5")).toBe(0);
  });

  it("validates input", () => {
    expect(discountError("", "")).toBeNull();
    expect(discountError("percent", "")).toMatch(/value/);
    expect(discountError("percent", "101")).toMatch(/100%/);
    expect(discountError("amount", "-1")).toMatch(/negative/);
    expect(discountError("amount", "5")).toBeNull();
  });

  it("builds API payloads with nulls when no discount is set", () => {
    expect(discountPayload("", "", "x")).toEqual({ discount_type: null, discount_value: null, discount_label: null });
    expect(discountPayload("percent", "0", "")).toEqual({ discount_type: null, discount_value: null, discount_label: null });
    expect(discountPayload("percent", "10", " Loyal ")).toEqual({
      discount_type: "percent",
      discount_value: 10,
      discount_label: "Loyal",
    });
  });

  it("copies saved discount fields", () => {
    expect(savedDiscountFields({ discount_type: "amount", discount_value: "5.00" })).toEqual({
      discount_type: "amount",
      discount_value: "5.00",
      discount_label: null,
    });
    expect(savedDiscountFields({})).toEqual({ discount_type: null, discount_value: null, discount_label: null });
  });
});

describe("saved documents", () => {
  const discountedLine = {
    total: "25.00",
    discount_type: "amount",
    discount_value: "5.00",
    discount_label: "Loyalty",
    discount_amount: "5.00",
  };

  it("shows nothing extra for an undiscounted document", () => {
    expect(savedSummaryRows([{ total: "10.00" }], { subtotal: "10.00" })).toEqual([]);
  });

  it("lists items total, line discounts and the quote discount", () => {
    const rows = savedSummaryRows(
      [discountedLine, { total: "10.00" }],
      { discount_type: "percent", discount_value: "10", discount_amount: "3.50" },
    );
    expect(rows.map((r) => [r.label, r.amount])).toEqual([
      ["Items total", 40],
      ["Line discounts", -5],
      ["10% discount", -3.5],
    ]);
  });

  it("handles a single-item quote with no lines", () => {
    const rows = savedSummaryRows([], {
      subtotal: "76.61",
      discount_type: "percent",
      discount_value: "10",
      discount_label: "10% discount",
      discount_amount: "8.51",
    });
    expect(rows[0]).toMatchObject({ label: "Items total", amount: 85.12 });
  });

  it("reads invoice lines, which carry a label instead of a type", () => {
    const invoiceLine = { line_total: "25.00", discount_label: "Loyalty", discount_amount: "5.00" };
    expect(savedLineGross(invoiceLine, "line_total")).toBe(30);
    expect(lineDiscountText(invoiceLine)).toBe("Loyalty: -$5.00");
    const rows = savedSummaryRows([invoiceLine], { discount_label: "Spring sale", discount_amount: "2.50" }, "line_total");
    expect(rows.map((r) => r.label)).toEqual(["Items total", "Line discounts", "Spring sale"]);
  });
});

describe("decimal-aware rounding", () => {
  it("rounds an exact half cent up, which binary Math.round does not", () => {
    expect(roundHalfUp(1.005, 2)).toBe(1.01);
    expect(toCents("1.005")).toBe(101);
    expect(toCents("-1.005")).toBe(-101);
    expect(toCents("42.56")).toBe(4256);
  });

  it("rounds a 50% price level on $2.01 to $1.01, as the server does", () => {
    const t = estimateQuoteTotals({
      lines: [{ line_type: "product", quantity: 1, unit_price: "2.01" }],
      priceLevelPercent: 50,
    });
    expect(t.itemsGross).toBe(1.01);
  });

  it("does not apply the price level again to a reopened line", () => {
    const t = estimateQuoteTotals({
      lines: [{ line_type: "product", quantity: 1, unit_price: "90.00", price_level_percent_applied: 10 }],
      priceLevelPercent: 10,
    });
    expect(t.itemsGross).toBe(90);
  });

  it("rounds a half-cent percent discount up", () => {
    expect(discountCents(201, "percent", 50)).toBe(101);
  });

  it("rounds tax like the server's Decimal quantize (half even)", () => {
    // 1250 cents x 7% = 87.5 cents -> 88; 1050 x 5% = 52.5 -> 52
    expect(taxCents(1250, 0.07)).toBe(88);
    expect(taxCents(1050, 0.05)).toBe(52);
    expect(taxCents(1234, 0.0825)).toBe(102); // 101.805 -> 102
    expect(taxCents(1000, 0)).toBe(0);
  });
});
