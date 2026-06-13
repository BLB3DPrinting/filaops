/**
 * Conflict-display subcomponents for OperationSchedulerModal.
 *
 * Extracted verbatim from OperationSchedulerModal.jsx (DEBT-1 D2-B) — markup,
 * classes, and props are unchanged. These render the resource-conflict,
 * predecessor-conflict, and successor-conflict panels plus the shared
 * next-available slot-suggestion pill.
 */
import { formatTime } from "../../../utils/formatting";

/**
 * Shared slot suggestion pill — used by both conflict alert banners.
 */
export function SlotSuggestion({ label, nextAvailableStart, nextAvailableEnd, onUseSlot }) {
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
export function ConflictAlert({
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
export function PredecessorAlert({
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
 * Successor conflict banner — shown when moving an op would violate a
 * downstream op's existing schedule.
 */
export function SuccessorConflictAlert({ successorConflicts }) {
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
