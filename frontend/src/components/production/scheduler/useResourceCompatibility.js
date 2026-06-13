/**
 * useResourceCompatibility — live resource/operation compatibility check.
 *
 * Extracted verbatim from OperationSchedulerModal.jsx (DEBT-1 D2-B). The effect
 * body, dependency array, fetch call, and cancellation guard are unchanged —
 * only lifted into a hook with explicit inputs.
 *
 * When the selected resource changes, GETs the production order's
 * check-resource-compatibility endpoint and reports an incompatibility reason
 * via the supplied setCompatWarning setter.
 */
import { useEffect } from "react";
import { API_URL } from "../../../config/api";

export function useResourceCompatibility({
  resourceId,
  productionOrder,
  resources,
  setCompatWarning,
}) {
  // Check compatibility when resource changes
  useEffect(() => {
    setCompatWarning(null);
    if (!resourceId || !productionOrder?.id) return;

    const selectedRes = resources.find((r) => String(r.id) === resourceId);
    if (!selectedRes) return;

    let cancelled = false;

    const checkCompat = async () => {
      try {
        const params = new URLSearchParams({
          resource_id: resourceId,
          is_printer: selectedRes.is_printer ? "true" : "false",
        });
        const res = await fetch(
          `${API_URL}/api/v1/production-orders/${productionOrder.id}/check-resource-compatibility?${params}`,
          { credentials: "include" },
        );
        if (res.ok && !cancelled) {
          const data = await res.json();
          if (!data.compatible) {
            setCompatWarning(data.reason);
          }
        }
      } catch {
        // Silently ignore - backend will still reject on submit
      }
    };

    checkCompat();
    return () => { cancelled = true; };
  }, [resourceId, productionOrder?.id, resources]);
}
