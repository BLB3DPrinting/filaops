/**
 * OperationSchedulerModal - Schedule an operation on a resource
 *
 * Allows selecting resource and time slot with conflict detection.
 */
import { useState, useEffect, useRef } from "react";
import { API_URL } from "../../config/api";
import { useResources, useResourceConflicts } from "../../hooks/useResources";
import { formatDuration, formatTime } from "../../utils/formatting";
import Modal from "../Modal";

/**
 * Conflict alert banner with next-available slot suggestion
 */
function ConflictAlert({
  conflicts,
  nextAvailableStart,
  nextAvailableEnd,
  onUseSlot,
}) {
  if (!conflicts || conflicts.length === 0) return null;

  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <svg
          className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <div className="flex-1">
          <h4 className="text-red-400 font-medium">Conflict Detected</h4>
          <p className="text-sm text-red-400/70 mt-1">
            This time slot overlaps with:
          </p>
          <ul className="mt-2 space-y-1">
            {conflicts.map((conflict, idx) => (
              <li key={idx} className="text-sm text-red-300">
                - {conflict.production_order_code || conflict.po_code} -{" "}
                {conflict.operation_code || "Operation"}
                {conflict.scheduled_start && (
                  <span className="text-red-400/50">
                    {" "}
                    ({formatTime(conflict.scheduled_start)} -{" "}
                    {formatTime(conflict.scheduled_end)})
                  </span>
                )}
              </li>
            ))}
          </ul>
          {nextAvailableStart ? (
            <div className="mt-3 p-2 bg-blue-500/10 border border-blue-500/30 rounded">
              <p className="text-sm text-blue-300">
                Next available slot: {formatTime(nextAvailableStart)} -{" "}
                {formatTime(nextAvailableEnd)}
              </p>
              <button
                type="button"
                onClick={() => onUseSlot(nextAvailableStart, nextAvailableEnd)}
                className="mt-1 text-sm text-blue-400 hover:text-blue-300 underline"
              >
                Use suggested time
              </button>
            </div>
          ) : (
            <p className="text-xs text-red-400/50 mt-2">
              Adjust the start time or select a different resource.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Compatibility warning banner
 */
function CompatibilityWarning({ reason }) {
  if (!reason) return null;

  return (
    <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
      <div className="flex items-start gap-2">
        <svg
          className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <div>
          <h4 className="text-yellow-400 font-medium text-sm">
            Incompatible Resource
          </h4>
          <p className="text-sm text-yellow-400/70 mt-1">{reason}</p>
        </div>
      </div>
    </div>
  );
}

/**
 * Success banner shown after scheduling, with option to advance to next op
 */
function ScheduleSuccess({ operationCode, nextOperation, onNext, onDone }) {
  return (
    <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <svg
          className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
        <div className="flex-1">
          <h4 className="text-green-400 font-medium">
            {operationCode} scheduled
          </h4>
          {nextOperation ? (
            <div className="mt-2 flex items-center gap-3">
              <p className="text-sm text-gray-400">
                Next: {nextOperation.sequence} — {nextOperation.operation_code}
              </p>
              <button
                type="button"
                onClick={onNext}
                className="text-sm text-blue-400 hover:text-blue-300 underline"
              >
                Schedule it now
              </button>
            </div>
          ) : (
            <p className="text-sm text-gray-400 mt-1">
              All operations scheduled.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Main modal component
 */
export default function OperationSchedulerModal({
  isOpen,
  onClose,
  operation,
  productionOrder,
  onScheduled,
}) {
  const [currentOp, setCurrentOp] = useState(null);
  const [resourceId, setResourceId] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [compatWarning, setCompatWarning] = useState(null);
  const [nextAvailableStart, setNextAvailableStart] = useState(null);
  const [nextAvailableEnd, setNextAvailableEnd] = useState(null);
  const [serverConflicts, setServerConflicts] = useState([]);
  const [justScheduled, setJustScheduled] = useState(null); // op code of just-scheduled op
  const [nextPendingOp, setNextPendingOp] = useState(null); // next op to schedule
  // Defensive: keep modal alive even if parent unmounts/remounts during conflicts
  const [forceOpen, setForceOpen] = useState(false);

  // Sync external operation prop into internal state.
  // Depends on isOpen too: if the same operation is clicked twice, the prop
  // reference hasn't changed so the effect won't re-fire — isOpen going
  // false→true forces a re-sync so currentOp is never stale on reopen.
  useEffect(() => {
    if (isOpen && operation) setCurrentOp(operation);
  }, [operation, isOpen]);

  // Debug: track unmount and isOpen changes
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      console.log("[Scheduler] Component UNMOUNTED");
    };
  }, []);
  useEffect(() => {
    console.log("[Scheduler] isOpen changed to:", isOpen);
  }, [isOpen]);

  // Get available resources for the operation's work center
  const { resources, loading: loadingResources } = useResources(
    currentOp?.work_center_id,
  );

  // Get the selected resource object to check if it's a printer
  const selectedResource = resources.find((r) => String(r.id) === resourceId);

  // Check for conflicts
  const { conflicts, checking, hasConflicts } = useResourceConflicts(
    resourceId ? parseInt(resourceId) : null,
    startTime,
    endTime,
    selectedResource?.is_printer || false,
  );

  // Calculate estimated duration
  const estimatedMinutes = currentOp
    ? (currentOp.planned_setup_minutes || 0) +
      (currentOp.planned_run_minutes || 0)
    : 0;

  // Auto-calculate end time when start time changes
  useEffect(() => {
    if (startTime && estimatedMinutes > 0) {
      const start = new Date(startTime);
      const end = new Date(start.getTime() + estimatedMinutes * 60000);
      setEndTime(end.toISOString().slice(0, 16));
    }
  }, [startTime, estimatedMinutes]);

  // Set default start time to now (rounded to next 15 min)
  useEffect(() => {
    if (isOpen && !startTime) {
      const now = new Date();
      now.setMinutes(Math.ceil(now.getMinutes() / 15) * 15, 0, 0);
      setStartTime(now.toISOString().slice(0, 16));
    }
  }, [isOpen, startTime]);

  // Pre-select resource if operation already has one
  useEffect(() => {
    if (isOpen && currentOp?.resource_id) {
      setResourceId(String(currentOp.resource_id));
    }
  }, [isOpen, currentOp]);

  // Check compatibility when resource changes
  useEffect(() => {
    setCompatWarning(null);
    if (!resourceId || !productionOrder?.id) return;

    const selectedRes = resources.find((r) => String(r.id) === resourceId);
    if (!selectedRes) return;

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
        if (res.ok) {
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
  }, [resourceId, productionOrder?.id, resources]);

  // Auto-suggest next available slot when resource is selected
  useEffect(() => {
    if (!resourceId || estimatedMinutes <= 0) return;

    const selectedRes = resources.find((r) => String(r.id) === resourceId);
    if (!selectedRes) return;

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
        if (res.ok) {
          const data = await res.json();
          if (data.next_available) {
            const start = new Date(data.next_available);
            const end = new Date(data.suggested_end);
            setStartTime(start.toISOString().slice(0, 16));
            setEndTime(end.toISOString().slice(0, 16));
          }
        }
      } catch {
        // Fall through to default time (now + duration)
      }
    };

    fetchSuggested();
  }, [resourceId, estimatedMinutes, resources]);

  // Fetch operations list to find next pending op
  const fetchNextPendingOp = async (justScheduledId) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations`,
        { credentials: "include" },
      );
      if (!res.ok) return null;
      const data = await res.json();
      const ops = Array.isArray(data) ? data : data.operations || [];
      // Find next pending op after the one we just scheduled (by sequence)
      const sorted = ops.sort((a, b) => a.sequence - b.sequence);
      return sorted.find(
        (op) => op.id !== justScheduledId && op.status === "pending",
      );
    } catch {
      return null;
    }
  };

  const resetFormState = () => {
    setResourceId("");
    setStartTime("");
    setEndTime("");
    setError(null);
    setCompatWarning(null);
    setServerConflicts([]);
    setNextAvailableStart(null);
    setNextAvailableEnd(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    console.log("[Scheduler] handleSubmit called", {
      resourceId,
      startTime,
      endTime,
      poId: productionOrder?.id,
      opId: currentOp?.id,
    });

    if (!resourceId || !startTime || !endTime) {
      setError("Please fill in all required fields");
      return;
    }

    if (hasConflicts) {
      setError(
        "Cannot schedule with conflicts. Please resolve conflicts first.",
      );
      return;
    }

    if (compatWarning) {
      setError(`Cannot schedule: ${compatWarning}`);
      return;
    }

    setSubmitting(true);
    setError(null);
    setServerConflicts([]);
    setNextAvailableStart(null);
    setNextAvailableEnd(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations/${currentOp.id}/schedule`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            resource_id: parseInt(resourceId),
            scheduled_start: new Date(startTime).toISOString(),
            scheduled_end: new Date(endTime).toISOString(),
            is_printer: selectedResource?.is_printer || false,
          }),
        },
      );

      const data = await res.json();
      console.log("[Scheduler] Response:", {
        status: res.status,
        ok: res.ok,
        data,
      });

      if (!res.ok) {
        throw new Error(data.detail || "Failed to schedule operation");
      }

      if (data.success === false) {
        console.log("[Scheduler] CONFLICT - staying open, setting error");
        setForceOpen(true);
        setServerConflicts(data.conflicts || []);
        if (data.next_available_start) {
          setNextAvailableStart(data.next_available_start);
          setNextAvailableEnd(data.next_available_end);
        }
        setError(data.message || "Scheduling conflict");
        setSubmitting(false);
        return;
      }

      // Success — notify parent, find next op, stay open
      console.log(
        "[Scheduler] SUCCESS - calling onScheduled, will NOT close modal",
      );
      onScheduled?.();
      const scheduledCode = `${currentOp.sequence} — ${currentOp.operation_code}`;
      const nextOp = await fetchNextPendingOp(currentOp.id);
      setJustScheduled(scheduledCode);
      setNextPendingOp(nextOp || null);
      resetFormState();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleAdvanceToNextOp = () => {
    if (!nextPendingOp) return;
    setCurrentOp(nextPendingOp);
    setJustScheduled(null);
    setNextPendingOp(null);
    resetFormState();
    // Set fresh default start time
    const now = new Date();
    now.setMinutes(Math.ceil(now.getMinutes() / 15) * 15, 0, 0);
    setStartTime(now.toISOString().slice(0, 16));
  };

  const handleUseSuggestedSlot = (suggestedStart, suggestedEnd) => {
    const start = new Date(suggestedStart);
    const end = new Date(suggestedEnd);
    setStartTime(start.toISOString().slice(0, 16));
    setEndTime(end.toISOString().slice(0, 16));
    setServerConflicts([]);
    setNextAvailableStart(null);
    setNextAvailableEnd(null);
    setError(null);
    setForceOpen(false);
  };

  // Close with full reset — used by X button, Done button, and advance
  const handleClose = () => {
    console.log("[Scheduler] handleClose (manual) called");
    setForceOpen(false);
    setCurrentOp(null);
    setJustScheduled(null);
    setNextPendingOp(null);
    resetFormState();
    onClose();
  };

  // Auto-close guard — used by Modal backdrop click and Escape key.
  // Blocks involuntary close when there are unacknowledged server conflicts.
  const handleAutoClose = () => {
    if (serverConflicts.length > 0 || error) {
      console.warn("[Scheduler] Blocked auto-close — conflicts/error present");
      return;
    }
    handleClose();
  };

  const effectiveOpen = isOpen || forceOpen;
  if (!effectiveOpen) return null;

  return (
    <Modal
      isOpen={effectiveOpen}
      onClose={handleAutoClose}
      title="Schedule Operation"
      disableClose={submitting}
      className="w-full max-w-lg mx-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b border-gray-800">
        <h2 className="text-xl font-semibold text-white">Schedule Operation</h2>
        <button
          onClick={handleClose}
          className="text-gray-400 hover:text-white transition-colors"
        >
          <svg
            className="w-6 h-6"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {/* Content */}
      <div className="p-6 space-y-6">
        {/* Success banner from previous schedule */}
        {justScheduled && (
          <ScheduleSuccess
            operationCode={justScheduled}
            nextOperation={nextPendingOp}
            onNext={handleAdvanceToNextOp}
            onDone={handleClose}
          />
        )}

        {/* Show form if we have an op to schedule (not in "all done" state) */}
        {currentOp && !justScheduled && (
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Operation info */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-white">
                <span className="font-medium">{currentOp.sequence}:</span>
                <span>{currentOp.operation_code}</span>
                {currentOp.operation_name && (
                  <span className="text-gray-400">
                    ({currentOp.operation_name})
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-500">
                Production Order: {productionOrder?.code}
              </div>
              <div className="text-sm text-gray-500">
                Estimated Duration: {formatDuration(estimatedMinutes)}
              </div>
            </div>

            <hr className="border-gray-800" />

            {/* Resource selector */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Resource <span className="text-red-400">*</span>
              </label>
              <select
                value={resourceId}
                onChange={(e) => setResourceId(e.target.value)}
                disabled={loadingResources}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              >
                <option value="">
                  {loadingResources ? "Loading..." : "Select a resource..."}
                </option>
                {resources.map((resource) => (
                  <option key={resource.id} value={resource.id}>
                    {resource.code} - {resource.name}
                  </option>
                ))}
              </select>
              {resources.length === 0 && !loadingResources && (
                <p className="text-xs text-gray-500 mt-1">
                  No resources available for this work center
                </p>
              )}
            </div>

            {/* Start time */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                Start Time <span className="text-red-400">*</span>
              </label>
              <input
                type="datetime-local"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* End time (auto-calculated) */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                End Time
                <span className="text-gray-600 font-normal ml-2">
                  (auto-calculated)
                </span>
              </label>
              <input
                type="datetime-local"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
            </div>

            {/* Compatibility warning */}
            <CompatibilityWarning reason={compatWarning} />

            {/* Conflict alert (live check) */}
            {checking ? (
              <div className="text-sm text-gray-500 flex items-center gap-2">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                Checking for conflicts...
              </div>
            ) : (
              <ConflictAlert
                conflicts={conflicts?.length > 0 ? conflicts : serverConflicts}
                nextAvailableStart={nextAvailableStart}
                nextAvailableEnd={nextAvailableEnd}
                onUseSlot={handleUseSuggestedSlot}
              />
            )}

            {/* Error message */}
            {error && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            <hr className="border-gray-800" />

            {/* Actions */}
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={handleClose}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Done
              </button>
              <button
                type="submit"
                disabled={
                  submitting ||
                  hasConflicts ||
                  !!compatWarning ||
                  !resourceId ||
                  !startTime
                }
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {submitting ? "Scheduling..." : "Schedule"}
              </button>
            </div>
          </form>
        )}

        {/* All done — only "Done" button */}
        {justScheduled && !nextPendingOp && (
          <div className="flex justify-end">
            <button
              type="button"
              onClick={handleClose}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
