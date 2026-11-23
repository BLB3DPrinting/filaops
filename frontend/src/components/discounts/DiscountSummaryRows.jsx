/**
 * DiscountSummaryRows - "Items total", "Line discounts" and the document
 * discount, shown above the subtotal on quotes, orders and invoices.
 * Renders nothing when nothing is discounted.
 */
import { money } from "../../lib/discounts";

export default function DiscountSummaryRows({
  rows,
  labelSuffix = "",
  className = "flex justify-between text-sm",
  format = money,
}) {
  if (!rows?.length) return null;
  return rows.map((row) => (
    <div key={row.key} className={className}>
      <span className={row.discount ? "text-green-400" : "text-gray-400"}>
        {row.label}
        {labelSuffix}
      </span>
      <span className={row.discount ? "text-green-400" : "text-white"}>
        {row.discount ? `-${format(Math.abs(row.amount))}` : format(row.amount)}
      </span>
    </div>
  ));
}
