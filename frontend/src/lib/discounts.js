/**
 * Discount math and display helpers shared by quotes, orders and invoices.
 *
 * Mirrors backend/app/services/discount_math.py: every step is rounded to
 * cents (half up), line discounts apply before the document discount, and a
 * fixed amount never exceeds what it discounts. The server stays the source
 * of truth (quote forms ask /quotes/preview-totals); this is the offline
 * fallback and the formatting layer.
 */

export const DISCOUNT_TYPE_OPTIONS = [
  { value: "", label: "No discount" },
  { value: "percent", label: "Percent (%)" },
  { value: "amount", label: "Amount ($)" },
];

const toNumber = (value) => {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : 0;
};

/**
 * Round half away from zero at ``places`` decimals, working on the number's
 * decimal text rather than its binary value. ``1.005`` is stored as
 * 1.00499999999999989..., so ``Math.round(1.005 * 100)`` gives 100; shifting
 * the decimal point in the text ("1.005e2" = 100.5) gives 101, which matches
 * the server's Decimal ROUND_HALF_UP.
 */
export const roundHalfUp = (value, places = 0) => {
  const n = toNumber(value);
  if (n === 0) return 0;
  const sign = n < 0 ? -1 : 1;
  const [mantissa, exponent = "0"] = String(Math.abs(n)).split("e");
  const shifted = Math.round(Number(`${mantissa}e${Number(exponent) + places}`));
  return sign * Number(`${shifted}e-${places}`);
};

/**
 * Tax in cents on ``baseCents`` at ``rate`` (a fraction, e.g. 0.0825),
 * mirroring tax_calculation_service: Decimal quantize with its default
 * half-even rounding. Integer arithmetic, so a tie is seen as a tie.
 */
export const taxCents = (baseCents, rate) => {
  const r = toNumber(rate);
  if (r <= 0 || !baseCents) return 0;
  const SCALE = 1000000; // rates carry at most 6 decimal places
  const product = Math.round(baseCents) * Math.round(r * SCALE);
  const whole = Math.floor(product / SCALE);
  const remainder = product - whole * SCALE;
  if (remainder * 2 > SCALE) return whole + 1;
  if (remainder * 2 < SCALE) return whole;
  return whole % 2 === 0 ? whole : whole + 1;
};

/** Dollars -> integer cents, half up. */
export const toCents = (value) => Math.round(roundHalfUp(value, 2) * 100);

export const fromCents = (cents) => cents / 100;

export const money = (value) => `$${toNumber(value).toFixed(2)}`;

/** Negative amount for a discount row, e.g. "-$8.51". */
export const negativeMoney = (value) => `-$${Math.abs(toNumber(value)).toFixed(2)}`;

/** True when a type is chosen and a value has been entered. */
export const hasDiscountInput = (type, value) =>
  Boolean(type) && value !== "" && value !== null && value !== undefined && !Number.isNaN(parseFloat(value));

/** Message describing an invalid discount, or null when it is fine. */
export const discountError = (type, value) => {
  if (!type) return null;
  if (!hasDiscountInput(type, value)) return "Enter a discount value or choose No discount";
  const n = parseFloat(value);
  if (n < 0) return "Discounts cannot be negative";
  if (type === "percent" && n > 100) return "A percent discount cannot exceed 100%";
  return null;
};

/** Discount in cents taken from ``baseCents``. */
export const discountCents = (baseCents, type, value) => {
  if (!hasDiscountInput(type, value) || baseCents <= 0) return 0;
  const n = parseFloat(value);
  if (n <= 0) return 0;
  if (type === "percent") return Math.min(baseCents, roundHalfUp((baseCents * n) / 100));
  if (type === "amount") return Math.min(baseCents, toCents(n));
  return 0;
};

export const defaultDiscountLabel = (type, value) => {
  if (type === "percent" && hasDiscountInput(type, value)) {
    return `${parseFloat(value)}% discount`;
  }
  return type ? "Discount" : "";
};

/** API fields for a discount; all null when none is set. */
export const discountPayload = (type, value, label) => {
  if (!hasDiscountInput(type, value) || parseFloat(value) === 0) {
    return { discount_type: null, discount_value: null, discount_label: null };
  }
  return {
    discount_type: type,
    discount_value: parseFloat(value),
    discount_label: (label || "").trim() || null,
  };
};

/** Discount fields of a saved quote or quote line, for copying it. */
export const savedDiscountFields = (record) =>
  record?.discount_type
    ? {
        discount_type: record.discount_type,
        discount_value: record.discount_value,
        discount_label: record.discount_label || null,
      }
    : { discount_type: null, discount_value: null, discount_label: null };

/**
 * True when a saved line or document carries a discount. Quotes and orders
 * store a type; invoices store the printed label instead.
 */
export const hasSavedDiscount = (record) =>
  Boolean(record?.discount_type || record?.discount_label) && toNumber(record?.discount_amount) > 0;

