/**
 * ProductionProgressSummary - Shows overall progress across all WOs
 * ProductionOrderStatusCard - Read-only display of WO status
 *
 * Extracted from OrderDetail.jsx (ARCHITECT-002)
 */

export function ProductionProgressSummary({ orders }) {
  const completed = orders.filter(o => o.status === "complete").length;
  const inProgress = orders.filter(o => o.status === "in_progress").length;
  const short = orders.filter(o => o.status === "short").length;
  const scrapped = orders.filter(o => o.status === "scrapped").length;
  const total = orders.length;
  const completionPercent = total > 0 ? (completed / total) * 100 : 0;

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 mb-2">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm text-gray-400">Overall Progress</span>
        <span className="text-sm text-white font-medium">{completed}/{total} Complete</span>
      </div>
      <div className="w-full bg-gray-700 rounded-full h-2 mb-2">
        <div
          className="bg-green-500 h-2 rounded-full transition-all"
          style={{ width: `${completionPercent}%` }}
        />
      </div>
      <div className="flex gap-4 text-xs">
        {inProgress > 0 && (
          <span className="text-purple-400">{inProgress} In Progress</span>
        )}
        {completed > 0 && (
          <span className="text-green-400">{completed} Complete</span>
        )}
        {short > 0 && (
          <span className="text-amber-400">{short} Short</span>
        )}
        {scrapped > 0 && (
          <span className="text-red-400">{scrapped} Scrapped</span>
        )}
      </div>
    </div>
  );
}

const STATUS_CONFIG = {
  draft: { color: "bg-gray-500", text: "Draft" },
  released: { color: "bg-blue-500", text: "Released" },
  in_progress: { color: "bg-purple-500", text: "In Progress" },
  short: { color: "bg-amber-500", text: "Short" },
  complete: { color: "bg-green-500", text: "Complete" },
  scrapped: { color: "bg-red-500", text: "Scrapped" },
  closed: { color: "bg-gray-400", text: "Closed" },
};

const OP_STATUS_CLASS = {
  complete: "bg-green-500/20 text-green-400",
  running: "bg-purple-500/20 text-purple-400",
  queued: "bg-blue-500/20 text-blue-400",
};

const PROGRESS_BAR_CLASS = {
  complete: "bg-green-500",
  scrapped: "bg-red-500",
};

export function ProductionOrderStatusCard({ order, onViewInProduction, onAcceptShort }) {
  const status = STATUS_CONFIG[order.status] || { color: "bg-gray-500", text: order.status };
  const progressPercent = order.quantity_ordered > 0
    ? ((order.quantity_completed || 0) / order.quantity_ordered) * 100
    : 0;

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-white font-medium">{order.code || `WO-${order.id}`}</span>
            <span className={`px-2 py-0.5 ${status.color} text-white text-xs rounded-full`}>
              {status.text}
            </span>
          </div>
          <p className="text-sm text-gray-400 mt-1">
            {order.product_name || order.product_sku || "N/A"}
          </p>
        </div>
        <button
          onClick={onViewInProduction}
          className="text-blue-400 hover:text-blue-300 text-sm flex items-center gap-1"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
          </svg>
          View
        </button>
      </div>

      {/* Accept Short action for orders stuck in "short" status */}
      {onAcceptShort && order.status === "short" && (order.quantity_completed || 0) > 0 && (
        <div className="mt-2 mb-1">
          <button
            onClick={() => onAcceptShort(order)}
            className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs rounded font-medium transition-colors"
          >
            Accept Short ({order.quantity_completed}/{order.quantity_ordered})
          </button>
        </div>
      )}

      {/* Progress bar */}
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-gray-700 rounded-full h-1.5">
          <div
            className={`h-1.5 rounded-full transition-all ${
              PROGRESS_BAR_CLASS[order.status] || "bg-blue-500"
            }`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
        <span className="text-xs text-gray-400 w-20 text-right">
          {order.quantity_completed || 0} / {order.quantity_ordered}
        </span>
      </div>

      {/* Operations summary if available */}
      {order.operations && order.operations.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-700">
          <div className="text-xs text-gray-500 mb-2">Operations:</div>
          <div className="flex flex-wrap gap-1">
            {order.operations.slice(0, 5).map((op, idx) => (
              <span
                key={idx}
                className={`px-2 py-0.5 rounded text-xs ${
                  OP_STATUS_CLASS[op.status] || "bg-gray-500/20 text-gray-400"
                }`}
              >
                {op.sequence}. {op.operation_name || op.operation_code || "Op"}
              </span>
            ))}
            {order.operations.length > 5 && (
              <span className="text-xs text-gray-500">+{order.operations.length - 5} more</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
