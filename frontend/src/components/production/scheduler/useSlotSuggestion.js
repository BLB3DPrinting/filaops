/**
 * useSlotSuggestion — auto-suggest the next available slot for a resource.
 *
 * Extracted verbatim from OperationSchedulerModal.jsx (DEBT-1 D2-B). The effect
 * body, dependency array, fetch call, and cancellation guard are unchanged —
 * only lifted into a hook with explicit inputs.
 *
 * When a resource is selected (and not in edit mode), POSTs to
 * /production-orders/resources/next-available and applies the returned slot via
 * the supplied setStartTime / setEndTime setters.
 */
import { useEffect } from "react";
import { API_URL } from "../../../config/api";
import { toLocalInputValue } from "../../../utils/formatting";

export function useSlotSuggestion({
  resourceId,
  estimatedMinutes,
  resources,
  isEditMode,
  setStartTime,
  setEndTime,
}) {
  // Auto-suggest next available slot when resource is selected — skip in edit mode
  // because the operator can see the current slot and change it deliberately.
  useEffect(() => {
    if (!resourceId || estimatedMinutes <= 0) return;
    if (isEditMode) return;

    const selectedRes = resources.find((r) => String(r.id) === resourceId);
    if (!selectedRes) return;

    let cancelled = false;

    const fetchSuggested = async () => {
      try {
        const res = await fetch(
          `${API_URL}/api/v1/production-orders/resources/next-available`,
          {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              resource_id: parseInt(resourceId),
              duration_minutes: estimatedMinutes,
              is_printer: selectedRes.is_printer || false,
            }),
          },
        );
        if (res.ok && !cancelled) {
          const data = await res.json();
          if (data.next_available && !cancelled) {
            setStartTime(toLocalInputValue(data.next_available));
            setEndTime(toLocalInputValue(data.suggested_end));
          }
        }
      } catch {
        // Fall through to default time (now + duration)
      }
    };

    fetchSuggested();
    return () => { cancelled = true; };
  }, [resourceId, estimatedMinutes, resources]); // eslint-disable-line react-hooks/exhaustive-deps -- matches original effect dependency array (DEBT-1 D2-B verbatim move)
}
