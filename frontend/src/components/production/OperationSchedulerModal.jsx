/**
 * OperationSchedulerModal - Schedule an operation on a resource
 *
 * Allows selecting resource and time slot with conflict detection.
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useResources, useResourceConflicts } from "../../hooks/useResources";
import { formatDuration, formatTime } from "../../utils/formatting";
import Modal from "../Modal";

/**
 * Shared slot suggestion pill — used by both conflict alert banners.
 */
function SlotSuggestion({ label, nextAvailableStart, nextAvailableEnd, onUseSlot }) {
  if (!nextAvailableStart) return null;
  return (
    <div className="mt-3 p-2 bg-blue-500/10 border border-blue-500/30 rounded">
      <p className="text-sm text-blue-300">
        {label}: {formatTime(nextAvailableStart)}
        {nextAvailableEnd ? ` – ${formatTime(nextAvailableEnd)}` : ""}
      </p>
      <button
        type="button"
        onClick={() => onUseSlot(nextAvailableStart, nextAvailableEnd)}
        className="mt-1 text-sm text-blue-400 hover:text-blue-300 underline"
      >
        Use this time
      </button>
    </div>
  );
}

/**
 * Conflict alert banner with next-available slot suggestion (resource conflicts)
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
          <h4 className="text-red-400 font-medium">Resource Conflict</h4>
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
                    ({formatTime(conflict.scheduled_start)} –{" "}
                    {formatTime(conflict.scheduled_end)})
                  </span>
                )}
              </li>
            ))}
          </ul>
          <SlotSuggestion
            label="Earliest available slot"
            nextAvailableStart={nextAvailableStart}
            nextAvailableEnd={nextAvailableEnd}
            onUseSlot={onUseSlot}
          />
          {!nextAvailableStart && (
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
 * Predecessor sequence violation banner with earliest-valid-start suggestion.
 */
