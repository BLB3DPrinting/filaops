/**
 * Quote form line items: building them from saved quotes, products and fees,
 * and turning them into the API payload.
 */
import { discountPayload, discountError, roundHalfUp } from "../../lib/discounts";

const blankLine = {
  product_sku: "",
  material_type: "",
  color: "",
  notes: "",
  description: "",
  discount_type: "",
  discount_value: "",
  discount_label: "",
};

/** Form line from a saved quote line. */
export const lineFromQuoteLine = (l) => ({
  ...blankLine,
  line_type: l.product_id ? "product" : "service",
  product_id: l.product_id,
  product_name: l.product_name,
  quantity: l.quantity,
  unit_price: l.unit_price,
  material_type: l.material_type || "",
  color: l.color || "",
  notes: l.notes || "",
  description: l.description || "",
  discount_type: l.discount_type || "",
  discount_value: l.discount_value ?? "",
  discount_label: l.discount_label || "",
  // The saved unit price already includes the customer's price-level
  // discount; tell the server so it is not applied again on save.
  price_level_percent_applied:
    l.product_id && Number(l.discount_percent) > 0 ? Number(l.discount_percent) : null,
});

/** Form line from a legacy single-item quote. */
export const lineFromSingleItemQuote = (quote) => ({
  ...blankLine,
  line_type: "product",
  product_id: quote.product_id,
  product_name: quote.product_name,
  quantity: quote.quantity || 1,
  unit_price: quote.unit_price || "",
  material_type: quote.material_type || "",
  color: quote.color || "",
  price_level_percent_applied:
    quote.product_id && Number(quote.discount_percent) > 0 ? Number(quote.discount_percent) : null,
});

/** Form line for a catalog item; its Description becomes the line description. */
export const lineFromProduct = (product) => ({
  ...blankLine,
  product_id: product.id,
  line_type: "product",
  product_name: product.name,
  product_sku: product.sku,
  quantity: 1,
  unit_price: product.selling_price ?? "",
  description: product.description || "",
});

/** Form line for a one-time fee. */
export const lineFromFee = (name, quantity, unitPrice) => ({
  ...blankLine,
  line_type: "service",
  product_id: null,
  product_name: name,
  quantity,
  unit_price: unitPrice,
});

/** API payload for one form line. */
export const linePayload = (li) => ({
  product_id: li.line_type === "service" ? null : li.product_id || null,
  product_name: li.product_name,
  quantity: li.quantity,
  unit_price: parseFloat(li.unit_price),
  material_type: li.material_type || null,
  color: li.color || null,
  notes: li.notes || null,
  description: (li.description || "").trim() ? li.description : null,
  ...discountPayload(li.discount_type, li.discount_value, li.discount_label),
  ...(hasPriceLevelApplied(li) ? { price_level_percent_applied: li.price_level_percent_applied } : {}),
});

const hasPriceLevelApplied = (li) =>
  li.line_type !== "service" &&
  li.price_level_percent_applied !== null &&
  li.price_level_percent_applied !== undefined;

/**
 * Line after one field changes. A typed unit price is a list price, like a
 * new line's, so the customer's price level applies to it again.
 */
export const withLineField = (li, field, value) =>
  field === "unit_price"
    ? { ...li, unit_price: value, price_level_percent_applied: null }
    : { ...li, [field]: value };

/**
 * List prices (in cents) that give ``netCents`` after ``pct`` percent off.
 * Quotes saved before half-up rounding used Decimal's half-even, so a price
 * counts if either mode gives the saved net price. Integer arithmetic, so the
 * check is exact.
 */
const listCentsFor = (netCents, pct) => {
  const keep = 10000 - Math.round(pct * 100); // parts of 10000 kept
  const fits = (listCents) => {
    const x = listCents * keep;
    const down = Math.floor(x / 10000);
    const rest = x - down * 10000;
    const halfUp = rest >= 5000 ? down + 1 : down;
    const halfEven = rest > 5000 || (rest === 5000 && down % 2 === 1) ? down + 1 : down;
    return halfUp === netCents || halfEven === netCents;
  };
  const found = [];
  const lo = Math.floor(((netCents - 1) * 10000) / keep);
  const hi = Math.ceil(((netCents + 1) * 10000) / keep);
  for (let c = Math.max(lo, 0); c <= hi; c += 1) if (fits(c)) found.push(c);
  return found;
};

/**
 * Line when the quote's customer changes: a saved price that includes the old
 * customer's price level goes back to its list price, so the new customer's
 * level (if any) is the one applied.
 *
 * The list price is not stored, so it is worked back from the saved net price.
 * When rounding means more than one list price fits ($2.01 and $2.02 at 50%
 * both save as $1.01; $10.04 and, under the old half-even rounding, $10.05 at
 * 10% both save as $9.04), or at 100% where nothing can be worked back, the price
 * is left blank for the user to enter: the form will not save a blank price.
 */
export const withoutSavedPriceLevel = (li) => {
  if (!hasPriceLevelApplied(li)) return li;
  const pct = Number(li.price_level_percent_applied);
  const unit = parseFloat(li.unit_price);
  const cleared = { ...li, price_level_percent_applied: null };
  if (Number.isNaN(unit) || !(pct > 0)) return cleared;
  const candidates = pct < 100 ? listCentsFor(Math.round(roundHalfUp(unit, 2) * 100), pct) : [];
  return { ...cleared, unit_price: candidates.length === 1 ? candidates[0] / 100 : "" };
};

/** First discount problem across the quote and its lines, or null. */
export const firstDiscountError = (lineItems, form) => {
  for (const li of lineItems) {
    const err = discountError(li.discount_type, li.discount_value);
    if (err) return `${li.product_name}: ${err}`;
  }
  return discountError(form.discount_type, form.discount_value);
};

/** True when every line has what the API needs to price it. */
export const linesArePriceable = (lineItems) =>
  lineItems.length > 0 &&
  lineItems.every((li) => li.product_name && li.unit_price !== "" && !Number.isNaN(parseFloat(li.unit_price)));
