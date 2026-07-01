/**
 * LegacyFulfillmentBanner - LEGACY-1 amber data-health banner + confirm
 * dialog for orders whose status claims shipment without evidence.
 *
 * Extracted from OrderDetail.jsx (DEBT-1 D1-C). Markup and handler moved
 * verbatim; the page decides visibility and refreshes data via onResolved.
 */
import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../Toast";

export default function LegacyFulfillmentBanner({ order, orderId, onResolved }) {
  const api = useApi();
  const toast = useToast();

  // LEGACY-1: legacy fulfillment resolution state
  // legacyResolveAction is "close_out" | "reopen" | null (null = modal closed)
  const [legacyResolveAction, setLegacyResolveAction] = useState(null);
  const [resolvingLegacy, setResolvingLegacy] = useState(false);

  // LEGACY-1: resolve a legacy fulfillment mismatch (close_out | reopen)
  const handleResolveLegacyFulfillment = async () => {
    if (!legacyResolveAction) return;
    setResolvingLegacy(true);
    try {
      await api.post(
        `/api/v1/sales-orders/${orderId}/resolve-legacy-fulfillment`,
        { action: legacyResolveAction }
      );
      toast.success(
        legacyResolveAction === "close_out"
          ? `Order ${order.order_number} closed out — fulfillment recorded`
          : `Order ${order.order_number} reopened — ready to ship`
      );
      setLegacyResolveAction(null);
      onResolved();
    } catch (err) {
      toast.error(err.message || "Failed to resolve legacy fulfillment");
    } finally {
      setResolvingLegacy(false);
    }
  };

  return (
    <>
        <div className="rounded-xl border border-[var(--status-amber)]/40 bg-[var(--status-amber-tint)] p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 shrink-0 text-[var(--status-amber)] mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-[var(--status-amber)]">
                  Legacy data issue: no shipment on record
                </p>
                <p className="mt-1 text-sm text-[var(--status-amber)]/80">
                  This order&apos;s status says{" "}
                  <span className="font-medium capitalize">
                    {order.status.replace(/_/g, " ")}
                  </span>
                  , but no shipment was ever recorded — likely data from an
                  older FilaOps version.
                </p>
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <button
                onClick={() => setLegacyResolveAction("close_out")}
                className="rounded-lg bg-[var(--orange)] px-3 py-2 text-sm font-medium text-white hover:bg-[var(--orange-press)]"
              >
                Close Out as Fulfilled
              </button>
              <button
                onClick={() => setLegacyResolveAction("reopen")}
                className="rounded-lg border border-[var(--rule-hair)] bg-[var(--paper-sunk)] px-3 py-2 text-sm font-medium text-[var(--ink-2)] hover:bg-[var(--rule-hair)]"
              >
                Reopen for Shipping
              </button>
            </div>
          </div>
        </div>

      {/* LEGACY-1: confirm dialog for legacy fulfillment resolution */}
      {legacyResolveAction && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => !resolvingLegacy && setLegacyResolveAction(null)}
        >
          <div
            className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-6 max-w-md w-full mx-4 shadow-[var(--shadow-pop)]"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-[var(--ink)] mb-2">
              {legacyResolveAction === "close_out"
                ? "Close Out as Fulfilled"
                : "Reopen for Shipping"}
            </h3>
            {legacyResolveAction === "close_out" ? (
              <p className="text-[var(--ink-3)] text-sm mb-4">
                This records the order as fully shipped (paperwork only). No
                inventory movements or accounting entries are created — the
                goods already left under an older FilaOps version. An audit
                note is added to the order.
              </p>
            ) : (
              <p className="text-[var(--ink-3)] text-sm mb-4">
                This sets the order back to Ready to Ship so you can ship it
                through the normal flow (which records inventory and
                accounting). Invoice and payment are left untouched. An audit
                note is added to the order.
              </p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setLegacyResolveAction(null)}
                disabled={resolvingLegacy}
                className="px-4 py-2 bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] rounded-lg hover:bg-[var(--rule-hair)] disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleResolveLegacyFulfillment}
                disabled={resolvingLegacy}
                className="px-4 py-2 bg-[var(--orange)] text-white rounded-lg hover:bg-[var(--orange-press)] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {resolvingLegacy
                  ? "Working..."
                  : legacyResolveAction === "close_out"
                  ? "Close Out"
                  : "Reopen Order"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
