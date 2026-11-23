/**
 * LineDescription - a line's multi-line description and discount, shown
 * under the item name on quotes, orders and invoices.
 */
import { lineDiscountText } from "../../lib/discounts";

export default function LineDescription({ text, line }) {
  const discount = line ? lineDiscountText(line) : null;
  if (!text && !discount) return null;
  return (
    <div className="mt-1 space-y-0.5">
      {text && <p className="text-xs text-gray-400 whitespace-pre-line">{text}</p>}
      {discount && <p className="text-xs text-green-400">{discount}</p>}
    </div>
  );
}
