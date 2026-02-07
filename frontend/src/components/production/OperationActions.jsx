/**
 * OperationActions - Action buttons for an operation
 *
 * Shows Start/Complete/Skip buttons based on operation status.
 * Handles API calls and validation.
 */
import { useState, useEffect } from 'react';
import { API_URL } from '../../config/api';

/**
 * Start button with blocking check
 */
function StartButton({ operation, productionOrderId, onSuccess, onError }) {
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    setLoading(true);
    try {
      // First check if operation can start (blocking issues)
      const checkRes = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations/${operation.id}/can-start`,
        { credentials: "include" }
      );

      if (checkRes.ok) {
        const checkData = await checkRes.json();
        if (!checkData.can_start) {
          // Show blocking issues
          const issues = checkData.blocking_issues || [];
          const issueText = issues.map(i => `${i.product_sku}: need ${i.quantity_short} more`).join(', ');
          onError?.(`Cannot start: ${issueText || 'Materials not available'}`);
          setLoading(false);
          return;
        }
      }

      // Proceed with start
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations/${operation.id}/start`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            resource_id: operation.resource_id || null
          })
        }
      );

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start operation');
      }

      onSuccess?.('Operation started');
    } catch (err) {
      onError?.(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        handleStart();
      }}
      disabled={loading}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-lg hover:bg-blue-600/30 disabled:opacity-50 transition-colors"
    >
      {loading ? (
        <>
          <div className="animate-spin rounded-full h-3.5 w-3.5 border-b-2 border-blue-400"></div>
          Checking...
        </>
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
            <path d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
          </svg>
          Start
        </>
      )}
    </button>
  );
}

/**
 * Complete button - opens completion modal
 */
function CompleteButton({ operation, onClick }) {
  const maxQty = Number(operation.quantity_input) || 1;

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-green-600/20 text-green-400 border border-green-500/30 rounded-lg hover:bg-green-600/30 transition-colors"
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
      Complete ({maxQty})
    </button>
  );
}

/**
 * Skip button (opens modal)
 */
function SkipButton({ onClick }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-yellow-600/20 text-yellow-400 border border-yellow-500/30 rounded-lg hover:bg-yellow-600/30 transition-colors"
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
      </svg>
      Skip
    </button>
  );
}

/**
 * Scrap button (opens modal) - for running operations
 */
function ScrapButton({ onClick }) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onClick?.();
      }}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium bg-red-600/20 text-red-400 border border-red-500/30 rounded-lg hover:bg-red-600/30 transition-colors"
    >
      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
      </svg>
      Scrap
    </button>
  );
}

/**
 * Main component - shows appropriate buttons based on status
 */
export default function OperationActions({
  operation,
  productionOrderId,
  onSuccess,
  onError,
  onSkipClick,
  onScrapClick,
  onCompleteClick
}) {
  if (!operation) return null;

  const { status } = operation;

  // No actions for completed or skipped
  if (['complete', 'skipped'].includes(status)) {
    return null;
  }

  return (
    <div className="flex items-center gap-2 mt-2">
      {/* Pending/Queued: Start and Skip */}
      {['pending', 'queued'].includes(status) && (
        <>
          <StartButton
            operation={operation}
            productionOrderId={productionOrderId}
            onSuccess={onSuccess}
            onError={onError}
          />
          <SkipButton onClick={() => onSkipClick?.(operation)} />
        </>
      )}

      {/* Running: Complete and Scrap */}
      {status === 'running' && (
        <>
          <CompleteButton
            operation={operation}
            onClick={() => onCompleteClick?.(operation)}
          />
          <ScrapButton onClick={() => onScrapClick?.(operation)} />
        </>
      )}
    </div>
  );
}
