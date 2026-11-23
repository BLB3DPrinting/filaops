/**
 * QuoteLineExtras - description and discount inputs under a quote line.
 *
 * The description prints under the item name on the quote, order and
 * invoice. For catalog items it starts as the item's own Description and can
 * be edited here without changing the item.
 */
import DiscountFields from "../discounts/DiscountFields";
import { money, negativeMoney } from "../../lib/discounts";

export default function QuoteLineExtras({ line, index, totals, onChange }) {
  return (
    <div className="mt-2 space-y-2">
      <textarea
        aria-label={`Description for ${line.product_name}`}
        value={line.description || ""}
        onChange={(e) => onChange("description", e.target.value)}
        rows={Math.min(5, Math.max(2, (line.description || "").split("\n").length))}
        maxLength={4000}
        placeholder="Description printed under the item name (optional)"
        className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <DiscountFields
          idPrefix={`line-${index}-discount`}
          title="Line discount"
          compact
          type={line.discount_type}
          value={line.discount_value}
          label={line.discount_label}
          onChange={onChange}
        />
        {totals && totals.discount > 0 && (
          <span className="text-sm text-green-400">
            {negativeMoney(totals.discount)} = {money(totals.net)}
          </span>
        )}
      </div>
    </div>
  );
}
