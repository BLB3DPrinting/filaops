import { describe, it, expect } from "vitest";
import {
  lineFromQuoteLine,
  lineFromSingleItemQuote,
  linePayload,
  withLineField,
  withoutSavedPriceLevel,
} from "../quoteFormLines";

const savedLine = {
  product_id: 7,
  product_name: "Bracket",
  quantity: 1,
  unit_price: "90.00",
  discount_percent: "10.00",
};

describe("reopened quote lines and the customer price level", () => {
  it("marks a saved product line's price as already including its price level", () => {
    const li = lineFromQuoteLine(savedLine);
    expect(li.price_level_percent_applied).toBe(10);
    expect(linePayload(li).price_level_percent_applied).toBe(10);
  });

  it("does not mark lines saved without a price level", () => {
    const li = lineFromQuoteLine({ ...savedLine, discount_percent: null });
    expect(li.price_level_percent_applied).toBeNull();
    expect(linePayload(li)).not.toHaveProperty("price_level_percent_applied");
  });

  it("marks a reopened single-item quote the same way", () => {
    const li = lineFromSingleItemQuote({ product_id: 3, product_name: "Part", quantity: 2, unit_price: "45.00", discount_percent: "10" });
    expect(li.price_level_percent_applied).toBe(10);
  });

  it("treats a typed unit price as a list price again", () => {
    const li = withLineField(lineFromQuoteLine(savedLine), "unit_price", "95");
    expect(li.price_level_percent_applied).toBeNull();
    expect(linePayload(li)).not.toHaveProperty("price_level_percent_applied");
  });

  it("keeps the mark when another field changes", () => {
    const li = withLineField(lineFromQuoteLine(savedLine), "quantity", 3);
    expect(li.price_level_percent_applied).toBe(10);
  });

  it("restores the list price when the customer changes", () => {
    const li = withoutSavedPriceLevel(lineFromQuoteLine(savedLine));
    expect(li.unit_price).toBe(100);
    expect(li.price_level_percent_applied).toBeNull();
  });
});
