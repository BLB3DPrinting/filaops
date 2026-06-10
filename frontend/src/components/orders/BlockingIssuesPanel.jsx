/**
 * BlockingIssuesPanel - Shows why an order can't ship/produce.
 *
 * Displays blocking issues analysis for sales or production orders.
 * Shows status badge, issue list, and resolution actions.
 */
import { useBlockingIssues } from '../../hooks/useBlockingIssues';

/**
 * Status badge showing fulfillment/production readiness
 */
function StatusBadge({ canProceed, blockingCount }) {
  if (canProceed) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-green-500/20 text-green-400 border border-green-500/30">
        <span className="w-2 h-2 rounded-full bg-green-400"></span>
        Ready
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-medium bg-red-500/20 text-red-400 border border-red-500/30">
      <span className="w-2 h-2 rounded-full bg-red-400"></span>
      {blockingCount} Blocking Issue{blockingCount !== 1 ? 's' : ''}
    </span>
  );
}

/**
 * Icon for issue type
 */
function IssueIcon({ type }) {
  const icons = {
    production_incomplete: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    production_missing: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
    material_shortage: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
    purchase_pending: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    ),
    inventory_reserved: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
      </svg>
    ),
    quality_hold: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  };

  return icons[type] || (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  );
}

/**
 * Severity badge colors
 */
function getSeverityColors(severity) {
  switch (severity) {
    case 'blocking':
      return 'text-red-400 bg-red-500/10';
    case 'warning':
      return 'text-yellow-400 bg-yellow-500/10';
    case 'info':
      return 'text-blue-400 bg-blue-500/10';
    default:
      return 'text-gray-400 bg-gray-500/10';
  }
}

/**
 * Single blocking issue row
 */
function BlockingIssueRow({ issue }) {
  const severityColors = getSeverityColors(issue.severity);

  return (
    <div className={`flex items-start gap-3 p-3 rounded-lg ${severityColors}`}>
      <div className="flex-shrink-0 mt-0.5">
        <IssueIcon type={issue.type} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{issue.message}</p>
        <p className="text-xs text-gray-500 mt-1">
          {issue.reference_type}: {issue.reference_code}
        </p>
      </div>
    </div>
  );
}

/**
 * Line issues section for sales orders
 */
function LineIssuesSection({ lineIssues }) {
  const linesWithIssues = lineIssues.filter(line => line.blocking_issues.length > 0 || line.quantity_short > 0);

  if (linesWithIssues.length === 0) return null;

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
        Line Issues
      </h4>
      {linesWithIssues.map((line) => (
        <div key={line.line_number} className="bg-gray-800/50 rounded-lg p-3 space-y-2">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-medium text-white">
                Line {line.line_number}: {line.product_sku}
              </p>
              <p className="text-xs text-gray-500">{line.product_name}</p>
            </div>
            {line.quantity_short > 0 && (
              <span className="text-xs px-2 py-1 rounded bg-red-500/20 text-red-400">
                Short: {line.quantity_short.toLocaleString()}
              </span>
            )}
          </div>
          {line.blocking_issues.map((issue, idx) => (
            <BlockingIssueRow key={idx} issue={issue} />
          ))}
        </div>
      ))}
    </div>
  );
}

/**
 * Badge showing whether a material shortage is covered by an incoming PO.
 * HARD-6: distinguishes "short now, covered by PO" vs "short, no supply".
 */
function ShortageStateBadge({ mat }) {
  if (mat.status === 'ok') return null;

  // covered_by_incoming: short on-hand but open PO(s) cover the full gap
  if (mat.covered_by_incoming) {
    return (
      <span className="text-xs px-2 py-1 rounded bg-yellow-500/20 text-yellow-400">
        Covered by PO
      </span>
    );
  }

  return (
    <span className="text-xs px-2 py-1 rounded bg-red-500/20 text-red-400">
      Short: {Number(mat.quantity_short).toLocaleString()}
    </span>
  );
}

