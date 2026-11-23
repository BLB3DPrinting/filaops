/**
 * DiscountFields - discount type, value and optional label.
 *
 * Used for the quote-level discount and for each quote line. The value and
 * label inputs appear only once a type is chosen, so a quote without
 * discounts looks the same as before.
 */
import { DISCOUNT_TYPE_OPTIONS, defaultDiscountLabel, discountError } from "../../lib/discounts";

export default function DiscountFields({
  type,
  value,
  label,
  onChange,
  idPrefix,
  title = "Discount",
  compact = false,
}) {
  const error = discountError(type, value);
  const inputClass = compact
    ? "bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm"
    : "bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white";

  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={`${idPrefix}-type`} className="text-gray-400 text-sm">
          {title}
        </label>
        <select
          id={`${idPrefix}-type`}
          value={type || ""}
          onChange={(e) => onChange("discount_type", e.target.value)}
          className={inputClass}
        >
          {DISCOUNT_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {type && (
          <>
            <input
              type="number"
              min="0"
              max={type === "percent" ? "100" : undefined}
              step="0.01"
              aria-label={`${title} ${type === "percent" ? "percent" : "amount"}`}
              value={value ?? ""}
              onChange={(e) => onChange("discount_value", e.target.value)}
              placeholder={type === "percent" ? "10" : "5.00"}
              className={`${inputClass} w-24 text-right`}
            />
            <input
              type="text"
              maxLength={100}
              aria-label={`${title} label`}
              value={label || ""}
              onChange={(e) => onChange("discount_label", e.target.value)}
              placeholder={defaultDiscountLabel(type, value) || "Label (optional)"}
              className={`${inputClass} flex-1 min-w-[10rem]`}
            />
          </>
        )}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
