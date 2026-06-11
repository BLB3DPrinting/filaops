/**
 * CommandCenter - Main dashboard page
 *
 * "What do I need to do RIGHT NOW?" view showing:
 * - Today's summary stats
 * - Prioritized action items
 * - Machine/resource status grid
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useCommandCenter from '../hooks/useCommandCenter';
import SummaryCard from '../components/command-center/SummaryCard';
import AlertCard from '../components/command-center/AlertCard';
import MachineStatusGrid from '../components/command-center/MachineStatusGrid';

/**
 * Loading skeleton for summary cards
 */
function SummarySkeleton() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="bg-[var(--color-surface-raised,theme(colors.gray.800))] rounded-xl p-4 animate-pulse">
          <div className="h-4 bg-[var(--color-surface-hover,theme(colors.gray.700))] rounded w-20 mb-2" />
          <div className="h-8 bg-[var(--color-surface-hover,theme(colors.gray.700))] rounded w-12" />
        </div>
      ))}
    </div>
  );
}

/**
 * Loading skeleton for action items
 */
function ActionItemsSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3].map((i) => (
        <div key={i} className="bg-[var(--color-surface-raised,theme(colors.gray.800))] rounded-lg p-4 animate-pulse">
          <div className="flex gap-3">
            <div className="w-5 h-5 bg-[var(--color-surface-hover,theme(colors.gray.700))] rounded-full" />
            <div className="flex-1">
              <div className="h-4 bg-[var(--color-surface-hover,theme(colors.gray.700))] rounded w-1/3 mb-2" />
              <div className="h-3 bg-[var(--color-surface-hover,theme(colors.gray.700))] rounded w-2/3" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * Empty state when no action items
 */
function AllClearState() {
  return (
    <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-8 text-center">
      <svg className="w-16 h-16 text-emerald-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <h3 className="text-lg font-medium text-emerald-400 mb-2">All Clear!</h3>
      <p className="text-gray-400">No issues requiring immediate attention.</p>
    </div>
  );
}

/**
 * Error state
 */
function ErrorState({ message, onRetry }) {
  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-8 text-center">
      <svg className="w-12 h-12 text-red-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <h3 className="text-lg font-medium text-red-400 mb-2">Error Loading Data</h3>
      <p className="text-gray-400 mb-4">{message}</p>
      <button
        onClick={onRetry}
        className="px-4 py-2 bg-red-500/20 text-red-400 rounded-lg hover:bg-red-500/30 transition-colors"
      >
        Try Again
      </button>
    </div>
  );
}

export default function CommandCenter() {
  const navigate = useNavigate();
  const [refreshing, setRefreshing] = useState(false);

  const {
    actionItems,
    summary,
    resources,
    loading,
    error,
    refetch
  } = useCommandCenter(true, 60000); // Auto-refresh every 60s

  const handleRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setTimeout(() => setRefreshing(false), 500);
  };

  const handleMachineClick = (resource) => {
    if (resource.current_operation) {
      navigate(`/admin/production/${resource.current_operation.production_order_id}`);
    }
  };

  // Format today's date
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric'
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Command Center</h1>
          <p className="text-[var(--color-text-muted,theme(colors.gray.400))] text-sm mt-1">{today}</p>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="/admin/dashboard"
            className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
          >
            Analytics →
          </a>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-2 px-4 py-2 bg-[var(--color-surface-raised,theme(colors.gray.800))] rounded-lg hover:bg-[var(--color-surface-hover,theme(colors.gray.700))] transition-colors disabled:opacity-50"
          >
            <svg
              className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <ErrorState message={error} onRetry={refetch} />
      ) : (
        <div className="space-y-8">
          {/* Summary Stats */}
          <section>
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-white">
              <svg className="w-5 h-5 text-[var(--color-text-muted,theme(colors.gray.400))]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
              Today's Summary
            </h2>
            {loading ? (
              <SummarySkeleton />
            ) : (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <SummaryCard
                  label="Orders Due Today"
                  value={summary?.orders_due_today || 0}
                  subtitle={`${summary?.orders_due_today_ready || 0} ready to ship`}
                  variant={summary?.orders_due_today > 0 && summary?.orders_due_today_ready < summary?.orders_due_today ? 'warning' : 'default'}
                  href="/admin/orders?filter=due_today"
                />
                <SummaryCard
                  label="Shipped Today"
                  value={summary?.orders_shipped_today || 0}
                  variant="success"
                  href="/admin/orders?status=shipped"
                />
                <SummaryCard
                  label="In Production"
                  value={summary?.production_in_progress || 0}
                  subtitle={`${summary?.operations_running || 0} operations running`}
                  variant="info"
                  href="/admin/production?status=in_progress"
                />
                <SummaryCard
                  label="Blocked"
                  value={(summary?.production_blocked || 0) + (summary?.orders_overdue || 0)}
                  subtitle={summary?.orders_overdue ? `${summary.orders_overdue} overdue` : undefined}
                  variant={(summary?.production_blocked || 0) + (summary?.orders_overdue || 0) > 0 ? 'danger' : 'default'}
                />
              </div>
            )}
          </section>

          {/* Action Items */}
          <section>
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-white">
              <svg className="w-5 h-5 text-[var(--color-text-muted,theme(colors.gray.400))]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Action Items
              {actionItems.length > 0 && (
                <span className="text-sm font-normal text-[var(--color-text-muted,theme(colors.gray.400))]">
                  ({actionItems.length})
                </span>
              )}
            </h2>
            {loading ? (
              <ActionItemsSkeleton />
            ) : actionItems.length === 0 ? (
              <AllClearState />
            ) : (
              <div className="space-y-3">
                {actionItems.map((item) => (
                  <AlertCard
                    key={item.id}
                    type={item.type}
                    priority={item.priority}
                    title={item.title}
                    description={item.description}
                    entityType={item.entity_type}
                    entityId={item.entity_id}
                    entityCode={item.entity_code}
                    suggestedActions={item.suggested_actions}
                    createdAt={item.created_at}
                    metadata={item.metadata}
                  />
                ))}
              </div>
            )}
          </section>

          {/* Machine Status */}
          <section>
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-white">
              <svg className="w-5 h-5 text-[var(--color-text-muted,theme(colors.gray.400))]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z" />
              </svg>
              Machines
              {resources.length > 0 && (
                <span className="text-sm font-normal text-[var(--color-text-muted,theme(colors.gray.400))]">
                  ({resources.filter(r => r.status === 'running').length}/{resources.length} running)
                </span>
              )}
            </h2>
            {loading ? (
              <div className="bg-[var(--color-surface-raised,theme(colors.gray.800))] rounded-lg p-8 animate-pulse">
                <div className="grid grid-cols-4 gap-4">
                  {[1, 2, 3, 4].map((i) => (
                    <div key={i} className="h-20 bg-[var(--color-surface-hover,theme(colors.gray.700))] rounded" />
                  ))}
                </div>
              </div>
            ) : (
              <MachineStatusGrid
                resources={resources}
                onMachineClick={handleMachineClick}
              />
            )}
          </section>
        </div>
      )}

      {/* Auto-refresh indicator */}
      <div className="fixed bottom-4 right-4 text-xs text-[var(--color-text-muted,theme(colors.gray.600))]">
        Auto-refreshes every 60s
      </div>
    </div>
  );
}
