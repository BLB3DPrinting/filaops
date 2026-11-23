/**
 * Quote form line items: building them from saved quotes, products and fees,
 * and turning them into the API payload.
 */
import { discountPayload, discountError } from "../../lib/discounts";

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
});

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
