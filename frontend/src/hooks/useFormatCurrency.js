/**
 * useFormatCurrency — locale-aware currency formatting hook.
 *
 * Returns a memoized formatter that uses the company's currency_code and locale
 * from LocaleContext. Falls back to USD / en-US if context is unavailable.
 *
 * Usage:
 *   const formatCurrency = useFormatCurrency();
 *   formatCurrency(1234.56)  // → "$1,234.56" (USD/en-US) or "1.234,56 €" (EUR/de-DE)
 */
import { useCallback } from "react";
import { useLocale } from "../contexts/LocaleContext";

export function useFormatCurrency() {
  const { currency_code, locale } = useLocale();

  return useCallback(
    (n, { maxDecimals } = {}) => {
      if (n == null || !Number.isFinite(Number(n))) return "";
      // Show up to 4 decimals for sub-dollar values (e.g., $0.0642/ea
      // from $8.99 / 140pcs), but keep $5.00 clean at currency default.
      // Don't force minimumFractionDigits — let Intl use the currency's
      // native minor-unit default (2 for USD, 0 for JPY, etc.).
      const val = Number(n);
      const max = maxDecimals ?? (Math.abs(val) < 1 && val !== 0 ? 4 : 2);
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: currency_code,
        maximumFractionDigits: max,
      }).format(val);
    },
    [currency_code, locale]
  );
}
