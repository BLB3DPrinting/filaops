/**
 * OperationsPanel - List of operations for a production order
 *
 * Displays all operations with status, provides click interaction,
 * and shows overall progress summary.
 */
import { useState, useEffect } from 'react';
import { API_URL } from '../../config/api';
import OperationRow from './OperationRow';
import SkipOperationModal from './SkipOperationModal';
import ScrapEntryModal from './ScrapEntryModal';
import OperationCompletionModal from './OperationCompletionModal';
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
 * Calculate total elapsed minutes for all operations
 */
function calculateTotalElapsed(operations) {
  if (!operations || operations.length === 0) return 0;

  return operations.reduce((sum, op) => {
    if (op.status === 'complete') {
      return sum + (op.actual_setup_minutes || 0) + (op.actual_run_minutes || 0);
    }
    if (op.status === 'running' && op.actual_start) {
      const start = parseDateTime(op.actual_start);
      const now = new Date();
      const elapsed = Math.floor((now.getTime() - start.getTime()) / 60000);
      return sum + elapsed;
    }
    return sum;
  }, 0);
}

/**
 * Operations summary bar
 */
function OperationsSummary({ operations }) {
  // Track time for running operations with periodic updates
  const [tick, setTick] = useState(0);

  // Update every minute if there are running operations
  useEffect(() => {
    if (!operations || operations.length === 0) return;

    const hasRunning = operations.some(op => op.status === 'running');
    if (!hasRunning) return;

    const interval = setInterval(() => {
      setTick(t => t + 1);
    }, 60000);

    return () => clearInterval(interval);
  }, [operations]);

  if (!operations || operations.length === 0) return null;

  // Calculate elapsed (recalculated when tick changes)
  const elapsedMinutes = calculateTotalElapsed(operations);

  // Suppress unused variable warning - tick triggers re-render
  void tick;

  const completed = operations.filter(op => op.status === 'complete').length;
  const skipped = operations.filter(op => op.status === 'skipped').length;
  const running = operations.filter(op => op.status === 'running').length;

  const remainingMinutes = operations.reduce((sum, op) => {
    if (['pending', 'queued'].includes(op.status)) {
      return sum + (op.planned_setup_minutes || 0) + (op.planned_run_minutes || 0);
    }
    return sum;
  }, 0);

  return (
    <div className="flex items-center justify-between text-sm border-t border-gray-800 pt-3 mt-3">
      <div className="flex items-center gap-4">
        <span className="text-gray-500">
          {completed + skipped}/{operations.length} complete
        </span>
        {running > 0 && (
          <span className="text-purple-400">
            ● {running} running
          </span>
        )}
      </div>
      <div className="flex items-center gap-4 text-gray-500">
        {elapsedMinutes > 0 && (
          <span>{formatDuration(elapsedMinutes)} elapsed</span>
        )}
        {remainingMinutes > 0 && (
          <span>~{formatDuration(remainingMinutes)} remaining</span>
        )}
      </div>
    </div>
  );
}

/**
 * Empty state when no operations
 */
function EmptyOperations({ orderStatus }) {
  if (orderStatus === 'draft') {
    return (
      <div className="text-center py-8">
        <div className="text-gray-500 mb-2">No operations yet</div>
        <div className="text-sm text-gray-600">
          Operations will be generated when the order is released
        </div>
      </div>
    );
  }

  return (
    <div className="text-center py-8">
      <div className="text-gray-500 mb-2">No operations defined</div>
      <div className="text-sm text-gray-600">
        This product may not have a routing configured
      </div>
    </div>
  );
}

/**
 * Main OperationsPanel component
 */
