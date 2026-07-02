/**
 * AutoPickSlotButton — PRO-gated auto-scheduler affordance.
 *
 * Extracted from OperationSchedulerModal.jsx (DEBT-1 D2-B).
 *
 * Calls POST /api/v1/scheduling/auto-schedule?order_id=<productionOrderId> —
 * the Core scheduling route gated by require_feature("production_advanced")
 * (PR #861). The endpoint takes the production order id as a query param (not
 * a JSON body) and does not use the operation id. If it returns 404/403 (a PRO
 * install whose wheel lacks the endpoint, or the feature not loaded), shows a
 * polite "PRO feature" note instead of an error.
 *
 * On success the returned slot is applied to startTime / endTime.
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../../config/api";
import { useFeatureFlags } from "../../../hooks/useFeatureFlags";

export default function AutoPickSlotButton({ operationId, productionOrderId, onSlotPicked, disabled }) {
  const { isPro, loading: flagsLoading } = useFeatureFlags();
  const [running, setRunning] = useState(false);
  const [proUnavailable, setProUnavailable] = useState(false);
  const [pickError, setPickError] = useState(null);

  // PRO availability is per-install, but reset on operation change so a
  // transient 403 (e.g. session blip) doesn't stick for the whole session.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Intentional reset of local availability/error state when the target operation changes.
    setProUnavailable(false);
    setPickError(null);
  }, [operationId]);

  const handleClick = async () => {
    setRunning(true);
    setProUnavailable(false);
    setPickError(null);
    try {
      // order_id is a query param on the Core scheduling route (not a JSON
      // body). productionOrderId maps to the endpoint's order_id.
      const res = await fetch(
        `${API_URL}/api/v1/scheduling/auto-schedule?order_id=${encodeURIComponent(productionOrderId)}`,
        {
          method: "POST",
          credentials: "include",
        },
      );
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

  // Proactively gate on tier: the /auto-schedule endpoint is PRO-only
  // (require_feature("production_advanced")), so on community show the upsell
  // note up front instead of firing a request that would only 403. The
  // proUnavailable branch also covers a PRO tier whose install lacks the
  // endpoint (older wheel / feature not loaded).
  //
  // Wait for feature flags to hydrate before showing the locked note: isPro
  // derives from tier, which is undefined while flagsLoading is true, so
  // branching on !isPro too early would flash "requires FilaOps PRO" at PRO
  // users. While loading, render the neutral (disabled) button and only
  // resolve the locked vs. active state once flags are known.
  if (!flagsLoading && (!isPro || proUnavailable)) {
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
        disabled={disabled || running || !operationId || flagsLoading}
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
