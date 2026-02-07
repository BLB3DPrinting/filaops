/**
 * Currency input: user-friendly editing, nicely formatted on blur.
 *
 * Accepts an optional `error` string. When present, renders an error message
 * and sets aria-invalid / aria-describedby on the input for screen-readers.
 */
import { parseDecimal, formatCurrency } from "../../lib/number";

export default function CurrencyField({
  id,
  value,
  onChange,
  error,
  currency = "USD",
  locale = "en-US",
  ...rest
}) {
  const errorId = id ? `${id}-error` : undefined;

  return (
    <>
      <input
        {...rest}
        id={id}
        inputMode="decimal"
        value={value ?? ""}
        onChange={(e) => onChange(parseDecimal(e.target.value) ?? "")}
        onBlur={(e) => {
          const n = parseDecimal(e.target.value);
          if (n !== null) e.target.value = formatCurrency(n, currency, locale);
        }}
        aria-invalid={error ? true : undefined}
        aria-describedby={error && errorId ? errorId : undefined}
        className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm w-full"
      />
      {error && errorId && (
        <p id={errorId} role="alert" className="text-red-400 text-sm mt-1">
          {error}
        </p>
      )}
    </>
  );
}

