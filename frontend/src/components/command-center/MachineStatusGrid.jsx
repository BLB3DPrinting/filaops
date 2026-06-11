/**
 * MachineStatusGrid - Display all resources/machines with current status
 *
 * Shows a responsive grid of machine cards with live timers for running operations.
 *
 * SCHED-3: Idle printers render a DispatchChip when a dispatch suggestion is
 * available.  The parent (AdminCommandCenter) passes a suggestions map keyed
 * by printer.id.
 *
 * Props:
 *   resources        — ResourceStatus[] from GET /command-center/resources
 *   suggestions      — Map<printerId, PrinterDispatchResult> (optional)
 *   onMachineClick   — (resource) => void
 *   onDispatchConfirmed — () => void — refresh signal after confirm
 *   onPickDifferent  — (operation, productionOrder) => void — open scheduler
 */
import { Link } from "react-router-dom";
import ElapsedTimer from "../production/ElapsedTimer";
import DispatchChip from "./DispatchChip";

/**
 * Status configurations
 */
const statusConfig = {
  running: {
    dot: "bg-emerald-500",
    label: "Running",
    labelColor: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
  },
  idle: {
    dot: "bg-yellow-500",
    label: "Idle",
    labelColor: "text-yellow-400",
    bg: "bg-gray-800",
    border: "border-gray-700",
  },
  maintenance: {
    dot: "bg-orange-500",
    label: "Maintenance",
    labelColor: "text-orange-400",
    bg: "bg-orange-500/10",
    border: "border-orange-500/30",
  },
  offline: {
    dot: "bg-red-500",
    label: "Offline",
    labelColor: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/30",
  },
  available: {
    dot: "bg-gray-500",
    label: "Available",
    labelColor: "text-gray-400",
    bg: "bg-gray-800",
    border: "border-gray-700",
  },
};

/**
 * Single machine card
 *
 * SCHED-3: When idle, shows a DispatchChip if a suggestion is available for
 * this resource's associated printer (matched by printer_id on the resource).
 * SCHED-4: Shows a maintenance due-soon badge when resource.maintenance_due_soon.
 */
function MachineCard({
  resource,
  onClick,
  suggestion,
  onDispatchConfirmed,
  onPickDifferent,
}) {
  const config = statusConfig[resource.status] || statusConfig.available;
  const isRunning = resource.status === "running" && resource.current_operation;
  const isIdle = resource.status === "idle";
  const maintenanceDueSoon = Boolean(resource.maintenance_due_soon);

  return (
    <div
      className={`
        ${config.bg} ${config.border} border rounded-lg p-3
        hover:border-gray-500 cursor-pointer transition-colors
      `}
      onClick={() => onClick?.(resource)}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="font-medium text-white truncate">{resource.code}</span>
          {/* SCHED-4: maintenance due-soon badge */}
          {maintenanceDueSoon && (
            <span
              title="Maintenance due within 7 days"
              className="shrink-0 flex items-center gap-0.5 text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30 rounded px-1 py-0.5"
              data-testid="maintenance-due-badge"
            >
              <svg className="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Maint
            </span>
          )}
        </div>
        <span
          className={`flex items-center gap-1.5 text-xs ${config.labelColor}`}
        >
          <span
            className={`w-2 h-2 rounded-full ${config.dot} ${isRunning ? "animate-pulse" : ""}`}
          />
          {config.label}
        </span>
      </div>

      {/* Resource name */}
      <div className="text-xs text-gray-500 mt-1 truncate">{resource.name}</div>

      {/* Running operation details */}
      {isRunning && (
        <div className="mt-2 pt-2 border-t border-gray-700">
          <div className="text-xs text-gray-400 truncate">
            {resource.current_operation.production_order_code}
          </div>
          <div className="flex items-center justify-between mt-1">
            <span className="text-xs text-gray-500">
              Op {resource.current_operation.sequence}
            </span>
            <ElapsedTimer
              startTime={resource.current_operation.started_at}
              className="text-xs text-emerald-400"
            />
          </div>
        </div>
      )}

      {/* SCHED-3: Idle with dispatch suggestion */}
      {isIdle && suggestion?.top_suggestion ? (
        <DispatchChip
          suggestion={suggestion.top_suggestion}
          printerId={suggestion.printer.id}
          onConfirmed={onDispatchConfirmed}
          onPickDifferent={onPickDifferent}
        />
      ) : isIdle && resource.pending_operations_count > 0 ? (
        /* Fallback: idle with pending work but no suggestion yet */
        <div className="mt-2 pt-2 border-t border-gray-700">
          <div className="text-xs text-yellow-400">
            {resource.pending_operations_count} ops waiting
          </div>
        </div>
      ) : null}

      {/* Maintenance/offline message */}
      {(resource.status === "maintenance" || resource.status === "offline") && (
        <div className="mt-2 pt-2 border-t border-gray-700">
          <div className="text-xs text-gray-500">
            {resource.status === "maintenance"
              ? "Under maintenance"
              : "Offline"}
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Main grid component
 */
export default function MachineStatusGrid({
  resources = [],
  suggestions = {},
  onMachineClick,
  onDispatchConfirmed,
  onPickDifferent,
}) {
  if (resources.length === 0) {
    return (
      <div className="bg-gray-800 rounded-lg p-8 text-center">
        <svg
          className="w-12 h-12 text-gray-600 mx-auto mb-3"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
          />
        </svg>
        <p className="text-gray-400">No resources configured</p>
        <Link
          to="/admin/manufacturing"
          className="text-blue-400 hover:text-blue-300 text-sm mt-2 inline-block"
        >
          Configure Resources
        </Link>
      </div>
    );
  }

  // Group by work center
  const byWorkCenter = resources.reduce((acc, resource) => {
    const wcName = resource.work_center_name || "Unassigned";
    if (!acc[wcName]) {
      acc[wcName] = [];
    }
    acc[wcName].push(resource);
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {Object.entries(byWorkCenter).map(([wcName, wcResources]) => (
        <div key={wcName}>
          <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">
            {wcName}
          </h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
            {wcResources.map((resource) => (
              <MachineCard
                key={resource.id}
                resource={resource}
                onClick={onMachineClick}
                suggestion={suggestions[resource.printer_id] ?? null}
                onDispatchConfirmed={onDispatchConfirmed}
                onPickDifferent={onPickDifferent}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
