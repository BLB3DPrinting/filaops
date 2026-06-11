/**
 * OperationsTimeline - Visual timeline of operation progress
 *
 * Shows operations as connected nodes with status indicators.
 * Provides quick visual reference for production progress.
 */
import { formatDuration } from '../../utils/formatting';

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
 * Status configuration for visual styling
 */
const STATUS_CONFIG = {
  pending: {
    nodeClass: 'border-2 border-gray-600 bg-gray-900',
    labelClass: 'text-gray-500',
    icon: null
  },
  queued: {
    nodeClass: 'border-2 border-blue-500 bg-gray-900',
    labelClass: 'text-blue-400',
    icon: null
  },
  running: {
    nodeClass: 'border-2 border-purple-500 bg-purple-500/20 animate-pulse',
    labelClass: 'text-purple-400',
    icon: (
      <div className="w-2 h-2 rounded-full bg-purple-400 animate-ping" />
    )
  },
  complete: {
    nodeClass: 'border-2 border-green-500 bg-green-500',
    labelClass: 'text-green-400',
    icon: (
      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
      </svg>
    )
  },
  skipped: {
    nodeClass: 'border-2 border-yellow-500 bg-yellow-500/20',
    labelClass: 'text-yellow-400 line-through',
    icon: (
      <svg className="w-3 h-3 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    )
  }
};

/**
 * Single timeline node
 */
function TimelineNode({ operation }) {
  const config = STATUS_CONFIG[operation.status] || STATUS_CONFIG.pending;

  // Calculate timing display
  let timingText = '';
  if (operation.status === 'complete') {
    const actual = (operation.actual_setup_minutes || 0) + (operation.actual_run_minutes || 0);
    timingText = formatDuration(actual);
  } else if (operation.status === 'running') {
    if (operation.actual_start) {
      // eslint-disable-next-line react-hooks/purity -- Date.now() is intentional for live elapsed time
      const elapsed = Math.floor((Date.now() - parseDateTime(operation.actual_start).getTime()) / 60000);
      timingText = formatDuration(elapsed);
    } else {
      timingText = 'Starting...';
    }
  } else if (operation.status === 'skipped') {
    timingText = 'Skipped';
  } else {
    // API returns Numeric columns as strings; use parseFloat to avoid string concatenation
    const toMin = (v) => { const n = parseFloat(v); return Number.isFinite(n) ? n : 0; };
    const planned = toMin(operation.planned_setup_minutes) + toMin(operation.planned_run_minutes);
    if (planned > 0) {
      timingText = `~${formatDuration(planned)}`;
    }
  }

  return (
    <div className="flex flex-col items-center flex-1 min-w-0">
      {/* Node */}
      <div
        className={`
          w-6 h-6 rounded-full flex items-center justify-center
          ${config.nodeClass}
          transition-all duration-300
        `}
      >
        {config.icon}
      </div>

      {/* Label */}
      <div className="mt-2 text-center">
        <div className={`text-xs font-medium truncate max-w-[80px] ${config.labelClass}`}>
          {operation.operation_code || `Op ${operation.sequence}`}
        </div>
        <div className={`text-[10px] ${config.labelClass} opacity-70`}>
          {timingText}
        </div>
      </div>
    </div>
  );
}

/**
 * Connector line between nodes
 */
function TimelineConnector({ prevStatus }) {
  // Use the "more complete" status for coloring
  const getConnectorClass = () => {
    if (prevStatus === 'complete' || prevStatus === 'skipped') {
      return 'bg-green-500';
    }
    if (prevStatus === 'running') {
      return 'bg-gradient-to-r from-purple-500 to-gray-700';
    }
    return 'bg-gray-700';
  };

  return (
    <div className="flex-1 h-0.5 mt-3 mx-1">
      <div className={`h-full ${getConnectorClass()} transition-all duration-300`} />
    </div>
  );
}

/**
 * Progress percentage display
 */
function ProgressSummary({ operations }) {
  if (!operations || operations.length === 0) return null;

  const completed = operations.filter(op =>
    ['complete', 'skipped'].includes(op.status)
  ).length;
  const percentage = Math.round((completed / operations.length) * 100);

  return (
    <div className="flex items-center justify-between mb-4">
      <span className="text-sm text-gray-400">Operations Progress</span>
      <span className="text-sm font-medium text-white">{percentage}%</span>
    </div>
  );
}

/**
 * Progress bar underneath timeline
 */
function ProgressBar({ operations }) {
  if (!operations || operations.length === 0) return null;

  const completed = operations.filter(op => op.status === 'complete').length;
  const running = operations.filter(op => op.status === 'running').length;
  const skipped = operations.filter(op => op.status === 'skipped').length;
  const total = operations.length;

  const completedPct = (completed / total) * 100;
  const runningPct = (running / total) * 100;
  const skippedPct = (skipped / total) * 100;

  return (
    <div className="mt-4">
      <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden flex">
        {/* Completed */}
        <div
          className="bg-green-500 transition-all duration-500"
          style={{ width: `${completedPct}%` }}
        />
        {/* Running */}
        <div
          className="bg-purple-500 animate-pulse transition-all duration-500"
          style={{ width: `${runningPct}%` }}
        />
        {/* Skipped */}
        <div
          className="bg-yellow-500/50 transition-all duration-500"
          style={{ width: `${skippedPct}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Main component
 */
export default function OperationsTimeline({ operations }) {
  if (!operations || operations.length === 0) {
    return null;
  }

  // Sort by sequence
  const sortedOps = [...operations].sort((a, b) => a.sequence - b.sequence);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <ProgressSummary operations={sortedOps} />

      {/* Timeline */}
      <div className="flex items-start">
        {sortedOps.map((operation, index) => (
          <div key={operation.id} className="flex items-start flex-1 min-w-0">
            <TimelineNode operation={operation} />
            {index < sortedOps.length - 1 && (
              <TimelineConnector prevStatus={operation.status} />
            )}
          </div>
        ))}
      </div>

      <ProgressBar operations={sortedOps} />
    </div>
  );
}
