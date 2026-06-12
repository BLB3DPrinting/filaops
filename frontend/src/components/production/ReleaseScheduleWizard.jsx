/**
 * ReleaseScheduleWizard
 *
 * SCHED-3b: Guided initial-schedule-on-release wizard.
 *
 * After a production order is successfully released to the floor, this
 * component offers the operator a chance to schedule its operations
 * immediately rather than finding the Schedule button later.
 *
 * Entry: shows a non-blocking "Schedule it now?" offer dialog.
 * Accept: opens OperationSchedulerModal in wizard mode, walking every
 *         schedulable operation in sequence order, pre-filled with a
 *         dispatch suggestion (resource + slot), predecessor timing chained
 *         across steps (step N start >= step N-1 end).
 * Dismiss: release already happened; scheduling is deferred — no gate.
 *
 * Architecture: thin wrapper around OperationSchedulerModal.
 * The modal's existing sequential mode (fetchNextPendingOp →
 * handleAdvanceToNextOp → ScheduleSuccess) is the scheduling chassis.
 * This component adds only:
 *   • The entry "Schedule now?" offer prompt
 *   • wizardMode prop to the modal for step counter + Skip button
 *   • Suggestion pre-fill: fetches first pending op and its dispatch
 *     suggestion, passes suggestionHint to the modal
 *   • Predecessor chaining: modal reports chosen end time back here;
 *     we pass it as earliestStart for the next step
 */
import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../../config/api";
import Modal from "../Modal";
import OperationSchedulerModal from "./OperationSchedulerModal";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Fetch all operations for a production order and return those that are
 * schedulable (status === "pending"), sorted by sequence.
 */
async function fetchPendingOps(productionOrderId) {
  const res = await fetch(
    `${API_URL}/api/v1/production-orders/${productionOrderId}/operations`,
    { credentials: "include" }
  );
  if (!res.ok) return [];
  const data = await res.json();
  const ops = Array.isArray(data) ? data : data.operations || [];
  return ops
    .filter((op) => op.status === "pending")
    .sort((a, b) => a.sequence - b.sequence);
}

/**
 * Fetch a dispatch suggestion for a specific operation.
 * Uses the next-available endpoint to get a suggested start/end slot.
 * Falls back gracefully if the endpoint is unavailable.
 *
 * Returns { resourceId, startTime, endTime, maintenanceWarning } or null.
 */
async function fetchSuggestionForOp(op, earliestStart) {
  try {
    // Derive estimated duration from op routing fields
    const toMin = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
    const estimatedMinutes =
      toMin(op.planned_setup_minutes) + toMin(op.planned_run_minutes);

    // Get dispatch suggestions to find best resource for this operation's
    // work center.  We call the existing suggestions endpoint and look for
    // a result matching this operation.
    const suggestRes = await fetch(
      `${API_URL}/api/v1/dispatch/suggestions`,
      { credentials: "include" }
    );

    let suggestedResourceId = op.resource_id || op.printer_id || null;
    let maintenanceWarning = null;

    if (suggestRes.ok) {
      const suggestData = await suggestRes.json();
      // Walk results: find a printer whose top_suggestion matches our op_id
      for (const result of suggestData.results || []) {
        const top = result.top_suggestion;
        if (top && top.operation_id === op.id) {
          // Use this printer as the suggested resource
          suggestedResourceId = result.printer?.id ?? suggestedResourceId;
          maintenanceWarning = top.maintenance_warning ?? null;
          break;
        }
      }
    }

    // If we have a resource, get its next available slot (respecting
    // earliestStart for predecessor chaining).
    if (suggestedResourceId && estimatedMinutes > 0) {
      // Determine if it's a printer resource
      const isPrinter = op.printer_id != null;

      const slotRes = await fetch(
        `${API_URL}/api/v1/production-orders/resources/next-available`,
        {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            resource_id: parseInt(suggestedResourceId),
            duration_minutes: estimatedMinutes,
            is_printer: isPrinter,
            // Predecessor chaining: earliest start is the previous step's end
            after: earliestStart || undefined,
          }),
        }
      );

      if (slotRes.ok) {
        const slotData = await slotRes.json();
        if (slotData.next_available) {
          // Pass the server's UTC ISO strings through untouched — the modal
          // converts them to local wall time (toLocalInputValue) exactly once
          // when seeding the datetime-local inputs. Slicing toISOString()
          // here would inject UTC into a local-by-definition input.
          return {
            resourceId: String(suggestedResourceId),
            startTime: slotData.next_available,
            endTime: slotData.suggested_end,
            maintenanceWarning,
          };
        }
      }
    }

    // Fallback: suggest a resource (if any) but leave slot as now
    if (suggestedResourceId) {
      // Compute a start from earliestStart or now (rounded to 15 min)
      const base = earliestStart ? new Date(earliestStart) : new Date();
      if (!earliestStart) {
        base.setMinutes(Math.ceil(base.getMinutes() / 15) * 15, 0, 0);
      }
      const end =
        estimatedMinutes > 0
          ? new Date(base.getTime() + estimatedMinutes * 60000)
          : new Date(base.getTime() + 60 * 60000);
      // Full UTC ISO strings (with 'Z') — the modal localizes them once.
      return {
        resourceId: String(suggestedResourceId),
        startTime: base.toISOString(),
        endTime: end.toISOString(),
        maintenanceWarning,
      };
    }

    return null;
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Offer prompt (step 0)
// ---------------------------------------------------------------------------

