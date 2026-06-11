/**
 * DispatchChip — "Next up" suggestion chip for idle machine cards.
 *
 * SCHED-3: Renders on idle printers in MachineStatusGrid.
 * Shows order code, product, qty, due date, expandable WHY list, and a
 * maintenance_warning badge when present.
 *
 * Actions:
 *   [Confirm]         — POST /dispatch/assign, optimistic refresh + toast
 *   [Pick different…] — opens OperationSchedulerModal prefilled for the op
 *
 * Auto-dispatch guard (hard rule):
 *   When autoDispatch=true, the parent calls confirmSuggestion() automatically
 *   for suggestions WITHOUT a maintenance_warning.  Suggestions WITH a
 *   maintenance_warning are NEVER auto-confirmed regardless of the setting.
 *   This component renders the warning badge and exposes the guard logic via
 *   the `canAutoDispatch` exported helper.
 *
 * Props:
 *   suggestion     — DispatchSuggestion object from GET /dispatch/suggestions
 *   printerId      — Printer.id (used for POST /dispatch/assign payload)
 *   onConfirmed    — () => void — called after a successful assign
 *   onPickDifferent — (operation, productionOrder) => void — open scheduler modal
 */
import { useState } from "react";
import { API_URL } from "../../config/api";

/**
 * Returns true when this suggestion may be auto-confirmed.
 * HARD RULE: any maintenance_warning blocks auto-dispatch.
 */
export function canAutoDispatch(suggestion) {
  return suggestion != null && !suggestion.maintenance_warning;
}

/**
 * Call POST /dispatch/assign for the given suggestion + printer.
 * Returns { ok: true } on success or { ok: false, message } on error.
 */
export async function confirmDispatch(suggestion, printerId) {
  try {
    const res = await fetch(`${API_URL}/api/v1/dispatch/assign`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        operation_id: suggestion.operation_id,
        printer_id: printerId,
      }),
    });
    if (!res.ok) {
      let message = "Dispatch failed";
      try {
        const errData = await res.json();
        message = errData.detail || message;
      } catch {
        // non-JSON error body (proxy/HTML error page) — keep generic message
      }
      return { ok: false, message };
    }
    const data = await res.json();
    return { ok: true, data };
  } catch (err) {
    return { ok: false, message: err.message || "Network error" };
  }
}

/**
 * Expandable WHY list pill
 */
function WhyList({ why }) {
  const [expanded, setExpanded] = useState(false);
  if (!why || why.length === 0) return null;

  return (
    <div className="mt-1.5">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setExpanded((v) => !v);
        }}
        className="text-xs text-blue-400/80 hover:text-blue-300 underline-offset-2 underline"
        aria-expanded={expanded}
      >
        {expanded ? "Hide reasons" : "Why?"}
      </button>
      {expanded && (
        <ul className="mt-1 pl-2 space-y-0.5">
          {why.map((reason, i) => (
            <li key={i} className="text-xs text-gray-400">
              · {reason}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Main DispatchChip component
 */
export default function DispatchChip({
  suggestion,
  printerId,
  onConfirmed,
  onPickDifferent,
}) {
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(null);

  if (!suggestion) return null;

  const hasWarning = Boolean(suggestion.maintenance_warning);

  const handleConfirm = async (e) => {
    e.stopPropagation();
    setConfirming(true);
    setError(null);
    const result = await confirmDispatch(suggestion, printerId);
    setConfirming(false);
    if (result.ok) {
      onConfirmed?.();
    } else {
      setError(result.message);
    }
  };

  const handlePickDifferent = (e) => {
    e.stopPropagation();
    // Build minimal operation + productionOrder objects for the scheduler modal
    const operation = {
      id: suggestion.operation_id,
      operation_code: suggestion.operation_code,
      operation_name: suggestion.operation_name,
      status: "pending",
      sequence: 1,
      planned_setup_minutes: "0",
      planned_run_minutes: String(suggestion.estimated_duration_minutes),
    };
    const productionOrder = {
      id: suggestion.production_order_id,
      code: suggestion.production_order_code,
    };
    onPickDifferent?.(operation, productionOrder);
  };

  return (
    <div
      className={`mt-2 pt-2 border-t ${
        hasWarning ? "border-amber-600/40" : "border-gray-700"
      }`}
      data-testid="dispatch-chip"
    >
      {/* "Next up" label */}
      <div className="text-[10px] font-semibold uppercase tracking-widest text-blue-400/80 mb-1">
        Next up
      </div>

      {/* Order + product info */}
      <div className="text-xs font-medium text-white truncate">
        {suggestion.production_order_code}
      </div>
      <div className="text-xs text-gray-400 truncate">{suggestion.product_name}</div>

      {/* Meta row: qty + due date */}
      <div className="flex items-center gap-2 mt-1 flex-wrap">
        <span className="text-xs text-gray-500">Qty {suggestion.quantity}</span>
        {suggestion.due_date && (
          <span className="text-xs text-gray-500">
            Due{" "}
            <span
              className={
                new Date(suggestion.due_date) < new Date()
                  ? "text-red-400"
                  : "text-gray-400"
              }
            >
              {suggestion.due_date}
            </span>
          </span>
        )}
      </div>

      {/* WHY expandable */}
      <WhyList why={suggestion.why} />

      {/* Maintenance warning badge */}
      {hasWarning && (
        <div
          className="mt-2 flex items-start gap-1.5 bg-amber-500/10 border border-amber-500/30 rounded px-2 py-1.5"
          data-testid="maintenance-warning-badge"
        >
          <svg
            className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5"
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
          <span className="text-[11px] text-amber-300 leading-tight">
            {suggestion.maintenance_warning}
          </span>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-1.5 text-xs text-red-400 bg-red-500/10 rounded px-2 py-1">
          {error}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-1.5 mt-2">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={confirming}
          className="px-2.5 py-1 bg-blue-600 text-white text-xs font-medium rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          data-testid="confirm-btn"
        >
          {confirming ? "Confirming…" : "Confirm"}
        </button>
        <button
          type="button"
          onClick={handlePickDifferent}
          disabled={confirming}
          className="px-2.5 py-1 border border-gray-700 text-gray-400 text-xs rounded hover:border-gray-500 hover:text-white disabled:opacity-50 transition-colors"
          data-testid="pick-different-btn"
        >
          Pick different…
        </button>
      </div>
    </div>
  );
}