/**
 * Material issues section for production orders
 */
function MaterialIssuesSection({ materialIssues }) {
  const issuesWithShortage = materialIssues.filter(mat => mat.status !== 'ok');

  if (issuesWithShortage.length === 0) return null;

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
        Material Issues
      </h4>
      {issuesWithShortage.map((mat) => (
        <div key={mat.product_id} className="bg-gray-800/50 rounded-lg p-3">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-sm font-medium text-white">{mat.product_sku}</p>
              <p className="text-xs text-gray-500">{mat.product_name}</p>
            </div>
            <ShortageStateBadge mat={mat} />
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
            <div>
              <span className="text-gray-500">Required:</span>
              <span className="text-white ml-1">{Number(mat.quantity_required).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-gray-500">Available:</span>
              <span className="text-white ml-1">{Number(mat.quantity_available).toLocaleString()}</span>
            </div>
            <div>
              <span className="text-gray-500">Short:</span>
              <span className={mat.covered_by_incoming ? 'text-yellow-400 ml-1' : 'text-red-400 ml-1'}>
                {Number(mat.quantity_short).toLocaleString()}
              </span>
            </div>
          </div>
          {mat.incoming_supply && (
            <div className={`mt-2 p-2 rounded text-xs ${
              mat.covered_by_incoming
                ? 'bg-green-500/10 border border-green-500/20'
                : 'bg-blue-500/10'
            }`}>
              {mat.covered_by_incoming ? (
                <span className="text-green-400 font-medium">Covered by incoming PO: </span>
              ) : (
                <span className="text-blue-400">Incoming: </span>
              )}
              <span className="text-white">
                {Number(mat.incoming_supply.quantity).toLocaleString()} from {mat.incoming_supply.purchase_order_code}
              </span>
              {mat.incoming_supply.expected_date && (
                <span className="text-gray-500 ml-1">
                  (ETA: {mat.incoming_supply.expected_date})
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * Resolution actions section
 */
function ResolutionActionsSection({ actions, onActionClick }) {
  if (!actions || actions.length === 0) return null;

  const getPriorityColor = (priority) => {
    if (priority === 1) return 'text-red-400 bg-red-500/10 border-red-500/30';
    if (priority === 2) return 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30';
    return 'text-blue-400 bg-blue-500/10 border-blue-500/30';
  };

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
        Suggested Actions
      </h4>
      {actions.map((action, idx) => (
        <button
          key={idx}
          onClick={() => onActionClick?.(action)}
          className={`w-full text-left p-3 rounded-lg border transition-colors hover:bg-gray-800 ${getPriorityColor(action.priority)}`}
        >
          <div className="flex items-start gap-3">
            <span className="flex-shrink-0 w-6 h-6 rounded-full bg-gray-700 flex items-center justify-center text-xs font-bold">
              {action.priority}
            </span>
            <div className="flex-1">
              <p className="text-sm font-medium">{action.action}</p>
              <p className="text-xs text-gray-500 mt-1">{action.impact}</p>
            </div>
            <svg className="w-4 h-4 flex-shrink-0 mt-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </div>
        </button>
      ))}
    </div>
  );
}

/**
 * Estimated ready date display
 */
function EstimatedReadyDate({ date, daysUntil }) {
  if (!date) return null;

  return (
    <div className="flex items-center gap-2 text-sm">
      <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
      <span className="text-gray-400">Est. Ready:</span>
      <span className="text-white">{date}</span>
      {daysUntil !== null && daysUntil !== undefined && (
        <span className={`text-xs px-2 py-0.5 rounded ${
          daysUntil <= 0 ? 'bg-green-500/20 text-green-400' :
          daysUntil <= 3 ? 'bg-yellow-500/20 text-yellow-400' :
          'bg-gray-500/20 text-gray-400'
        }`}>
          {daysUntil <= 0 ? 'Ready now' : `${daysUntil} day${daysUntil !== 1 ? 's' : ''}`}
        </span>
      )}
    </div>
  );
}

/**
 * Main BlockingIssuesPanel component
 */
export function BlockingIssuesPanel({
  orderType,
  orderId,
  onActionClick,
  className = '',
}) {
  const { data, loading, error, refetch } = useBlockingIssues(orderType, orderId);

  // Loading state
  if (loading) {
    return (
      <div className={`bg-gray-900 border border-gray-800 rounded-xl p-4 ${className}`}>
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
      <div className={`bg-gray-900 border border-red-500/30 rounded-xl p-4 ${className}`}>
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div>
            <p className="text-red-400 font-medium">Failed to load blocking issues</p>
            <p className="text-sm text-gray-500">{error}</p>
          </div>
          <button
            onClick={refetch}
            className="ml-auto px-3 py-1 text-sm bg-gray-800 text-gray-300 rounded hover:bg-gray-700"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  // No data state
  if (!data) {
    return (
      <div className={`bg-gray-900 border border-gray-800 rounded-xl p-4 text-center text-gray-500 ${className}`}>
        No blocking issues data available
      </div>
    );
  }

  const isSalesOrder = orderType === 'sales';
  const canProceed = isSalesOrder
    ? data.status_summary?.can_fulfill
    : data.status_summary?.can_produce;
  const blockingCount = data.status_summary?.blocking_count || 0;

  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-xl ${className}`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-white">
              {isSalesOrder ? 'Fulfillment Status' : 'Production Readiness'}
            </h3>
            <StatusBadge canProceed={canProceed} blockingCount={blockingCount} />
          </div>
          <button
            onClick={refetch}
            className="p-2 text-gray-500 hover:text-white rounded-lg hover:bg-gray-800"
            title="Refresh"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>
        {data.status_summary?.estimated_ready_date && (
          <div className="mt-2">
            <EstimatedReadyDate
              date={data.status_summary.estimated_ready_date}
              daysUntil={data.status_summary.days_until_ready}
            />
          </div>
        )}
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Ready message */}
        {canProceed && (
          <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-lg">
            <div className="flex items-center gap-3">
              <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-green-400 font-medium">
                  {isSalesOrder ? 'Ready to fulfill' : 'Ready to produce'}
                </p>
                <p className="text-sm text-gray-400">
                  {isSalesOrder
                    ? 'All items are available for shipping'
                    : 'All materials are available for production'}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Linked sales order for production orders */}
        {!isSalesOrder && data.linked_sales_order && (
          <div className="p-3 bg-gray-800/50 rounded-lg">
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Linked Sales Order</p>
            <p className="text-sm text-white">
              {data.linked_sales_order.code} - {data.linked_sales_order.customer}
            </p>
            {data.linked_sales_order.requested_date && (
              <p className="text-xs text-gray-500 mt-1">
                Requested: {data.linked_sales_order.requested_date}
              </p>
            )}
          </div>
        )}

        {/* Line issues for sales orders */}
        {isSalesOrder && data.line_issues && (
          <LineIssuesSection lineIssues={data.line_issues} />
        )}

        {/* Material issues for production orders */}
        {!isSalesOrder && data.material_issues && (
          <MaterialIssuesSection materialIssues={data.material_issues} />
        )}

        {/* Other issues for production orders */}
        {!isSalesOrder && data.other_issues && data.other_issues.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
              Other Issues
            </h4>
            {data.other_issues.map((issue, idx) => (
              <div key={idx} className={`p-3 rounded-lg ${getSeverityColors(issue.severity)}`}>
                <p className="text-sm font-medium">{issue.message}</p>
              </div>
            ))}
          </div>
        )}

        {/* Resolution actions */}
        {data.resolution_actions && (
          <ResolutionActionsSection
            actions={data.resolution_actions}
            onActionClick={onActionClick}
          />
        )}
      </div>
    </div>
  );
}

export default BlockingIssuesPanel;
