/**
 * Helpers for quote discount lines.
 *
 * A discount line is a product-less (fee/service) quote line with a negative
 * unit price, e.g. "Multi-buy discount" at -5.00. The quote form lets the
 * user type the amount off as a positive number; it is stored negative.
 */

/** True for a fee/service line whose unit price is negative. */
export const isDiscountLine = (line) =>
  line?.line_type === "service" && (parseFloat(line.unit_price) || 0) < 0;

/** Turn an "amount off" typed as a positive number into a negative price. */
export const toDiscountPrice = (amount) => {
  const value = Math.abs(parseFloat(amount));
  return Number.isFinite(value) ? -value : NaN;
};

/** Format money with the minus sign before the currency symbol: -$5.00. */
export const formatSignedMoney = (value) => {
  const number = Number(value) || 0;
  return `${number < 0 ? "-" : ""}$${Math.abs(number).toFixed(2)}`;
};
