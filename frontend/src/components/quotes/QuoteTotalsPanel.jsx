/**
 * QuoteTotalsPanel - totals in the order the quote PDF prints them:
 * items total, line discounts, quote discount, subtotal, tax, shipping, total.
 */
import { money, negativeMoney } from "../../lib/discounts";

const Row = ({ label, value, discount = false }) => (
  <div className="flex justify-between items-center text-sm">
    <span className={discount ? "text-green-400" : "text-gray-400"}>{label}:</span>
    <span className={discount ? "text-green-400" : "text-white"}>{value}</span>
  </div>
);

export default function QuoteTotalsPanel({ totals, itemCount, discountLabel, taxName }) {
  const discounted = totals.lineDiscounts > 0 || totals.discountAmount > 0;
  const taxPercent = totals.taxRate > 0 ? ` (${(totals.taxRate * 100).toFixed(2)}%)` : "";
  return (
    <div className="bg-gray-800 rounded-lg p-4 space-y-2">
      {discounted && <Row label="Items total" value={money(totals.itemsGross)} />}
      {totals.lineDiscounts > 0 && (
        <Row label="Line discounts" value={negativeMoney(totals.lineDiscounts)} discount />
      )}
      {totals.discountAmount > 0 && (
        <Row label={discountLabel || "Discount"} value={negativeMoney(totals.discountAmount)} discount />
      )}
      <Row
        label={`Subtotal (${itemCount} item${itemCount !== 1 ? "s" : ""})`}
        value={money(totals.subtotal)}
      />
      {totals.taxAmount > 0 && <Row label={`${taxName || "Tax"}${taxPercent}`} value={money(totals.taxAmount)} />}
      {totals.shipping > 0 && <Row label="Shipping" value={money(totals.shipping)} />}
      <div className="flex justify-between items-center pt-2 border-t border-gray-700">
        <span className="text-gray-400 font-medium">Total:</span>
        <span className="text-2xl font-bold text-green-400">{money(totals.total)}</span>
      </div>
    </div>
  );
}