function PredecessorAlert({
  message,
  earliestValidStart,
  nextAvailableStart,
  nextAvailableEnd,
  onUseSlot,
}) {
  if (!message) return null;

  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <svg
          className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5"
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
          <h4 className="text-amber-400 font-medium">Sequence Constraint</h4>
          <p className="text-sm text-amber-400/70 mt-1">{message}</p>
          {earliestValidStart && (
            <p className="text-sm text-amber-300 mt-1">
              Predecessor finishes:{" "}
              <span className="font-medium">{formatTime(earliestValidStart)}</span>
            </p>
          )}
          {nextAvailableStart ? (
            <SlotSuggestion
              label="Earliest valid start"
              nextAvailableStart={nextAvailableStart}
              nextAvailableEnd={nextAvailableEnd}
              onUseSlot={onUseSlot}
            />
          ) : (
            <p className="text-xs text-amber-400/50 mt-2">
              Schedule the predecessor operation first, then retry.
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
function ScheduleSuccess({ operationCode, nextOperation, onNext }) {
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
 * Unschedule confirmation inline panel.
 */
function UnscheduleConfirm({ onConfirm, onCancel, submitting }) {
  return (
    <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
      <p className="text-amber-300 font-medium text-sm">
        Unschedule this operation?
      </p>
      <p className="text-amber-400/70 text-sm mt-1">
        The operation will return to pending and its time slot will be freed.
      </p>
      <div className="flex gap-3 mt-3">
        <button
          type="button"
          onClick={onConfirm}
          disabled={submitting}
          className="px-4 py-1.5 bg-amber-600 text-white text-sm rounded-lg hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? "Unscheduling..." : "Confirm Unschedule"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-1.5 text-gray-400 hover:text-white text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

/**
 * Successor conflict banner — shown when moving an op would violate a
 * downstream op's existing schedule.
 */
function SuccessorConflictAlert({ successorConflicts }) {
  if (!successorConflicts || successorConflicts.length === 0) return null;
  return (
    <div className="bg-orange-500/10 border border-orange-500/30 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <svg
          className="w-5 h-5 text-orange-400 flex-shrink-0 mt-0.5"
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
          <h4 className="text-orange-400 font-medium">Successor Conflict</h4>
          <p className="text-sm text-orange-400/70 mt-1">
            Moving this operation would violate existing schedules of:
          </p>
          <ul className="mt-2 space-y-1">
            {successorConflicts.map((sc, idx) => (
              <li key={idx} className="text-sm text-orange-300">
                - Seq {sc.sequence} ({sc.operation_code || "Operation"})
                {sc.scheduled_start && (
                  <span className="text-orange-400/50">
                    {" "}currently at {formatTime(sc.scheduled_start)}
                  </span>
                )}
                {sc.earliest_valid_start && (
                  <span className="text-orange-300">
                    {" "}— earliest valid start: {formatTime(sc.earliest_valid_start)}
                  </span>
                )}
              </li>
            ))}
          </ul>
          <p className="text-xs text-orange-400/50 mt-2">
            Reschedule the successor operations first, or choose an earlier end time.
          </p>
        </div>
      </div>
    </div>
  );
}

/**
 * Auto-pick slot — PRO-gated affordance.
 *
 * Calls POST /api/v1/pro/auto-schedule with the operation + production order
 * context.  If the endpoint returns 404/403 (Core install without PRO), shows
 * a polite "PRO feature" note instead of an error.
 *
 * On success the returned slot is applied to startTime / endTime.
 */
function AutoPickSlotButton({ operationId, productionOrderId, onSlotPicked, disabled }) {
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

/**
 * Wizard step header — shown when wizardMode is true.
 */
function WizardStepHeader({ step, total, onSkipAll }) {
  return (
    <div className="flex items-center justify-between px-6 py-3 bg-blue-950/30 border-b border-blue-800/30">
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-blue-300 uppercase tracking-wide">
          Schedule Wizard
        </span>
        <span className="text-xs text-gray-500">
          Step {step} of {total}
        </span>
        {/* Progress dots */}
        <div className="flex gap-1">
          {Array.from({ length: total }, (_, i) => (
            <span
              key={i}
              className={`w-1.5 h-1.5 rounded-full ${
                i < step ? "bg-blue-400" : "bg-gray-700"
              }`}
            />
          ))}
        </div>
      </div>
      <button
        type="button"
        onClick={onSkipAll}
        className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
      >
        Skip all / later
      </button>
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
  // Wizard-mode props (SCHED-3b)
  wizardMode = false,
  wizardStep = 1,
  wizardTotal = 1,
  wizardSuggestion = null, // { resourceId, startTime, endTime, maintenanceWarning }
  onWizardSkip = null,
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
  // Predecessor-specific conflict state
  const [predecessorConflict, setPredecessorConflict] = useState(null); // { message, earliestValidStart }
  // Successor conflict state
  const [successorConflicts, setSuccessorConflicts] = useState([]);
  const [justScheduled, setJustScheduled] = useState(null); // op code of just-scheduled op
  const [nextPendingOp, setNextPendingOp] = useState(null); // next op to schedule
  // Defensive: keep modal alive even if parent unmounts/remounts during conflicts
  const [forceOpen, setForceOpen] = useState(false);
  // Unschedule confirm state
  const [showUnscheduleConfirm, setShowUnscheduleConfirm] = useState(false);

  // Derived: is this an already-scheduled op? → edit mode.
  const isEditMode =
    currentOp != null &&
    (currentOp.status === "queued" ||
      (currentOp.scheduled_start != null && currentOp.status !== "pending"));

  // Sync external operation prop into internal state.
  // Depends on isOpen too: if the same operation is clicked twice, the prop
  // reference hasn't changed so the effect won't re-fire — isOpen going
  // false→true forces a re-sync so currentOp is never stale on reopen.
  useEffect(() => {
    if (isOpen && operation) setCurrentOp(operation);
  }, [operation, isOpen]);

  // Wizard suggestion pre-fill: when a suggestion is provided (SCHED-3b),
  // apply it as the initial resource + slot.  Only fires in wizard mode
  // and only when the modal opens fresh (not in edit mode).
  useEffect(() => {
    if (!wizardMode || !isOpen || !wizardSuggestion || isEditMode) return;
    if (wizardSuggestion.resourceId) {
      setResourceId(wizardSuggestion.resourceId);
    }
    if (wizardSuggestion.startTime) {
      setStartTime(wizardSuggestion.startTime);
    }
    if (wizardSuggestion.endTime) {
      setEndTime(wizardSuggestion.endTime);
    }
  }, [wizardMode, isOpen, wizardSuggestion, isEditMode]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Parse a Numeric-as-string value from the API into a finite number.
  // The backend serializes SQLAlchemy Numeric columns as strings ("3.00",
  // "150.00").  Using plain `|| 0` with string values concatenates instead
  // of adding, e.g. "3.00" + "150.00" = "3.00150.00" → NaN downstream.
  const toMin = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };

  // Calculate estimated duration
  const estimatedMinutes = currentOp
    ? toMin(currentOp.planned_setup_minutes) + toMin(currentOp.planned_run_minutes)
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

  // Pre-select resource if operation already has one (covers both resource and printer)
  useEffect(() => {
    if (isOpen && currentOp) {
      if (currentOp.printer_id) {
        setResourceId(String(currentOp.printer_id));
      } else if (currentOp.resource_id) {
        setResourceId(String(currentOp.resource_id));
      }
    }
  }, [isOpen, currentOp]);

  // In edit mode: prefill times from the operation's existing schedule.
  // We do NOT auto-suggest a new slot when already scheduled — the operator
  // chose this slot and we should show it rather than immediately replacing it.
  useEffect(() => {
    if (isOpen && isEditMode && currentOp?.scheduled_start) {
      const start = new Date(currentOp.scheduled_start);
      setStartTime(start.toISOString().slice(0, 16));
      if (currentOp.scheduled_end) {
        const end = new Date(currentOp.scheduled_end);
        setEndTime(end.toISOString().slice(0, 16));
      }
    }
  }, [isOpen, isEditMode, currentOp?.id]); // eslint-disable-line react-hooks/exhaustive-deps

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
    return () => { cancelled = true; };
  }, [resourceId, estimatedMinutes, resources]);

  // Fetch operations list to find next pending op after the one just scheduled
  const fetchNextPendingOp = async (justScheduledId) => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations`,
        { credentials: "include" },
      );
      if (!res.ok) return null;
      const data = await res.json();
      const ops = Array.isArray(data) ? data : data.operations || [];
      const sorted = ops.sort((a, b) => a.sequence - b.sequence);
      const justScheduled = sorted.find((op) => op.id === justScheduledId);
      // Find the first pending op with a higher sequence than the one just scheduled
      return sorted.find(
        (op) =>
          op.status === "pending" &&
          (justScheduled ? op.sequence > justScheduled.sequence : true),
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
    setPredecessorConflict(null);
    setSuccessorConflicts([]);
    setShowUnscheduleConfirm(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

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
    setSuccessorConflicts([]);

    // Choose endpoint: reschedule for already-scheduled ops, schedule for new.
    const endpoint = isEditMode ? "reschedule" : "schedule";

    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations/${currentOp.id}/${endpoint}`,
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

      if (!res.ok) {
        throw new Error(data.detail || `Failed to ${isEditMode ? "reschedule" : "schedule"} operation`);
      }

      if (data.success === false) {
        setForceOpen(true);
        if (data.conflict_type === "predecessor") {
          // Predecessor sequence violation — show amber banner with earliest-valid-start
          setPredecessorConflict({
            message: data.message,
            earliestValidStart: data.earliest_valid_start,
          });
          setServerConflicts([]);
          setSuccessorConflicts([]);
        } else if (data.conflict_type === "successor") {
          // Successor violation — show orange banner with per-successor details
          setSuccessorConflicts(data.successor_conflicts || []);
          setServerConflicts([]);
          setPredecessorConflict(null);
        } else {
          // Resource conflict — show red banner with conflicting ops
          setServerConflicts(data.conflicts || []);
          setPredecessorConflict(null);
          setSuccessorConflicts([]);
        }
        if (data.next_available_start) {
          setNextAvailableStart(data.next_available_start);
          setNextAvailableEnd(data.next_available_end);
        }
        setError(data.message || "Scheduling conflict");
        setSubmitting(false);
        return;
      }

      // Report scheduling info back to the parent (wizard uses this for
      // predecessor chaining and the summary screen).
      const scheduledInfo = {
        operationId: currentOp.id,
        operationLabel: `${currentOp.sequence} — ${currentOp.operation_code}`,
        resourceName: selectedResource?.name ?? null,
        startTime: new Date(startTime).toISOString(),
        endTime: new Date(endTime).toISOString(),
      };
      onScheduled?.(scheduledInfo);

      const actionLabel = isEditMode ? "rescheduled" : "scheduled";
      const scheduledCode = `${currentOp.sequence} — ${currentOp.operation_code} (${actionLabel})`;
      // In wizard mode, the wizard handles advancement — just close the modal
      // after signalling the parent via onScheduled.
      if (wizardMode) {
        resetFormState();
        return;
      }
      // In edit mode, don't advance to next op — the operator was editing, not
      // sequentially scheduling. Just show success and close.
      if (isEditMode) {
        setJustScheduled(scheduledCode);
        setNextPendingOp(null);
        resetFormState();
      } else {
        const nextOp = await fetchNextPendingOp(currentOp.id);
        setJustScheduled(scheduledCode);
        setNextPendingOp(nextOp || null);
        resetFormState();
      }
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
    setStartTime(start.toISOString().slice(0, 16));
    if (suggestedEnd) {
      setEndTime(new Date(suggestedEnd).toISOString().slice(0, 16));
    }
    setServerConflicts([]);
    setPredecessorConflict(null);
    setSuccessorConflicts([]);
    setNextAvailableStart(null);
    setNextAvailableEnd(null);
    setError(null);
    setForceOpen(false);
  };

  const handleUnscheduleConfirmed = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations/${currentOp.id}/unschedule`,
        {
          method: "POST",
          credentials: "include",
        },
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to unschedule operation");
      }
      onScheduled?.();
      const unscheduledCode = `${currentOp.sequence} — ${currentOp.operation_code} (unscheduled)`;
      setJustScheduled(unscheduledCode);
      setNextPendingOp(null);
      resetFormState();
    } catch (err) {
      setError(err.message);
      setShowUnscheduleConfirm(false);
    } finally {
      setSubmitting(false);
    }
  };

  // Close with full reset — used by X button, Done button, and advance
  const handleClose = () => {
    setForceOpen(false);
    setCurrentOp(null);
    setJustScheduled(null);
    setNextPendingOp(null);
    resetFormState();
    onClose();
  };

  // Auto-close guard — used by Modal backdrop click and Escape key.
  // Blocks involuntary close when live or server conflicts are shown — the
  // user needs to explicitly resolve or dismiss them, not lose their work
  // by accidentally clicking outside.
  const handleAutoClose = () => {
    if (
      serverConflicts.length > 0 ||
      conflicts.length > 0 ||
      predecessorConflict ||
      successorConflicts.length > 0 ||
      error ||
      compatWarning ||
      showUnscheduleConfirm
    ) {
      return;
    }
    handleClose();
  };

  const effectiveOpen = isOpen || forceOpen;
  if (!effectiveOpen) return null;

  const modalTitle = isEditMode ? "Edit Schedule" : "Schedule Operation";

  return (
    <Modal
      isOpen={effectiveOpen}
      onClose={handleAutoClose}
      title={modalTitle}
      disableClose={submitting}
      className="w-full max-w-lg mx-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b border-gray-800">
        <h2 className="text-xl font-semibold text-white">{modalTitle}</h2>
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

      {/* Wizard step header (SCHED-3b) */}
      {wizardMode && (
        <WizardStepHeader
          step={wizardStep}
          total={wizardTotal}
          onSkipAll={handleClose}
        />
      )}

      {/* Content */}
      <div className="p-6 space-y-6">
        {/* Success banner from previous schedule */}
        {justScheduled && (
          <ScheduleSuccess
            operationCode={justScheduled}
            nextOperation={nextPendingOp}
            onNext={handleAdvanceToNextOp}
          />
        )}

        {/* Wizard maintenance warning (SCHED-3b) */}
        {wizardMode && wizardSuggestion?.maintenanceWarning && (
          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3">
            <div className="flex items-start gap-2">
              <svg className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <p className="text-sm text-amber-400">{wizardSuggestion.maintenanceWarning}</p>
            </div>
          </div>
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
                {estimatedMinutes > 0 ? (
                  <>Estimated Duration: {formatDuration(estimatedMinutes)}</>
                ) : (
                  <span className="italic">
                    Duration unknown — set end time manually
                  </span>
                )}
              </div>
            </div>

            <hr className="border-gray-800" />

            {/* Resource selector */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-gray-400">
                  Resource <span className="text-red-400">*</span>
                </label>
                {/* SCHED-3: Auto-pick slot — PRO-gated, only shown when not in edit mode */}
                {!isEditMode && currentOp?.id && productionOrder?.id && (
                  <AutoPickSlotButton
                    operationId={currentOp.id}
                    productionOrderId={productionOrder.id}
                    disabled={submitting}
                    onSlotPicked={(start, end) => {
                      setStartTime(new Date(start).toISOString().slice(0, 16));
                      setEndTime(new Date(end).toISOString().slice(0, 16));
                      setServerConflicts([]);
                      setPredecessorConflict(null);
                      setSuccessorConflicts([]);
                      setNextAvailableStart(null);
                      setNextAvailableEnd(null);
                      setError(null);
                      setForceOpen(false);
                    }}
                  />
                )}
              </div>
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

            {/* End time (auto-calculated or manual when duration is unknown) */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">
                End Time <span className="text-red-400">*</span>
                <span className="text-gray-600 font-normal ml-2">
                  {estimatedMinutes > 0 ? "(auto-calculated)" : "(enter manually)"}
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

            {/* Predecessor sequence violation banner */}
            {predecessorConflict && (
              <PredecessorAlert
                message={predecessorConflict.message}
                earliestValidStart={predecessorConflict.earliestValidStart}
                nextAvailableStart={nextAvailableStart}
                nextAvailableEnd={nextAvailableEnd}
                onUseSlot={handleUseSuggestedSlot}
              />
            )}

            {/* Successor conflict banner */}
            {successorConflicts.length > 0 && (
              <SuccessorConflictAlert successorConflicts={successorConflicts} />
            )}

            {/* Resource conflict alert (live check or server response) */}
            {!predecessorConflict && successorConflicts.length === 0 && (
              checking ? (
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
              )
            )}

            {/* Error message (only for non-conflict errors) */}
            {error && !predecessorConflict && !serverConflicts.length && successorConflicts.length === 0 && (
              <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}

            {/* Unschedule confirm panel (edit mode only) */}
            {isEditMode && showUnscheduleConfirm && (
              <UnscheduleConfirm
                onConfirm={handleUnscheduleConfirmed}
                onCancel={() => setShowUnscheduleConfirm(false)}
                submitting={submitting}
              />
            )}

            <hr className="border-gray-800" />

            {/* Actions */}
            <div className="flex justify-between gap-3">
              {/* Left: Unschedule button (edit mode only) */}
              <div>
                {isEditMode && !showUnscheduleConfirm && (
                  <button
                    type="button"
                    onClick={() => setShowUnscheduleConfirm(true)}
                    disabled={submitting}
                    className="px-4 py-2 text-amber-400 hover:text-amber-300 transition-colors disabled:opacity-50"
                  >
                    Unschedule
                  </button>
                )}
              </div>

              {/* Right: Done/Skip + Schedule/Reschedule */}
              <div className="flex gap-3">
                {wizardMode && onWizardSkip ? (
                  <button
                    type="button"
                    onClick={onWizardSkip}
                    disabled={submitting}
                    className="px-4 py-2 text-gray-400 hover:text-white transition-colors disabled:opacity-50"
                  >
                    Skip
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleClose}
                    className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
                  >
                    Done
                  </button>
                )}
                {!showUnscheduleConfirm && (
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
                    {submitting
                      ? isEditMode ? "Rescheduling..." : "Scheduling..."
                      : isEditMode ? "Reschedule" : "Schedule"}
                  </button>
                )}
              </div>
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
