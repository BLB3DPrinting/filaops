/**
 * AutoPickSlotButton — PRO-gated auto-scheduler affordance.
 *
 * Extracted verbatim from OperationSchedulerModal.jsx (DEBT-1 D2-B). Markup,
 * classes, fetch logic, and props are unchanged.
 *
 * Calls POST /api/v1/pro/auto-schedule with the operation + production order
 * context.  If the endpoint returns 404/403 (Core install without PRO), shows
 * a polite "PRO feature" note instead of an error.
 *
 * On success the returned slot is applied to startTime / endTime.
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../../config/api";

export default function AutoPickSlotButton({ operationId, productionOrderId, onSlotPicked, disabled }) {
  const [running, setRunning] = useState(false);
  const [proUnavailable, setProUnavailable] = useState(false);
  const [pickError, setPickError] = useState(null);

  // PRO availability is per-install, but reset on operation change so a
  // transient 403 (e.g. session blip) doesn't stick for the whole session.
  useEffect(() => {
    setProUnavailable(false);
    setPickError(null);
  }, [operationId]);

  const handleClick = async () => {
    setRunning(true);
    setProUnavailable(false);
    setPickError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/pro/auto-schedule`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ operation_id: operationId, production_order_id: productionOrderId }),
      });
      if (res.status === 404 || res.status === 403) {
        setProUnavailable(true);
        return;
      }
      if (!res.ok) {
        let message = "Auto-pick failed — schedule manually";
        try {
          const errData = await res.json();
          message = errData.detail?.message || errData.detail || message;
        } catch {
          // non-JSON error body — keep generic message
        }
        setPickError(typeof message === "string" ? message : "Auto-pick failed — schedule manually");
        return;
      }
      const data = await res.json();
      if (data.scheduled_start && data.scheduled_end) {
        onSlotPicked(data.scheduled_start, data.scheduled_end);
      }
    } catch {
      setPickError("Network error — schedule manually");
    } finally {
      setRunning(false);
    }
  };

  if (proUnavailable) {
    return (
      <span className="text-xs text-gray-500 italic">
        Auto-pick requires FilaOps PRO
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || running || !operationId}
        className="text-xs text-purple-400 hover:text-purple-300 border border-purple-500/30 hover:border-purple-400/50 rounded px-2 py-1 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        title="Use the PRO auto-scheduler to find the optimal slot"
      >
        {running ? "Finding slot…" : "Auto-pick slot ✦"}
      </button>
      {pickError && (
        <span className="text-xs text-amber-400">{pickError}</span>
      )}
    </span>
  );
}
