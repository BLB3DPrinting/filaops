/**
 * OperationsProgressBar - Compact progress indicator
 *
 * Shows operation progress in a single horizontal bar.
 * Use when space is limited (e.g., in list views).
 */

export default function OperationsProgressBar({ operations, showLabels = true }) {
  if (!operations || operations.length === 0) {
    return (
      <div className="text-xs text-[var(--ink-4)]">No operations</div>
    );
  }

  const sortedOps = [...operations].sort((a, b) => a.sequence - b.sequence);

  const completed = sortedOps.filter(op => op.status === 'complete').length;
  const running = sortedOps.filter(op => op.status === 'running').length;
  const skipped = sortedOps.filter(op => op.status === 'skipped').length;
  const total = sortedOps.length;

  const completedPct = (completed / total) * 100;
  const runningPct = (running / total) * 100;
  const skippedPct = (skipped / total) * 100;

  // Find current operation (first running or first pending)
  const currentOp = sortedOps.find(op => op.status === 'running')
    || sortedOps.find(op => op.status === 'pending' || op.status === 'queued');

  return (
    <div className="space-y-1.5">
      {/* Progress bar */}
      <div className="h-2 bg-[var(--rule-hair)] rounded-full overflow-hidden flex">
        <div
          className="bg-[var(--status-green)] transition-all duration-500"
          style={{ width: `${completedPct}%` }}
        />
        <div
          className="bg-[var(--status-amber)] animate-pulse transition-all duration-500"
          style={{ width: `${runningPct}%` }}
        />
        <div
          className="bg-[var(--status-amber)]/50 transition-all duration-500"
          style={{ width: `${skippedPct}%` }}
        />
      </div>

      {/* Labels */}
      {showLabels && (
        <div className="flex justify-between text-xs">
          <span className="text-[var(--ink-4)]">
            {completed + skipped}/{total} ops
          </span>
          {currentOp && (
            <span className={currentOp.status === 'running' ? 'text-[var(--status-amber)]' : 'text-[var(--ink-4)]'}>
              {currentOp.status === 'running' ? '\u25CF ' : ''}
              {currentOp.operation_code || `Op ${currentOp.sequence}`}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