export default function OperationsPanel({ productionOrderId, productionOrder, orderStatus, onOperationClick }) {
  const [operations, setOperations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [skipModalOpen, setSkipModalOpen] = useState(false);
  const [operationToSkip, setOperationToSkip] = useState(null);
  const [scrapModalOpen, setScrapModalOpen] = useState(false);
  const [operationToScrap, setOperationToScrap] = useState(null);
  const [completionModalOpen, setCompletionModalOpen] = useState(false);
  const [operationToComplete, setOperationToComplete] = useState(null);

  useEffect(() => {
    fetchOperations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [productionOrderId]);

  // Auto-refresh while any operation is running
  useEffect(() => {
    const hasRunning = operations.some(op => op.status === 'running');
    if (!hasRunning) return;

    const interval = setInterval(fetchOperations, 30000); // Refresh every 30s
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [operations]);

  const fetchOperations = async () => {
    if (!productionOrderId) return;

    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations`,
        { credentials: "include" }
      );

      if (!res.ok) throw new Error('Failed to fetch operations');

      const data = await res.json();
      // Handle both array response and object with operations array
      setOperations(Array.isArray(data) ? data : data.operations || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = () => {
    setLoading(true);
    fetchOperations();
  };

  const handleActionSuccess = () => {
    // Refresh operations after action
    fetchOperations();
  };

  const handleActionError = (message) => {
    // Could show inline error or let parent handle
    console.error('Operation action error:', message);
  };

  const handleSkipClick = (operation) => {
    setOperationToSkip(operation);
    setSkipModalOpen(true);
  };

  const handleScrapClick = (operation) => {
    setOperationToScrap(operation);
    setScrapModalOpen(true);
  };

  const handleCompleteClick = (operation) => {
    setOperationToComplete(operation);
    setCompletionModalOpen(true);
  };

  // Find the active (running) operation
  const activeOperation = operations.find(op => op.status === 'running');

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-white">Operations</h2>
        <button
          onClick={handleRefresh}
          disabled={loading}
          className="text-gray-400 hover:text-white transition-colors disabled:opacity-50"
          title="Refresh"
        >
          <svg
            className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 mb-4">
          <p className="text-red-400 text-sm">{error}</p>
        </div>
      )}

      {/* Loading state */}
      {loading && operations.length === 0 && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Operations list */}
      {!loading && operations.length === 0 ? (
        <EmptyOperations orderStatus={orderStatus} />
      ) : (
        <div className="space-y-2">
          {operations
            .sort((a, b) => a.sequence - b.sequence)
            .map(operation => (
              <OperationRow
                key={operation.id}
                operation={operation}
                isActive={activeOperation?.id === operation.id}
                productionOrderId={productionOrderId}
                onActionSuccess={handleActionSuccess}
                onActionError={handleActionError}
                onSkipClick={handleSkipClick}
                onScrapClick={handleScrapClick}
                onCompleteClick={handleCompleteClick}
                onClick={onOperationClick}
              />
            ))}

          <OperationsSummary operations={operations} />
        </div>
      )}

      {/* Skip Operation Modal */}
      <SkipOperationModal
        isOpen={skipModalOpen}
        onClose={() => {
          setSkipModalOpen(false);
          setOperationToSkip(null);
        }}
        operation={operationToSkip}
        productionOrderId={productionOrderId}
        onSkipped={() => {
          fetchOperations();
        }}
      />

      {/* Scrap Entry Modal */}
      <ScrapEntryModal
        isOpen={scrapModalOpen}
        onClose={() => {
          setScrapModalOpen(false);
          setOperationToScrap(null);
        }}
        productionOrderId={productionOrderId}
        operation={operationToScrap}
        productionOrder={productionOrder}
        onScrapComplete={() => {
          fetchOperations();
        }}
      />

      {/* Operation Completion Modal */}
      <OperationCompletionModal
        isOpen={completionModalOpen}
        onClose={() => {
          setCompletionModalOpen(false);
          setOperationToComplete(null);
        }}
        productionOrderId={productionOrderId}
        operation={operationToComplete}
        productionOrder={productionOrder}
        onComplete={() => {
          fetchOperations();
        }}
      />
    </div>
  );
}
