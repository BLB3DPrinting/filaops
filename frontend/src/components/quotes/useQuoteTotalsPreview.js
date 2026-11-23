/**
 * Ask the server what a save would store (POST /quotes/preview-totals), so
 * the quote form shows the same subtotal, tax and total the PDF will print.
 * Returns null until a preview for the current inputs arrives, or when the
 * request fails; callers fall back to the local estimate.
 */
import { useEffect, useState } from "react";
import { API_URL } from "../../config/api";

const DEBOUNCE_MS = 300;

export default function useQuoteTotalsPreview(body) {
  const [result, setResult] = useState({ key: null, data: null });
  const key = body ? JSON.stringify(body) : null;

  useEffect(() => {
    if (!key) return undefined;
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/quotes/preview-totals`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: key,
        });
        const data = res.ok ? await res.json() : null;
        if (!cancelled) setResult({ key, data });
      } catch {
        if (!cancelled) setResult({ key, data: null });
      }
    }, DEBOUNCE_MS);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [key]);

  // A preview for older inputs is never shown against newer ones.
  return key && result.key === key ? result.data : null;
}
