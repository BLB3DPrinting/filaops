/**
 * Auxiliary banner / inline-panel subcomponents for OperationSchedulerModal.
 *
 * Extracted verbatim from OperationSchedulerModal.jsx (DEBT-1 D2-B) — markup,
 * classes, and props are unchanged. Covers the compatibility warning, the
 * post-schedule success banner, the unschedule confirmation panel, and the
 * wizard step header.
 */

/**
 * Compatibility warning banner
 */
export function CompatibilityWarning({ reason }) {
  if (!reason) return null;

  return (
    <div className="bg-[var(--status-amber-tint)] border border-[var(--status-amber)]/30 rounded-lg p-3">
      <div className="flex items-start gap-2">
        <svg
          className="w-5 h-5 text-[var(--status-amber)] flex-shrink-0 mt-0.5"
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
          <h4 className="text-[var(--status-amber)] font-medium text-sm">
            Incompatible Resource
          </h4>
          <p className="text-sm text-[var(--status-amber)]/70 mt-1">{reason}</p>
        </div>
      </div>
    </div>
  );
}

/**
 * Success banner shown after scheduling, with option to advance to next op
 */
export function ScheduleSuccess({ operationCode, nextOperation, onNext }) {
  return (
    <div className="bg-[var(--status-green-tint)] border border-[var(--status-green)]/30 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <svg
          className="w-5 h-5 text-[var(--status-green)] flex-shrink-0 mt-0.5"
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
          <h4 className="text-[var(--status-green)] font-medium">
            {operationCode} scheduled
          </h4>
          {nextOperation ? (
            <div className="mt-2 flex items-center gap-3">
              <p className="text-sm text-[var(--ink-3)]">
                Next: {nextOperation.sequence} — {nextOperation.operation_code}
              </p>
              <button
                type="button"
                onClick={onNext}
                className="text-sm text-[var(--ink-2)] hover:text-[var(--ink)] underline"
              >
                Schedule it now
              </button>
            </div>
          ) : (
            <p className="text-sm text-[var(--ink-3)] mt-1">
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
export function UnscheduleConfirm({ onConfirm, onCancel, submitting }) {
  return (
    <div className="bg-[var(--status-amber-tint)] border border-[var(--status-amber)]/30 rounded-lg p-4">
      <p className="text-[var(--status-amber)] font-medium text-sm">
        Unschedule this operation?
      </p>
      <p className="text-[var(--status-amber)]/70 text-sm mt-1">
        The operation will return to pending and its time slot will be freed.
      </p>
      <div className="flex gap-3 mt-3">
        <button
          type="button"
          onClick={onConfirm}
          disabled={submitting}
          className="px-4 py-1.5 bg-[var(--orange)] text-white text-sm rounded-lg hover:bg-[var(--orange-press)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {submitting ? "Unscheduling..." : "Confirm Unschedule"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-1.5 text-[var(--ink-3)] hover:text-[var(--ink)] text-sm transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

/**
 * Wizard step header — shown when wizardMode is true.
 */
export function WizardStepHeader({ step, total, onSkipAll }) {
  return (
    <div className="flex items-center justify-between px-6 py-3 bg-[var(--paper-sunk)] border-b border-[var(--rule-hair)]">
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium text-[var(--ink-2)] uppercase tracking-wide">
          Schedule Wizard
        </span>
        <span className="text-xs text-[var(--ink-4)]">
          Step {step} of {total}
        </span>
        {/* Progress dots */}
        <div className="flex gap-1">
          {Array.from({ length: total }, (_, i) => (
            <span
              key={i}
              className={`w-1.5 h-1.5 rounded-full ${
                i < step ? "bg-[var(--ink)]" : "bg-[var(--rule-hair)]"
              }`}
            />
          ))}
        </div>
      </div>
      <button
        type="button"
        onClick={onSkipAll}
        className="text-xs text-[var(--ink-4)] hover:text-[var(--ink-2)] transition-colors"
      >
        Skip all / later
      </button>
    </div>
  );
}
