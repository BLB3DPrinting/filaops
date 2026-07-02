/**
 * OperationSchedulerModal - Schedule an operation on a resource
 *
 * Allows selecting resource and time slot with conflict detection.
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useResources, useResourceConflicts } from "../../hooks/useResources";
import { formatDuration, toLocalInputValue } from "../../utils/formatting";
import Modal from "../Modal";
import {
  ConflictAlert,
  PredecessorAlert,
  SuccessorConflictAlert,
} from "./scheduler/ConflictPanels";
import {
  CompatibilityWarning,
  ScheduleSuccess,
  UnscheduleConfirm,
  WizardStepHeader,
} from "./scheduler/SchedulerBanners";
import AutoPickSlotButton from "./scheduler/AutoPickSlotButton";
import { useSlotSuggestion } from "./scheduler/useSlotSuggestion";
import { useResourceCompatibility } from "./scheduler/useResourceCompatibility";

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
      setStartTime(toLocalInputValue(wizardSuggestion.startTime));
    }
    if (wizardSuggestion.endTime) {
      setEndTime(toLocalInputValue(wizardSuggestion.endTime));
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
      setEndTime(toLocalInputValue(end));
    }
  }, [startTime, estimatedMinutes]);

  // Set default start time to now (rounded to next 15 min)
  useEffect(() => {
    if (isOpen && !startTime) {
      const now = new Date();
      now.setMinutes(Math.ceil(now.getMinutes() / 15) * 15, 0, 0);
      setStartTime(toLocalInputValue(now));
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
      // scheduled_start/end are naive-UTC server strings — toLocalInputValue
      // routes them through parseDateTime so they land at local wall time.
      // (Plain `new Date(naiveString)` would mis-parse them as local.)
      setStartTime(toLocalInputValue(currentOp.scheduled_start));
      if (currentOp.scheduled_end) {
        setEndTime(toLocalInputValue(currentOp.scheduled_end));
      }
    }
  }, [isOpen, isEditMode, currentOp?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Check compatibility when resource changes (extracted hook — DEBT-1 D2-B)
  useResourceCompatibility({
    resourceId,
    productionOrder,
    resources,
    setCompatWarning,
  });

  // Auto-suggest next available slot when resource is selected — skip in edit
  // mode because the operator can see the current slot and change it
  // deliberately. (extracted hook — DEBT-1 D2-B)
  useSlotSuggestion({
    resourceId,
    estimatedMinutes,
    resources,
    isEditMode,
    setStartTime,
    setEndTime,
  });

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
    setStartTime(toLocalInputValue(now));
  };

  const handleUseSuggestedSlot = (suggestedStart, suggestedEnd) => {
    setStartTime(toLocalInputValue(suggestedStart));
    if (suggestedEnd) {
      setEndTime(toLocalInputValue(suggestedEnd));
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
      variant="workbench"
      className="w-full max-w-lg mx-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b border-[var(--rule-hair)]">
        <h2 className="text-xl font-semibold text-[var(--ink)]">{modalTitle}</h2>
        <button
          onClick={handleClose}
          className="text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors"
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
          <div className="bg-[var(--status-amber-tint)] border border-[var(--status-amber)]/30 rounded-lg p-3">
            <div className="flex items-start gap-2">
              <svg className="w-4 h-4 text-[var(--status-amber)] flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <p className="text-sm text-[var(--status-amber)]">{wizardSuggestion.maintenanceWarning}</p>
            </div>
          </div>
        )}

        {/* Show form if we have an op to schedule (not in "all done" state) */}
        {currentOp && !justScheduled && (
          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Operation info */}
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-[var(--ink)]">
                <span className="font-medium">{currentOp.sequence}:</span>
                <span>{currentOp.operation_code}</span>
                {currentOp.operation_name && (
                  <span className="text-[var(--ink-3)]">
                    ({currentOp.operation_name})
                  </span>
                )}
              </div>
              <div className="text-sm text-[var(--ink-4)]">
                Production Order: {productionOrder?.code}
              </div>
              <div className="text-sm text-[var(--ink-4)]">
                {estimatedMinutes > 0 ? (
                  <>Estimated Duration: {formatDuration(estimatedMinutes)}</>
                ) : (
                  <span className="italic">
                    Duration unknown — set end time manually
                  </span>
                )}
              </div>
            </div>

            <hr className="border-[var(--rule-hair)]" />

            {/* Resource selector */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-sm font-medium text-[var(--ink-3)]">
                  Resource <span className="text-[var(--status-red)]">*</span>
                </label>
                {/* SCHED-3: Auto-pick slot — PRO-gated, only shown when not in edit mode */}
                {!isEditMode && currentOp?.id && productionOrder?.id && (
                  <AutoPickSlotButton
                    operationId={currentOp.id}
                    productionOrderId={productionOrder.id}
                    disabled={submitting}
                    onSlotPicked={(start, end) => {
                      setStartTime(toLocalInputValue(start));
                      setEndTime(toLocalInputValue(end));
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
                className="w-full bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg px-4 py-2.5 text-[var(--ink)] focus:ring-2 focus:ring-[var(--orange)] focus:border-transparent"
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
                <p className="text-xs text-[var(--ink-4)] mt-1">
                  No resources available for this work center
                </p>
              )}
            </div>

            {/* Start time */}
            <div>
              <label className="block text-sm font-medium text-[var(--ink-3)] mb-2">
                Start Time <span className="text-[var(--status-red)]">*</span>
              </label>
              <input
                type="datetime-local"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                className="w-full bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg px-4 py-2.5 text-[var(--ink)] focus:ring-2 focus:ring-[var(--orange)] focus:border-transparent"
              />
            </div>

            {/* End time (auto-calculated or manual when duration is unknown) */}
            <div>
              <label className="block text-sm font-medium text-[var(--ink-3)] mb-2">
                End Time <span className="text-[var(--status-red)]">*</span>
                <span className="text-[var(--ink-4)] font-normal ml-2">
                  {estimatedMinutes > 0 ? "(auto-calculated)" : "(enter manually)"}
                </span>
              </label>
              <input
                type="datetime-local"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                className="w-full bg-[var(--paper)] border border-[var(--rule-hair)] rounded-lg px-4 py-2.5 text-[var(--ink-3)] focus:ring-2 focus:ring-[var(--orange)] focus:border-transparent"
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
                <div className="text-sm text-[var(--ink-4)] flex items-center gap-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-[var(--orange)]"></div>
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
              <div className="bg-[var(--status-red-tint)] border border-[var(--status-red)]/30 rounded-lg p-3">
                <p className="text-[var(--status-red)] text-sm">{error}</p>
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

            <hr className="border-[var(--rule-hair)]" />

            {/* Actions */}
            <div className="flex justify-between gap-3">
              {/* Left: Unschedule button (edit mode only) */}
              <div>
                {isEditMode && !showUnscheduleConfirm && (
                  <button
                    type="button"
                    onClick={() => setShowUnscheduleConfirm(true)}
                    disabled={submitting}
                    className="px-4 py-2 text-[var(--status-amber)] hover:opacity-80 transition-colors disabled:opacity-50"
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
                    className="px-4 py-2 text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors disabled:opacity-50"
                  >
                    Skip
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleClose}
                    className="px-4 py-2 text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors"
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
                    className="px-6 py-2 bg-[var(--orange)] text-white rounded-lg hover:bg-[var(--orange-press)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
              className="px-6 py-2 bg-[var(--orange)] text-white rounded-lg hover:bg-[var(--orange-press)] transition-colors"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </Modal>
  );
}
