/**
 * ProductionQueueList - List view of production orders with inline operations
 *
 * Shows all POs with their operations, status, time estimates, and material status.
 * Click a row to open the detail/action modal.
 */
import { useState, useEffect } from 'react';
import { API_URL } from '../../config/api';
import { formatDuration } from '../../utils/formatting';
import ElapsedTimer from './ElapsedTimer';

/**
 * Status badge component
 */
function StatusBadge({ status }) {
  const configs = {
    draft: { bg: 'bg-gray-500/20', text: 'text-gray-400', label: 'Draft' },
    released: { bg: 'bg-blue-500/20', text: 'text-blue-400', label: 'Released' },
    in_progress: { bg: 'bg-purple-500/20', text: 'text-purple-400', label: 'In Progress' },
    complete: { bg: 'bg-green-500/20', text: 'text-green-400', label: 'Complete' },
    short: { bg: 'bg-orange-500/20', text: 'text-orange-400', label: 'Short' },
    cancelled: { bg: 'bg-red-500/20', text: 'text-red-400', label: 'Cancelled' },
  };

  const config = configs[status] || configs.draft;

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}

/**
 * Operations chain - shows all ops as connected status indicators
 */
function OperationsChain({ operations }) {
  if (!operations || operations.length === 0) {
    return <span className="text-gray-600 text-sm">No operations</span>;
  }

  const statusIcons = {
    pending: { icon: '○', color: 'text-gray-400', title: 'Pending' },
    queued: { icon: '◐', color: 'text-blue-400', title: 'Queued' },
    running: { icon: '●', color: 'text-purple-400 animate-pulse', title: 'Running' },
    complete: { icon: '✓', color: 'text-green-400', title: 'Complete' },
    skipped: { icon: '⊘', color: 'text-yellow-400', title: 'Skipped' },
  };

  return (
    <div className="flex items-center gap-1">
      {operations.map((op, idx) => {
        const config = statusIcons[op.status] || statusIcons.pending;
        const tooltip = `${op.operation_code || `Op ${op.sequence}`}: ${config.title}${op.resource_name ? ` on ${op.resource_name}` : ''}`;

        return (
          <div key={op.id} className="flex items-center">
            <span
              className={`${config.color} cursor-default`}
              title={tooltip}
              role="img"
              aria-label={`${op.operation_code || `Op ${op.sequence}`}: ${config.title}`}
            >
              {config.icon}
            </span>
            {idx < operations.length - 1 && (
              <span className="text-gray-600 mx-0.5">→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Materials status indicator
 */
function MaterialsStatus({ materials }) {
  if (!materials || materials.length === 0) {
    return <span className="text-gray-600 text-sm">—</span>;
  }

  const ready = materials.filter(m => m.status === 'allocated' || m.status === 'consumed').length;
  const total = materials.length;
  const hasBlocking = materials.some(m => m.status === 'unavailable' || m.status === 'pending');

  return (
    <span className={`text-sm ${hasBlocking ? 'text-red-400' : ready === total ? 'text-green-400' : 'text-yellow-400'}`}>
      {ready}/{total} ready
      {hasBlocking && <span className="ml-1 text-red-400">!</span>}
    </span>
  );
}

/**
 * Calculate total estimated time from operations
 */
function calculateTotalTime(operations) {
  if (!operations || operations.length === 0) return 0;
  return operations.reduce((sum, op) => {
    return sum + (parseFloat(op.planned_setup_minutes) || 0) + (parseFloat(op.planned_run_minutes) || 0);
  }, 0);
}

/**
 * Single row in the production queue
 */
function ProductionQueueRow({ order, operations, onRowClick }) {
  const totalMinutes = calculateTotalTime(operations);

  // Gather all materials from all operations
  const allMaterials = operations?.flatMap(op => op.materials || []) || [];

  // Check for running operation
  const runningOp = operations?.find(op => op.status === 'running');

  return (
    <tr
      className={`border-b border-gray-800 cursor-pointer transition-colors ${
        runningOp
          ? 'bg-purple-900/30 hover:bg-purple-900/40 border-l-2 border-l-purple-500'
          : 'hover:bg-gray-800/50'
      }`}
      onClick={() => onRowClick(order)}
    >
      {/* Order Code */}
      <td className="px-4 py-3">
        <div className="font-mono text-white">{order.code}</div>
        {order.sales_order_code && (
          <div className="text-xs text-blue-400">SO: {order.sales_order_code}</div>
        )}
      </td>

      {/* Product */}
      <td className="px-4 py-3">
        <div className="text-white">{order.product?.name || order.item?.name || 'Unknown'}</div>
        <div className="text-xs text-gray-500">Qty: {order.quantity_ordered}</div>
      </td>

      {/* Operations */}
      <td className="px-4 py-3">
        <OperationsChain operations={operations} />
      </td>

      {/* Estimated Time / Running Timer */}
      <td className="px-4 py-3">
        {runningOp ? (
          <div className="flex flex-col">
            <ElapsedTimer
              startTime={runningOp.actual_start}
              className="text-purple-400 text-sm"
            />
            <span className="text-gray-500 text-xs">running</span>
          </div>
        ) : (
          <span className="text-gray-300 font-mono text-sm">
            {totalMinutes > 0 ? formatDuration(totalMinutes) : '—'}
          </span>
        )}
      </td>

      {/* Materials */}
      <td className="px-4 py-3">
        <MaterialsStatus materials={allMaterials} />
      </td>

      {/* Status */}
      <td className="px-4 py-3">
        <StatusBadge status={order.status} />
      </td>

      {/* Due Date */}
      <td className="px-4 py-3 text-right">
        {order.due_date ? (
          <span className="text-gray-400 text-sm">
            {new Date(order.due_date).toLocaleDateString()}
          </span>
        ) : (
          <span className="text-gray-600 text-sm">—</span>
        )}
      </td>
    </tr>
  );
}

/**
 * Main ProductionQueueList component
 */
export default function ProductionQueueList({
  orders,
  onOrderClick,
  loading,
  filters,
  onFiltersChange,
}) {
  const [operationsMap, setOperationsMap] = useState({});
  const [loadingOps, setLoadingOps] = useState(false);
  const [workCenters, setWorkCenters] = useState([]);

  // Fetch work centers on mount
  useEffect(() => {
    const fetchWorkCenters = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/work-centers`, {
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setWorkCenters(data.items || data || []);
        }
      } catch { // err unused
        // Non-critical
      }
    };
    fetchWorkCenters();
  }, []);

  // Fetch operations for all orders
  useEffect(() => {
    if (!orders || orders.length === 0) return;

    const fetchAllOperations = async () => {
      setLoadingOps(true);

      const newOpsMap = {};

      // Fetch operations for each order (batch in parallel, max 5 at a time)
      const batchSize = 5;
      for (let i = 0; i < orders.length; i += batchSize) {
        const batch = orders.slice(i, i + batchSize);
        await Promise.all(
          batch.map(async (order) => {
            try {
              const res = await fetch(
                `${API_URL}/api/v1/production-orders/${order.id}/operations`,
                { credentials: "include" }
              );
              if (res.ok) {
                const data = await res.json();
                newOpsMap[order.id] = data.operations || data || [];
              }
            } catch {
              // Skip failed fetches
            }
          })
        );
      }

      setOperationsMap(newOpsMap);
      setLoadingOps(false);
    };

    fetchAllOperations();
  }, [orders]);

  // Filter orders
  const filteredOrders = orders?.filter((order) => {
    // Status filter
    if (filters?.status && filters.status !== 'all') {
      if (filters.status === 'active') {
        // Active = not complete and not short
        if (order.status === 'complete' || order.status === 'short') return false;
      } else {
        if (order.status !== filters.status) return false;
      }
    }

    // Search filter
    if (filters?.search) {
      const search = filters.search.toLowerCase();
      const matchesCode = order.code?.toLowerCase().includes(search);
      const matchesProduct = order.product?.name?.toLowerCase().includes(search) ||
                            order.item?.name?.toLowerCase().includes(search);
      const matchesSO = order.sales_order_code?.toLowerCase().includes(search);
      if (!matchesCode && !matchesProduct && !matchesSO) return false;
    }

    // Work center filter - show orders with any operation in selected work center
    if (filters?.workCenter && filters.workCenter !== 'all') {
      const ops = operationsMap[order.id] || [];
      const hasMatchingOp = ops.some(
        op => op.work_center_id === parseInt(filters.workCenter) ||
              op.work_center_code === filters.workCenter
      );
      if (!hasMatchingOp) return false;
    }

    return true;
  }) || [];

  // Sort orders: in_progress first, then by priority (lower = higher), then by due date
  const sortedOrders = [...filteredOrders].sort((a, b) => {
    // In progress orders first
    const aInProgress = a.status === 'in_progress' ? 0 : 1;
    const bInProgress = b.status === 'in_progress' ? 0 : 1;
    if (aInProgress !== bInProgress) return aInProgress - bInProgress;

    // Then by priority (lower number = higher priority)
    const aPriority = a.priority ?? 5;
    const bPriority = b.priority ?? 5;
    if (aPriority !== bPriority) return aPriority - bPriority;

    // Then by due date (earliest first, null goes last)
    const aDue = a.due_date ? new Date(a.due_date).getTime() : Infinity;
    const bDue = b.due_date ? new Date(b.due_date).getTime() : Infinity;
    return aDue - bDue;
  });

  if (loading) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
        <div className="flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <span className="ml-3 text-gray-400">Loading production orders...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden relative">
      {/* Filters */}
      <div className="p-4 border-b border-gray-800 flex gap-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search by PO code, product, or sales order..."
            value={filters?.search || ''}
            onChange={(e) => onFiltersChange?.({ ...filters, search: e.target.value })}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>
        <select
          value={filters?.status || 'active'}
          onChange={(e) => onFiltersChange?.({ ...filters, status: e.target.value })}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="active">Active Only</option>
          <option value="all">All Status</option>
          <option value="draft">Draft</option>
          <option value="released">Released</option>
          <option value="in_progress">In Progress</option>
          <option value="complete">Complete</option>
          <option value="short">Short</option>
        </select>
        <select
          value={filters?.workCenter || 'all'}
          onChange={(e) => onFiltersChange?.({ ...filters, workCenter: e.target.value })}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="all">All Work Centers</option>
          {workCenters.map((wc) => (
            <option key={wc.id} value={wc.id}>
              {wc.name || wc.code}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="bg-gray-800/50 text-left">
              <th className="px-4 py-3 text-gray-400 font-medium text-sm">Order</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-sm">Product</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-sm">Operations</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-sm">Est. Time</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-sm">Materials</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-sm">Status</th>
              <th className="px-4 py-3 text-gray-400 font-medium text-sm text-right">Due</th>
            </tr>
          </thead>
          <tbody>
            {sortedOrders.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                  {filters?.search || filters?.status !== 'all' || filters?.workCenter !== 'all'
                    ? 'No orders match your filters'
                    : 'No production orders found'}
                </td>
              </tr>
            ) : (
              sortedOrders.map((order) => (
                <ProductionQueueRow
                  key={order.id}
                  order={order}
                  operations={operationsMap[order.id] || []}
                  onRowClick={onOrderClick}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Loading operations overlay - shows on top of table */}
      {loadingOps && (
        <div className="absolute inset-0 bg-gray-900/80 flex items-center justify-center z-10 rounded-xl">
          <div className="flex items-center gap-3 px-4 py-3 bg-gray-800 rounded-lg border border-gray-700 shadow-lg">
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-blue-500 border-t-transparent"></div>
            <span className="text-gray-300 text-sm font-medium">Loading operation details...</span>
          </div>
        </div>
      )}

      {/* Summary footer */}
      {sortedOrders.length > 0 && (
        <div className="px-4 py-3 border-t border-gray-800 text-sm text-gray-500 flex justify-between">
          <span>{sortedOrders.length} order{sortedOrders.length !== 1 ? 's' : ''}</span>
          <span>
            {sortedOrders.filter(o => o.status === 'in_progress').length} in progress
          </span>
        </div>
      )}
    </div>
  );
}
