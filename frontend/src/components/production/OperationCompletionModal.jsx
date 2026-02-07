/**
 * OperationCompletionModal - Complete operation with partial pass/scrap
 *
 * Allows completing an operation with:
 * - X good units (pass)
 * - Y bad units (scrap) with reason and cascade preview
 * - Optional replacement order creation
 */
import { useState, useEffect, useCallback } from 'react';
import { API_URL } from '../../config/api';
import { useToast } from '../Toast';
import Modal from '../Modal';

/**
 * Format currency value
 */
function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value || 0);
}

/**
 * Cascading materials summary (collapsed view)
 */
function CascadeSummary({ materials, totalCost, operationsAffected }) {
  const [expanded, setExpanded] = useState(false);

  if (!materials || materials.length === 0) {
    return null;
  }

  // Group by operation
  const byOperation = materials.reduce((acc, mat) => {
    const key = mat.operation_sequence;
    if (!acc[key]) {
      acc[key] = {
        name: mat.operation_name,
        sequence: mat.operation_sequence,
        subtotal: 0,
      };
    }
    acc[key].subtotal += mat.cost;
    return acc;
  }, {});

  const sortedOps = Object.values(byOperation).sort((a, b) => a.sequence - b.sequence);

  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
      <div
        className="flex items-center justify-between cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          <svg
            className={`w-4 h-4 text-red-400 transition-transform ${expanded ? 'rotate-90' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span className="text-red-400 text-sm font-medium">
            Scrap Cost: {formatCurrency(totalCost)}
          </span>
        </div>
        <span className="text-red-400/70 text-xs">
          {operationsAffected} operation{operationsAffected !== 1 ? 's' : ''} affected
        </span>
      </div>

      {expanded && (
        <div className="mt-3 pt-3 border-t border-red-500/20 space-y-2">
          {sortedOps.map((op) => (
            <div key={op.sequence} className="flex items-center justify-between text-xs">
              <span className="text-gray-400">
                Op {op.sequence}: {op.name}
              </span>
              <span className="text-red-400">{formatCurrency(op.subtotal)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Main OperationCompletionModal component
 */
export default function OperationCompletionModal({
  isOpen,
  onClose,
  productionOrderId,
  operation,
  productionOrder,
  onComplete,
}) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [scrapReasons, setScrapReasons] = useState([]);
  const [cascadeData, setCascadeData] = useState(null);

  // Calculate max quantity from operation input
  const maxQty = operation
    ? Number(operation.quantity_input || 0) - Number(operation.quantity_completed || 0)
    : 0;

  // Form state
  const [qtyGood, setQtyGood] = useState(maxQty);
  const [qtyBad, setQtyBad] = useState(0);
  const [scrapReason, setScrapReason] = useState('');
  const [scrapNotes, setScrapNotes] = useState('');
  const [notes, setNotes] = useState('');
  const [createReplacement, setCreateReplacement] = useState(true);

  // Validation
  const total = qtyGood + qtyBad;
  const hasScrap = qtyBad > 0;
  const needsReason = hasScrap && !scrapReason;
  const isValid = total > 0 && total <= maxQty && (!hasScrap || scrapReason);

  // Fetch scrap reasons
  useEffect(() => {
    if (!isOpen) return;

    const fetchReasons = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/production-orders/scrap-reasons`, {
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          setScrapReasons(data.details || data.reasons || []);
        }
      } catch (err) {
        console.error('Error fetching scrap reasons:', err);
      }
    };

    fetchReasons();
  }, [isOpen]);

  // Fetch cascade preview when scrapping
  const fetchCascade = useCallback(async () => {
    if (!isOpen || !productionOrderId || !operation?.id || qtyBad <= 0) {
      setCascadeData(null);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations/${operation.id}/scrap-cascade?quantity=${qtyBad}`,
        { credentials: "include" }
      );

      if (res.ok) {
        const data = await res.json();
        setCascadeData(data);
      } else {
        setCascadeData(null);
      }
    } catch (err) {
      console.error('Error fetching cascade:', err);
      setCascadeData(null);
    } finally {
      setLoading(false);
    }
  }, [isOpen, productionOrderId, operation?.id, qtyBad]);

  // Debounced cascade fetch
  useEffect(() => {
    const timer = setTimeout(fetchCascade, 300);
    return () => clearTimeout(timer);
  }, [fetchCascade]);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen && operation) {
      const max = Number(operation.quantity_input || 0) - Number(operation.quantity_completed || 0);
      setQtyGood(max);
      setQtyBad(0);
      setScrapReason('');
      setScrapNotes('');
      setNotes('');
      setCreateReplacement(true);
      setCascadeData(null);
    }
  }, [isOpen, operation]);

  // Handle quantity changes with auto-adjustment
  const handleGoodChange = (value) => {
    const good = Math.max(0, Math.min(maxQty, parseInt(value) || 0));
    setQtyGood(good);
    // Auto-adjust bad if total exceeds max
    if (good + qtyBad > maxQty) {
      setQtyBad(Math.max(0, maxQty - good));
    }
  };

  const handleBadChange = (value) => {
    const bad = Math.max(0, Math.min(maxQty, parseInt(value) || 0));
    setQtyBad(bad);
    // Auto-adjust good if total exceeds max
    if (qtyGood + bad > maxQty) {
      setQtyGood(Math.max(0, maxQty - bad));
    }
  };

  const handleSubmit = async () => {
    if (!isValid) {
      if (needsReason) {
        toast.error('Please select a scrap reason');
      } else if (total === 0) {
        toast.error('Total quantity must be greater than 0');
      } else if (total > maxQty) {
        toast.error(`Total cannot exceed ${maxQty}`);
      }
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations/${operation.id}/complete`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            quantity_completed: qtyGood,
            quantity_scrapped: qtyBad,
            scrap_reason: hasScrap ? scrapReason : null,
            scrap_notes: hasScrap && scrapNotes.trim() ? scrapNotes.trim() : null,
            notes: notes.trim() || null,
            create_replacement: hasScrap && createReplacement,
          }),
        }
      );

      if (res.ok) {
        const data = await res.json();

        // Build success message
        let message = `Completed: ${qtyGood} good`;
        if (hasScrap) {
          message += `, ${qtyBad} scrapped`;
          if (cascadeData?.total_cost) {
            message += ` (${formatCurrency(cascadeData.total_cost)})`;
          }
        }

        // Check for scrap result with replacement
        if (data.scrap_result?.replacement_order) {
          toast.success(
            <div>
              <p>{message}</p>
              <p className="mt-1 text-green-300">
                Replacement order{' '}
                <strong>{data.scrap_result.replacement_order.code}</strong> created
              </p>
            </div>,
            { duration: 6000 }
          );
        } else {
          toast.success(message);
        }

        onComplete?.(data);
        onClose();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Failed to complete operation');
      }
    } catch (err) {
      toast.error(err.message || 'Network error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen || !operation) return null;

  const selectedReason = scrapReasons.find((r) => r.code === scrapReason);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Complete Operation" disableClose={submitting} className="w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b border-gray-800">
          <div>
            <h2 className="text-xl font-bold text-white">Complete Operation</h2>
            <p className="text-gray-400 text-sm mt-1">
              Op {operation.sequence}: {operation.operation_name || operation.operation_code}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl"
          >
            &times;
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Input quantity summary */}
          <div className="bg-gray-800/50 rounded-lg p-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Input Quantity:</span>
              <span className="text-white font-medium">{maxQty} units</span>
            </div>
            <div className="flex items-center justify-between text-sm mt-1">
              <span className="text-gray-400">Accounted:</span>
              <span className={`font-medium ${total === maxQty ? 'text-green-400' : total > maxQty ? 'text-red-400' : 'text-yellow-400'}`}>
                {total} / {maxQty}
              </span>
            </div>
          </div>

          {/* Quantity inputs */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-green-400 mb-2">
                Good Units (Pass)
              </label>
              <input
                type="number"
                value={qtyGood}
                onChange={(e) => handleGoodChange(e.target.value)}
                min="0"
                max={maxQty}
                className="w-full bg-gray-800 border border-green-500/50 rounded-lg px-4 py-3 text-white text-lg focus:border-green-500 focus:ring-1 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm text-red-400 mb-2">
                Bad Units (Scrap)
              </label>
              <input
                type="number"
                value={qtyBad}
                onChange={(e) => handleBadChange(e.target.value)}
                min="0"
                max={maxQty}
                className="w-full bg-gray-800 border border-red-500/50 rounded-lg px-4 py-3 text-white text-lg focus:border-red-500 focus:ring-1 focus:ring-red-500"
              />
            </div>
          </div>

          {/* Scrap details - only show if scrapping */}
          {hasScrap && (
            <div className="space-y-4 pt-4 border-t border-gray-800">
              <h3 className="text-sm font-medium text-red-400">Scrap Details</h3>

              {/* Scrap Reason */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  Scrap Reason *
                </label>
                <select
                  value={scrapReason}
                  onChange={(e) => setScrapReason(e.target.value)}
                  className={`w-full bg-gray-800 border rounded-lg px-4 py-2 text-white ${
                    needsReason ? 'border-red-500' : 'border-gray-700'
                  }`}
                >
                  <option value="">Select reason...</option>
                  {scrapReasons.map((reason) => (
                    <option key={reason.code} value={reason.code}>
                      {reason.name}
                    </option>
                  ))}
                </select>
                {selectedReason?.description && (
                  <p className="text-gray-500 text-xs mt-1">
                    {selectedReason.description}
                  </p>
                )}
              </div>

              {/* Scrap Notes */}
              <div>
                <label className="block text-sm text-gray-400 mb-2">
                  Scrap Notes
                </label>
                <textarea
                  value={scrapNotes}
                  onChange={(e) => setScrapNotes(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white h-16 resize-none text-sm"
                  placeholder="What went wrong..."
                />
              </div>

              {/* Cascade preview */}
              {loading ? (
                <div className="flex items-center justify-center py-3">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-red-400"></div>
                  <span className="ml-2 text-sm text-gray-400">Calculating costs...</span>
                </div>
              ) : cascadeData ? (
                <CascadeSummary
                  materials={cascadeData.materials_consumed}
                  totalCost={cascadeData.total_cost}
                  operationsAffected={cascadeData.operations_affected}
                />
              ) : null}

              {/* Create Replacement */}
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={createReplacement}
                  onChange={(e) => setCreateReplacement(e.target.checked)}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                />
                <div>
                  <span className="text-white text-sm">Create replacement order</span>
                  <p className="text-gray-500 text-xs">
                    Auto-create PO for {qtyBad} scrapped unit{qtyBad !== 1 ? 's' : ''}
                  </p>
                </div>
              </label>
            </div>
          )}

          {/* General notes */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Completion Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white h-16 resize-none text-sm"
              placeholder="Any notes about this operation..."
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex gap-3 p-6 border-t border-gray-800">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || submitting}
            className={`flex-1 px-4 py-2 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed ${
              hasScrap
                ? 'bg-yellow-600 hover:bg-yellow-500'
                : 'bg-green-600 hover:bg-green-500'
            }`}
          >
            {submitting
              ? 'Processing...'
              : hasScrap
                ? `Complete (${qtyGood} pass, ${qtyBad} scrap)`
                : `Complete ${qtyGood} Unit${qtyGood !== 1 ? 's' : ''}`}
          </button>
        </div>
    </Modal>
  );
}
