/**
 * FulfillmentProgress - Shows line-by-line fulfillment status on SO detail page.
 * UI-302 - Week 4 UI Refactor
 */

// Status badge styles per fulfillment state
const STATUS_STYLES = {
  ready_to_ship: 'bg-green-500/20 text-green-400 border-green-500/30',
  partially_ready: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  blocked: 'bg-red-500/20 text-red-400 border-red-500/30',
  short_closed: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  shipped: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  cancelled: 'bg-gray-500/20 text-gray-500 border-gray-500/30',
};

// Human-readable labels for fulfillment states
const STATUS_LABELS = {
  ready_to_ship: 'Ready to Ship',
  partially_ready: 'Partially Ready',
  blocked: 'Blocked',
  short_closed: 'Closed Short — Ready to Ship',
  shipped: 'Shipped',
  cancelled: 'Cancelled',
};

/**
 * Get progress bar color based on fulfillment percentage
 */
function getProgressColor(percent) {
  if (percent === 100) return 'bg-green-500';
  if (percent >= 50) return 'bg-yellow-500';
  if (percent > 0) return 'bg-orange-500';
  return 'bg-red-500';
}

/**
 * Check circle icon (inline SVG)
 */
function CheckCircleIcon({ className }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <path
        fillRule="evenodd"
        d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zm13.36-1.814a.75.75 0 10-1.22-.872l-3.236 4.53L9.53 12.22a.75.75 0 00-1.06 1.06l2.25 2.25a.75.75 0 001.14-.094l3.75-5.25z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/**
 * X circle icon (inline SVG)
 */
function XCircleIcon({ className }) {
  return (
    <svg className={className} fill="currentColor" viewBox="0 0 24 24">
      <path
        fillRule="evenodd"
        d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25zm-1.72 6.97a.75.75 0 10-1.06 1.06L10.94 12l-1.72 1.72a.75.75 0 101.06 1.06L12 13.06l1.72 1.72a.75.75 0 101.06-1.06L13.06 12l1.72-1.72a.75.75 0 10-1.06-1.06L12 10.94l-1.72-1.72z"
        clipRule="evenodd"
      />
    </svg>
  );
}

/**
 * FulfillmentProgress component
 *
 * @param {Object} props
 * @param {Object|null} props.fulfillmentStatus - Fulfillment status data from useFulfillmentStatus hook
 * @param {boolean} props.loading - Loading state
 * @param {string|null} props.error - Error message if any
 * @param {Function} props.onRefresh - Callback to refresh data
 * @param {Function} [props.onShip] - Optional callback when Ship button clicked
 * @param {boolean} [props.closedShort] - When true, non-terminal states render as "Closed Short —
 *   Ready to Ship" (amber) and short lines show "Short Closed" instead of "Short X"
 */
export default function FulfillmentProgress({
  fulfillmentStatus,
  loading,
  error,
  onRefresh,
  onShip,
  closedShort = false,
}) {
  // Loading state
  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-4">
        <div className="animate-pulse space-y-4">
          <div className="h-6 bg-gray-800 rounded w-1/3"></div>
          <div className="h-4 bg-gray-800 rounded w-2/3"></div>
          <div className="h-20 bg-gray-800 rounded"></div>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="bg-gray-900 border border-red-500/30 rounded-xl p-4 mb-4">
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-red-400 font-medium">Failed to load fulfillment status</p>
            <p className="text-sm text-gray-500">{error}</p>
          </div>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="ml-auto px-3 py-1 text-sm bg-gray-800 text-gray-300 rounded hover:bg-gray-700"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  // No data state
  if (!fulfillmentStatus) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center text-gray-500 mb-4">
        No fulfillment status data available
      </div>
    );
  }

  const { summary, lines } = fulfillmentStatus;
  const rawState = summary?.state || 'blocked';
  // When an order is closed short, it is intentionally partial — show short_closed for any
  // non-terminal state (blocked, partially_ready, ready_to_ship). Terminal states (shipped,
  // cancelled) keep their own label since closed_short is just historical context at that point.
  const TERMINAL_STATES = new Set(['shipped', 'cancelled']);
  const state = closedShort && !TERMINAL_STATES.has(rawState) ? 'short_closed' : rawState;
  const percent = summary?.fulfillment_percent ?? 0;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl mb-4">
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-white">Fulfillment Progress</h3>
            <span className={`px-2 py-1 rounded-full text-xs font-medium border ${STATUS_STYLES[state] || STATUS_STYLES.blocked}`}>
              {STATUS_LABELS[state] || state}
            </span>
          </div>
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="p-2 text-gray-500 hover:text-white rounded-lg hover:bg-gray-800"
              title="Refresh"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Progress Bar */}
        <div>
          <div className="flex justify-between text-sm text-gray-400 mb-2">
            <span>{summary?.lines_ready || 0}/{summary?.lines_total || 0} lines ready</span>
            <span>{percent}%</span>
          </div>
          <div
            className="w-full bg-gray-700 rounded-full h-3"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Fulfillment progress: ${percent}%`}
          >
            <div
              className={`h-3 rounded-full transition-all ${getProgressColor(percent)}`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>

        {/* Line Items */}
        {lines && lines.length > 0 && (
          <div className="space-y-2">
            {lines.map((line) => {
              const isShortClosed = closedShort && !line.is_ready;
              const rowClass = line.is_ready
                ? 'bg-green-500/10 border border-green-500/20'
                : isShortClosed
                  ? 'bg-amber-500/10 border border-amber-500/20'
                  : 'bg-red-500/10 border border-red-500/20';
              const iconClass = line.is_ready
                ? 'w-5 h-5 text-green-400'
                : isShortClosed
                  ? 'w-5 h-5 text-amber-400'
                  : 'w-5 h-5 text-red-400';
              const labelClass = line.is_ready
                ? 'text-sm font-medium text-green-400'
                : isShortClosed
                  ? 'text-sm font-medium text-amber-400'
                  : 'text-sm font-medium text-red-400';
              const label = line.is_ready
                ? 'Ready'
                : isShortClosed
                  ? 'Short Closed'
                  : `Short ${line.shortage}`;

              return (
                <div
                  key={line.line_id || line.line_number}
                  className={`flex items-center justify-between p-3 rounded-lg ${rowClass}`}
                >
                  <div className="flex items-center gap-3">
                    {line.is_ready ? (
                      <CheckCircleIcon className={iconClass} />
                    ) : (
                      <XCircleIcon className={iconClass} />
                    )}
                    <span className="text-sm text-white">
                      <span className="font-medium">Line {line.line_number}:</span>{' '}
                      <span className="text-gray-400">{line.product_sku}</span>{' '}
                      <span className="text-gray-500">({line.quantity_remaining} units)</span>
                    </span>
                  </div>
                  <span className={labelClass}>{label}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Action Buttons */}
        {summary?.can_ship_complete && onShip && (
          <div className="pt-4 border-t border-gray-800">
            <button
              onClick={() => onShip('complete')}
              className="w-full px-4 py-2.5 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition-colors flex items-center justify-center gap-2"
            >
              Ship Complete Order
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </button>
          </div>
        )}

        {!summary?.can_ship_complete && summary?.can_ship_partial && onShip && (
          <div className="pt-4 border-t border-gray-800">
            <button
              onClick={() => onShip('partial')}
              className="w-full px-4 py-2.5 bg-yellow-600 text-white font-medium rounded-lg hover:bg-yellow-700 transition-colors flex items-center justify-center gap-2"
            >
              Ship Partial ({summary.lines_ready} lines)
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
              </svg>
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