/** Line amount before its discount (saved totals are after the discount). */
export const savedLineGross = (line, totalField = "total") => {
  const net = toNumber(line?.[totalField]);
  return hasSavedDiscount(line) ? net + toNumber(line.discount_amount) : net;
};

/** Text for a saved line discount, e.g. "Loyalty: -$4.26" or "10% discount: -$4.26". */
export const lineDiscountText = (line) => {
  if (!hasSavedDiscount(line)) return null;
  const label = line.discount_label || defaultDiscountLabel(line.discount_type, line.discount_value);
  return `${label}: ${negativeMoney(line.discount_amount)}`;
};

/**
 * Rows between the items and the subtotal on a saved document.
 * Returns [] when nothing is discounted, so legacy records render as before.
 */
export const savedSummaryRows = (lines, doc, totalField = "total") => {
  const list = Array.isArray(lines) ? lines : [];
  const lineDiscounts = list.reduce(
    (sum, l) => sum + (hasSavedDiscount(l) ? toCents(l.discount_amount) : 0),
    0,
  );
  const docDiscount = hasSavedDiscount(doc) ? toCents(doc.discount_amount) : 0;
  if (!lineDiscounts && !docDiscount) return [];
  // A single-item quote has no lines: its items total is subtotal + discount.
  const gross = list.length
    ? list.reduce((sum, l) => sum + toCents(savedLineGross(l, totalField)), 0)
    : toCents(doc?.subtotal) + docDiscount;
  const rows = [{ key: "items", label: "Items total", amount: fromCents(gross) }];
  if (lineDiscounts) {
    rows.push({ key: "lines", label: "Line discounts", amount: -fromCents(lineDiscounts), discount: true });
  }
  if (docDiscount) {
    rows.push({
      key: "doc",
      label: doc.discount_label || defaultDiscountLabel(doc.discount_type, doc.discount_value) || "Discount",
      amount: -fromCents(docDiscount),
      discount: true,
    });
  }
  return rows;
};

/**
 * Local estimate of quote totals while the server preview is pending or
 * unavailable. ``lines`` are form lines (quantity, unit_price, line_type,
 * discount_type, discount_value).
 */
export const estimateQuoteTotals = ({
  lines,
  priceLevelPercent = 0,
  discountType,
  discountValue,
  taxRate = 0,
  shippingCost = 0,
  shippingTaxable = false,
}) => {
  const lineResults = (lines || []).map((li) => {
    // Work in cents so the price-level step rounds the same way the server does.
    let unitCents = toCents(li.unit_price);
    // A line reopened from a saved quote already includes its price level.
    const alreadyApplied = li.price_level_percent_applied !== null && li.price_level_percent_applied !== undefined;
    if (li.line_type === "product" && priceLevelPercent > 0 && !alreadyApplied) {
      unitCents = roundHalfUp((unitCents * (100 - priceLevelPercent)) / 100);
    }
    const gross = unitCents * (li.quantity || 1);
    const disc = discountCents(gross, li.discount_type, li.discount_value);
    return { gross, discount: disc, net: gross - disc };
  });
  const itemsGross = lineResults.reduce((s, r) => s + r.gross, 0);
  const lineDiscounts = lineResults.reduce((s, r) => s + r.discount, 0);
  const itemsTotal = itemsGross - lineDiscounts;
  const docDiscount = discountCents(itemsTotal, discountType, discountValue);
  const subtotal = itemsTotal - docDiscount;
  const shipping = toCents(shippingCost);
  const taxableBase = subtotal + (shippingTaxable ? shipping : 0);
  const tax = taxCents(taxableBase, taxRate);
  return {
    lines: lineResults.map((r) => ({ gross: fromCents(r.gross), discount: fromCents(r.discount), net: fromCents(r.net) })),
    itemsGross: fromCents(itemsGross),
    lineDiscounts: fromCents(lineDiscounts),
    itemsTotal: fromCents(itemsTotal),
    discountAmount: fromCents(docDiscount),
    subtotal: fromCents(subtotal),
    taxRate,
    taxAmount: fromCents(tax),
    shipping: fromCents(shipping),
    total: fromCents(subtotal + tax + shipping),
  };
};

/** Normalise a /quotes/preview-totals response to the estimate's shape. */
export const totalsFromPreview = (p) => ({
  lines: (p.lines || []).map((l) => ({
    gross: toNumber(l.gross),
    discount: toNumber(l.discount_amount),
    net: toNumber(l.total),
  })),
  itemsGross: toNumber(p.items_gross),
  lineDiscounts: toNumber(p.line_discounts),
  itemsTotal: toNumber(p.items_total),
  discountAmount: toNumber(p.discount_amount),
  subtotal: toNumber(p.subtotal),
  taxRate: toNumber(p.tax_rate),
  taxAmount: toNumber(p.tax_amount),
  shipping: toNumber(p.shipping_cost),
  total: toNumber(p.total),
});