function OfferPrompt({ orderCode, pendingCount, loading, onAccept, onDismiss }) {
  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start gap-4">
        <div className="flex-shrink-0 w-10 h-10 bg-blue-500/20 rounded-full flex items-center justify-center">
          <svg
            className="w-5 h-5 text-blue-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-white font-semibold">
            {orderCode} released to floor
          </h3>
          {loading ? (
            <p className="text-gray-400 text-sm mt-1">
              Checking schedulable operations…
            </p>
          ) : pendingCount > 0 ? (
            <p className="text-gray-400 text-sm mt-1">
              {pendingCount === 1
                ? "This order has 1 operation ready to schedule."
                : `This order has ${pendingCount} operations ready to schedule.`}{" "}
              Schedule them now to assign resources and time slots.
            </p>
          ) : (
            <p className="text-gray-400 text-sm mt-1">
              No schedulable operations found — you can schedule them later
              from the operations panel.
            </p>
          )}
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onDismiss}
          className="px-4 py-2 text-gray-400 hover:text-white text-sm transition-colors"
        >
          Later
        </button>
        {!loading && pendingCount > 0 && (
          <button
            type="button"
            onClick={onAccept}
            className="px-5 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
          >
            Schedule now
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary screen (shown after wizard finishes or all ops are skipped)
// ---------------------------------------------------------------------------

function WizardSummary({ scheduled, skipped, productionOrderId, onClose, onOpenScheduler }) {
  const hasScheduled = scheduled.length > 0;

  return (
    <div className="p-6 space-y-4">
      <div className="space-y-3">
        {hasScheduled ? (
          <>
            <h3 className="text-green-400 font-semibold flex items-center gap-2">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              {scheduled.length === 1
                ? "1 operation scheduled"
                : `${scheduled.length} operations scheduled`}
            </h3>
            <ul className="space-y-1 text-sm">
              {scheduled.map((s, idx) => (
                <li key={idx} className="text-gray-300">
                  <span className="font-medium">{s.operationLabel}</span>
                  {s.resourceName && (
                    <span className="text-gray-400"> — {s.resourceName}</span>
                  )}
                  {s.startTime && (
                    <span className="text-gray-500 ml-1">
                      @ {new Date(s.startTime).toLocaleString(undefined, {
                        month: "short", day: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-gray-400 text-sm">
            No operations were scheduled. You can schedule them anytime from
            the operations panel.
          </p>
        )}

        {skipped.length > 0 && (
          <div className="text-sm text-gray-500">
            Skipped: {skipped.join(", ")}
          </div>
        )}
      </div>

      {hasScheduled && (
        <div className="pt-2 border-t border-gray-800">
          <button
            type="button"
            onClick={onOpenScheduler}
            className="text-sm text-blue-400 hover:text-blue-300 underline"
          >
            Open scheduler for adjustments
          </button>
        </div>
      )}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={onClose}
          className="px-5 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
        >
          Done
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

/**
 * ReleaseScheduleWizard
 *
 * Props:
 *   isOpen          — whether the wizard is mounted (set true on release success)
 *   productionOrder — the just-released production order object
 *   onClose         — called when the wizard is dismissed or finishes
 *   onOpenScheduler — called when operator clicks "Open scheduler" from summary
 *                     (parent opens OperationSchedulerModal in edit mode)
 *   onRefresh       — called after scheduling to trigger parent data refresh
 */
export default function ReleaseScheduleWizard({
  isOpen,
  productionOrder,
  onClose,
  onOpenScheduler,
  onRefresh,
}) {
  // Wizard phases: "offer" | "scheduling" | "summary"
  const [phase, setPhase] = useState("offer");

  // Pending operations fetched when offer is shown
  const [pendingOps, setPendingOps] = useState([]);
  const [loadingOps, setLoadingOps] = useState(false);

  // Suggestion for current op (pre-fill for the modal)
  const [currentSuggestion, setCurrentSuggestion] = useState(null);
  // The index into pendingOps we're currently scheduling
  const [currentOpIndex, setCurrentOpIndex] = useState(0);
  // Earliest start for the next op — predecessor chaining
  const [predecessorEnd, setPredecessorEnd] = useState(null);

  // Accumulated results for summary
  const [scheduled, setScheduled] = useState([]); // { operationLabel, resourceName, startTime }
  const [skipped, setSkipped] = useState([]);     // operation labels

  // Is the OperationSchedulerModal open?
  const [modalOpen, setModalOpen] = useState(false);

  // Reset on open
  useEffect(() => {
    if (!isOpen) return;
    setPhase("offer");
    setPendingOps([]);
    setLoadingOps(false);
    setCurrentSuggestion(null);
    setCurrentOpIndex(0);
    setPredecessorEnd(null);
    setScheduled([]);
    setSkipped([]);
    setModalOpen(false);
  }, [isOpen]);

  // Fetch pending ops when offer is shown
  useEffect(() => {
    if (!isOpen || !productionOrder?.id) return;
    setLoadingOps(true);
    fetchPendingOps(productionOrder.id)
      .then(setPendingOps)
      .catch(() => setPendingOps([]))
      .finally(() => setLoadingOps(false));
  }, [isOpen, productionOrder?.id]);

  // Current op being scheduled
  const currentOp = pendingOps[currentOpIndex] ?? null;

  // Fetch suggestion for current op whenever we enter scheduling phase
  // or advance to a new op
  useEffect(() => {
    if (phase !== "scheduling" || !currentOp) return;
    setCurrentSuggestion(null);

    fetchSuggestionForOp(currentOp, predecessorEnd)
      .then(setCurrentSuggestion)
      .catch(() => setCurrentSuggestion(null));
  }, [phase, currentOp?.id, predecessorEnd]); // eslint-disable-line react-hooks/exhaustive-deps

  // Open the modal once we have the suggestion (or after a short grace period)
  useEffect(() => {
    if (phase !== "scheduling" || !currentOp) return;
    setModalOpen(true);
  }, [phase, currentOp?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAccept = useCallback(() => {
    if (pendingOps.length === 0) {
      onClose?.();
      return;
    }
    setCurrentOpIndex(0);
    setPredecessorEnd(null);
    setScheduled([]);
    setSkipped([]);
    setPhase("scheduling");
  }, [pendingOps, onClose]);

  const handleDismiss = useCallback(() => {
    onClose?.();
  }, [onClose]);

  /**
   * Called by OperationSchedulerModal's onScheduled callback.
   * We get the scheduled result from the modal and advance to the next op.
   *
   * scheduledInfo: { operationId, operationLabel, resourceName, startTime, endTime }
   */
  const handleOperationScheduled = useCallback(
    (scheduledInfo) => {
      onRefresh?.();
      setScheduled((prev) => [
        ...prev,
        {
          operationLabel: scheduledInfo?.operationLabel ?? currentOp?.operation_code ?? "Operation",
          resourceName: scheduledInfo?.resourceName ?? null,
          startTime: scheduledInfo?.startTime ?? null,
        },
      ]);

      // Chain predecessor timing: next op's earliest start = this op's end
      if (scheduledInfo?.endTime) {
        setPredecessorEnd(scheduledInfo.endTime);
      }

      // Advance to next op or finish
      const nextIndex = currentOpIndex + 1;
      if (nextIndex < pendingOps.length) {
        setCurrentOpIndex(nextIndex);
        // Modal will naturally advance via its own handleAdvanceToNextOp;
        // we close and re-open for the new op so suggestion is re-fetched
        setModalOpen(false);
        // A tiny delay lets state settle before the next op's suggestion fetch
        setTimeout(() => {
          setModalOpen(true);
        }, 50);
      } else {
        // All ops done
        setModalOpen(false);
        setPhase("summary");
      }
    },
    [currentOp, currentOpIndex, pendingOps.length, onRefresh]
  );

  /**
   * Called when operator skips the current op.
   */
  const handleSkip = useCallback(() => {
    setSkipped((prev) => [
      ...prev,
      currentOp
        ? `${currentOp.sequence} — ${currentOp.operation_code}`
        : "Operation",
    ]);

    const nextIndex = currentOpIndex + 1;
    if (nextIndex < pendingOps.length) {
      setCurrentOpIndex(nextIndex);
      setModalOpen(false);
      setTimeout(() => {
        setModalOpen(true);
      }, 50);
    } else {
      setModalOpen(false);
      setPhase("summary");
    }
  }, [currentOp, currentOpIndex, pendingOps.length]);

  /**
   * Called when operator clicks "Later" or "Skip all" from inside the modal.
   */
  const handleModalClose = useCallback(() => {
    setModalOpen(false);
    setPhase("summary");
  }, []);

  const handleSummaryClose = useCallback(() => {
    onClose?.();
  }, [onClose]);

  if (!isOpen) return null;

  const orderCode = productionOrder?.code ?? "Order";

  // ---- Offer phase --------------------------------------------------------
  if (phase === "offer") {
    return (
      <Modal
        isOpen={true}
        onClose={handleDismiss}
        title="Order Released"
        className="w-full max-w-md mx-4"
      >
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <h2 className="text-xl font-semibold text-white">Order Released</h2>
          <button
            onClick={handleDismiss}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <OfferPrompt
          orderCode={orderCode}
          pendingCount={pendingOps.length}
          loading={loadingOps}
          onAccept={handleAccept}
          onDismiss={handleDismiss}
        />
      </Modal>
    );
  }

  // ---- Summary phase -------------------------------------------------------
  if (phase === "summary") {
    return (
      <Modal
        isOpen={true}
        onClose={handleSummaryClose}
        title="Schedule Summary"
        className="w-full max-w-md mx-4"
      >
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <h2 className="text-xl font-semibold text-white">Schedule Summary</h2>
          <button
            onClick={handleSummaryClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <WizardSummary
          scheduled={scheduled}
          skipped={skipped}
          productionOrderId={productionOrder?.id}
          onClose={handleSummaryClose}
          onOpenScheduler={() => {
            handleSummaryClose();
            onOpenScheduler?.();
          }}
        />
      </Modal>
    );
  }

  // ---- Scheduling phase (modal per op) ------------------------------------
  // The OperationSchedulerModal handles the actual scheduling UX.
  // We pass wizardMode props to enable the step counter and Skip button.
  return (
    <OperationSchedulerModal
      isOpen={modalOpen}
      onClose={handleModalClose}
      operation={currentOp}
      productionOrder={productionOrder}
      onScheduled={handleOperationScheduled}
      // Wizard-mode props
      wizardMode={true}
      wizardStep={currentOpIndex + 1}
      wizardTotal={pendingOps.length}
      wizardSuggestion={currentSuggestion}
      onWizardSkip={handleSkip}
    />
  );
}
