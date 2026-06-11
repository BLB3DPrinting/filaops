/**
 * OperationRow - Single operation in the operations list
 *
 * Shows operation sequence, name, status, timing, and assignment.
 * Handles visual states for pending, running, complete, skipped.
 */
import { useState, useEffect } from 'react';
import { formatDuration, formatTime } from '../../utils/formatting';
import OperationActions from './OperationActions';

/**
 * Status indicator with icon and color
 */
function StatusIndicator({ status }) {
  const configs = {
    pending: {
      color: 'text-gray-400',
      bgColor: 'bg-gray-500/20',
      icon: '○',
      label: 'Pending'
    },
    queued: {
      color: 'text-blue-400',
      bgColor: 'bg-blue-500/20',
      icon: '◐',
      label: 'Queued'
    },
    running: {
      color: 'text-purple-400',
      bgColor: 'bg-purple-500/20',
      icon: '●',
      label: 'Running',
      pulse: true
    },
    complete: {
      color: 'text-green-400',
      bgColor: 'bg-green-500/20',
      icon: '●',
      label: 'Complete'
    },
    skipped: {
      color: 'text-yellow-400',
      bgColor: 'bg-yellow-500/20',
      icon: '⊘',
      label: 'Skipped'
    }
  };

  const config = configs[status] || configs.pending;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${config.bgColor} ${config.color}`}
    >
      <span className={config.pulse ? 'animate-pulse' : ''}>{config.icon}</span>
      {config.label}
    </span>
  );
}

/**
 * Parse datetime string, ensuring UTC interpretation
 */
function parseDateTime(datetime) {
  if (!datetime) return null;
  if (datetime instanceof Date) return datetime;

  // If string doesn't have timezone info, assume UTC and add 'Z'
  let dateStr = datetime;
  if (typeof dateStr === 'string' && !dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z';
  }
  return new Date(dateStr);
}

/**
 * Calculate elapsed minutes from a start time
 */
function calculateElapsedMinutes(startTime) {
  if (!startTime) return 0;
  const start = parseDateTime(startTime);
  const now = new Date();
  return Math.floor((now.getTime() - start.getTime()) / 60000);
}

/**
 * Format elapsed or estimated time
 */
function TimingDisplay({ operation }) {
  // Track time for running operations with periodic updates
  const [tick, setTick] = useState(0);

  // Update every minute for running operations
  useEffect(() => {
    if (operation.status !== 'running' || !operation.actual_start) {
      return;
    }

    const interval = setInterval(() => {
      setTick(t => t + 1);
    }, 60000);

    return () => clearInterval(interval);
  }, [operation.status, operation.actual_start]);

  // Calculate elapsed minutes (recalculated when tick changes)
  const elapsedMinutes = operation.status === 'running' && operation.actual_start
    ? calculateElapsedMinutes(operation.actual_start)
    : 0;

  // Suppress unused variable warning - tick triggers re-render
  void tick;

  if (operation.status === 'complete') {
    // Show actual time
    const actualMinutes = (operation.actual_setup_minutes || 0) + (operation.actual_run_minutes || 0);
    return (
      <span className="text-green-400 text-sm">
        {formatDuration(actualMinutes)}
      </span>
    );
  }

  if (operation.status === 'running') {
    // Show elapsed time (calculate from actual_start)
    if (operation.actual_start) {
      return (
        <span className="text-purple-400 text-sm font-mono">
          {formatDuration(elapsedMinutes)}
        </span>
      );
    }
    return <span className="text-purple-400 text-sm">Starting...</span>;
  }

  if (operation.status === 'skipped') {
    return <span className="text-yellow-400 text-sm">—</span>;
  }

  // Pending - show estimate (API returns Numeric columns as strings; use parseFloat)
  const toMin = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
  const planned = toMin(operation.planned_setup_minutes) + toMin(operation.planned_run_minutes);
  if (planned > 0) {
    return (
      <span className="text-gray-500 text-sm">
        Est: {formatDuration(planned)}
      </span>
    );
  }

  return <span className="text-gray-600 text-sm">—</span>;
}

/**
 * Main OperationRow component
 */
export default function OperationRow({
  operation,
  isActive,
  productionOrderId,
  onActionSuccess,
  onActionError,
  onSkipClick,
  onScrapClick,
  onCompleteClick,
  onClick
}) {
  const isClickable = onClick && ['pending', 'running'].includes(operation.status);

  return (
    <div
      className={`
        group p-3 rounded-lg border transition-all
        ${isActive ? 'border-purple-500/50 bg-purple-500/5' : 'border-gray-800 bg-gray-900/50'}
        ${isClickable ? 'cursor-pointer hover:border-gray-700 hover:bg-gray-800/50' : ''}
        ${operation.status === 'complete' ? 'opacity-75' : ''}
        ${operation.status === 'skipped' ? 'opacity-50' : ''}
      `}
      onClick={isClickable ? () => onClick(operation) : undefined}
    >
      <div className="flex items-center justify-between">
        {/* Left: Sequence, Code, Name */}
        <div className="flex items-center gap-3">
          {/* Sequence number */}
          <span className="w-8 h-8 flex items-center justify-center rounded-full bg-gray-800 text-gray-400 text-sm font-mono">
            {operation.sequence}
          </span>

          {/* Operation info */}
          <div>
            <div className="flex items-center gap-2">
              <span className="text-white font-medium">
                {operation.operation_code || `Op ${operation.sequence}`}
              </span>
              {operation.operation_name && (
                <>
                  <span className="text-gray-600">—</span>
                  <span className="text-gray-400">{operation.operation_name}</span>
                </>
              )}
            </div>

            {/* Work center / resource */}
            <div className="text-xs text-gray-500 mt-0.5">
              {operation.work_center_name || operation.work_center_code || 'Unassigned'}
              {operation.resource_name && (
                <span className="text-gray-600"> → {operation.resource_name}</span>
              )}
            </div>
          </div>
        </div>

        {/* Right: Status and Timing */}
        <div className="flex items-center gap-4">
          <TimingDisplay operation={operation} />
          <StatusIndicator status={operation.status} />
        </div>
      </div>

      {/* Expanded details for running operation */}
      {operation.status === 'running' && (
        <div className="mt-3 pt-3 border-t border-gray-800 flex items-center justify-between">
          <div className="text-xs text-gray-500">
            Started: {operation.actual_start ? formatTime(operation.actual_start) : 'Just now'}
          </div>
          <div className="text-xs text-purple-400">
            ● In Progress
          </div>
        </div>
      )}

      {/* Materials required for this operation */}
      {operation.materials && operation.materials.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <div className="text-xs text-gray-500 mb-2">Materials:</div>
          <div className="space-y-1">
            {operation.materials.map((mat) => (
              <div key={mat.id} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">{mat.component_sku || mat.component_name}</span>
                  {mat.component_name && mat.component_sku && (
                    <span className="text-gray-600">- {mat.component_name}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <span className={mat.status === 'consumed' ? 'text-green-400' : 'text-gray-400'}>
                    {mat.status === 'consumed'
                      ? `${Number(mat.quantity_consumed).toFixed(2)} ${mat.unit}`
                      : `${Number(mat.quantity_required).toFixed(2)} ${mat.unit}`}
                  </span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                    mat.status === 'consumed' ? 'bg-green-500/20 text-green-400' :
                    mat.status === 'allocated' ? 'bg-blue-500/20 text-blue-400' :
                    'bg-gray-700 text-gray-400'
                  }`}>
                    {mat.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Show skip reason if skipped */}
      {operation.status === 'skipped' && operation.notes && (
        <div className="mt-2 text-xs text-yellow-400/70 italic">
          Skipped: {operation.notes}
        </div>
      )}

      {/* Action buttons */}
      {productionOrderId && (
        <OperationActions
          operation={operation}
          productionOrderId={productionOrderId}
          onSuccess={onActionSuccess}
          onError={onActionError}
          onSkipClick={onSkipClick}
          onScrapClick={onScrapClick}
          onCompleteClick={onCompleteClick}
        />
      )}
    </div>
  );
}
