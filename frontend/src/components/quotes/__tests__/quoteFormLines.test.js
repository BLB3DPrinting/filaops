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

  it("uses the catalog price when rounding makes the list price ambiguous", () => {
    // $2.01 and $2.02 at 50% both save as $1.01.
    const saved = lineFromQuoteLine({ ...savedLine, unit_price: "1.01", discount_percent: "50" });
    expect(withoutSavedPriceLevel(saved, "2.01").unit_price).toBe(2.01);
    expect(withoutSavedPriceLevel(saved).unit_price).toBe(2.02);
  });

  it("ignores a catalog price that does not match the saved price", () => {
    // The quote used a custom list price, not the catalog's.
    expect(withoutSavedPriceLevel(lineFromQuoteLine(savedLine), "120.00").unit_price).toBe(100);
  });

  it("never treats a 100% price level's $0 as the list price", () => {
    const saved = lineFromQuoteLine({ ...savedLine, unit_price: "0.00", discount_percent: "100" });
    expect(withoutSavedPriceLevel(saved, "100.00").unit_price).toBe(100);
    const blank = withoutSavedPriceLevel(saved);
    expect(blank.unit_price).toBe("");
    expect(blank.price_level_percent_applied).toBeNull();
  });
});
