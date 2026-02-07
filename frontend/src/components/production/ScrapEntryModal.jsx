/**
 * ScrapEntryModal - Operation-level scrap with cascading material accounting
 *
 * Shows preview of all materials that will be scrapped (from current + prior operations)
 * and allows creation of replacement production order.
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
 * Cascading materials table showing breakdown by operation
 */
function CascadeMaterialsTable({ materials, totalCost }) {
  if (!materials || materials.length === 0) {
    return (
      <div className="text-center py-4 text-gray-500">
        No materials to display
      </div>
    );
  }

  // Group materials by operation
  const byOperation = materials.reduce((acc, mat) => {
    const key = mat.operation_sequence;
    if (!acc[key]) {
      acc[key] = {
        operation_name: mat.operation_name,
        sequence: mat.operation_sequence,
        materials: [],
        subtotal: 0,
      };
    }
    acc[key].materials.push(mat);
    acc[key].subtotal += mat.cost;
    return acc;
  }, {});

  const sortedOps = Object.values(byOperation).sort((a, b) => a.sequence - b.sequence);

  return (
    <div className="space-y-3">
      {sortedOps.map((op) => (
        <div key={op.sequence} className="bg-gray-800/30 rounded-lg p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-white">
              Op {op.sequence}: {op.operation_name}
            </span>
            <span className="text-sm text-gray-400">
              {formatCurrency(op.subtotal)}
            </span>
          </div>
          <div className="space-y-1">
            {op.materials.map((mat, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">{mat.component_sku}</span>
                  <span className="text-gray-600">-</span>
                  <span className="text-gray-500">{mat.component_name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-gray-400">
                    {mat.quantity.toFixed(2)} {mat.unit}
                  </span>
                  <span className="text-gray-400">
                    @ {formatCurrency(mat.unit_cost)}/{mat.unit}
                  </span>
                  <span className="text-white font-medium w-20 text-right">
                    {formatCurrency(mat.cost)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Total */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-700">
        <span className="text-sm font-medium text-white">Total Scrap Cost</span>
        <span className="text-lg font-bold text-red-400">
          {formatCurrency(totalCost)}
        </span>
      </div>
    </div>
  );
}

/**
 * Main ScrapEntryModal component
 */
export default function ScrapEntryModal({
  isOpen,
  onClose,
  productionOrderId,
  operation,
  productionOrder,
  onScrapComplete,
}) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [scrapReasons, setScrapReasons] = useState([]);
  const [cascadeData, setCascadeData] = useState(null);

  // Form state
  const [quantity, setQuantity] = useState(1);
  const [scrapReason, setScrapReason] = useState('');
  const [notes, setNotes] = useState('');
  const [createReplacement, setCreateReplacement] = useState(true);

  // Calculate max scrap quantity (from operation input or PO remaining)
  const maxQuantity = operation?.quantity_input
    ? Number(operation.quantity_input) - Number(operation.quantity_completed || 0)
    : productionOrder?.quantity_ordered
      ? Number(productionOrder.quantity_ordered) - Number(productionOrder.quantity_completed || 0)
      : 1;

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

  // Fetch cascade preview when quantity changes
  const fetchCascade = useCallback(async () => {
    if (!isOpen || !productionOrderId || !operation?.id || quantity <= 0) {
      setCascadeData(null);
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations/${operation.id}/scrap-cascade?quantity=${quantity}`,
        { credentials: "include" }
      );

      if (res.ok) {
        const data = await res.json();
        setCascadeData(data);
      } else {
        const err = await res.json();
        console.error('Cascade fetch error:', err);
        setCascadeData(null);
      }
    } catch (err) {
      console.error('Error fetching cascade:', err);
      setCascadeData(null);
    } finally {
      setLoading(false);
    }
  }, [isOpen, productionOrderId, operation?.id, quantity]);

  // Debounced cascade fetch
  useEffect(() => {
    const timer = setTimeout(fetchCascade, 300);
    return () => clearTimeout(timer);
  }, [fetchCascade]);

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setQuantity(1);
      setScrapReason('');
      setNotes('');
      setCreateReplacement(true);
      setCascadeData(null);
    }
  }, [isOpen]);

  const handleSubmit = async () => {
    if (!scrapReason) {
      toast.error('Please select a scrap reason');
      return;
    }

    if (quantity <= 0 || quantity > maxQuantity) {
      toast.error(`Quantity must be between 1 and ${maxQuantity}`);
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations/${operation.id}/scrap`,
        {
          method: 'POST',
          credentials: "include",
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            quantity_scrapped: quantity,
            scrap_reason_code: scrapReason,
            notes: notes.trim() || null,
            create_replacement: createReplacement,
          }),
        }
      );

      if (res.ok) {
        const data = await res.json();

        // Build success message
        let message = `Scrapped ${quantity} unit${quantity > 1 ? 's' : ''}`;
        if (data.total_scrap_cost) {
          message += ` (${formatCurrency(data.total_scrap_cost)} in materials)`;
        }

        if (data.replacement_order) {
          toast.success(
            <div>
              <p>{message}</p>
              <p className="mt-1 text-green-300">
                Replacement order{' '}
                <strong>{data.replacement_order.code}</strong> created
              </p>
            </div>,
            { duration: 6000 }
          );
        } else {
          toast.success(message);
        }

        onScrapComplete?.(data);
        onClose();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Failed to process scrap');
      }
    } catch (err) {
      toast.error(err.message || 'Network error');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const selectedReason = scrapReasons.find((r) => r.code === scrapReason);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Scrap at Operation" disableClose={submitting} className="w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b border-gray-800">
          <div>
            <h2 className="text-xl font-bold text-white">Scrap at Operation</h2>
            <p className="text-gray-400 text-sm mt-1">
              {productionOrder?.code} - Op {operation?.sequence}:{' '}
              {operation?.operation_name || operation?.operation_code}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl"
          >
            &times;
          </button>
        </div>

        {/* Content - scrollable */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Quantity Input */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Quantity to Scrap *
            </label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Math.max(1, Math.min(maxQuantity, parseInt(e.target.value) || 0)))}
              min="1"
              max={maxQuantity}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white text-lg"
            />
            <p className="text-gray-500 text-sm mt-1">
              Max: {maxQuantity} unit{maxQuantity !== 1 ? 's' : ''}
            </p>
          </div>

          {/* Scrap Reason */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Scrap Reason *
            </label>
            <select
              value={scrapReason}
              onChange={(e) => setScrapReason(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white"
            >
              <option value="">Select reason...</option>
              {scrapReasons.map((reason) => (
                <option key={reason.code} value={reason.code}>
                  {reason.name}
                </option>
              ))}
            </select>
            {selectedReason?.description && (
              <p className="text-gray-500 text-sm mt-1">
                {selectedReason.description}
              </p>
            )}
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Additional Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white h-20 resize-none"
              placeholder="Describe what happened..."
            />
          </div>

          {/* Cascading Materials Preview */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <label className="block text-sm text-gray-400">
                Cascading Material Costs
              </label>
              {loading && (
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400"></div>
              )}
            </div>

            {cascadeData ? (
              <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
                <div className="text-xs text-gray-500 mb-3">
                  Materials from {cascadeData.operations_affected} operation
                  {cascadeData.operations_affected !== 1 ? 's' : ''} will be
                  recorded as scrap
                </div>
                <CascadeMaterialsTable
                  materials={cascadeData.materials_consumed}
                  totalCost={cascadeData.total_cost}
                />
              </div>
            ) : (
              <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700 text-center text-gray-500">
                {loading ? 'Loading cascade preview...' : 'Enter quantity to see material costs'}
              </div>
            )}
          </div>

          {/* Create Replacement Toggle */}
          <div className="bg-gray-800/50 rounded-lg p-4">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={createReplacement}
                onChange={(e) => setCreateReplacement(e.target.checked)}
                className="w-5 h-5 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
              />
              <div>
                <span className="text-white font-medium">
                  Create Replacement Order
                </span>
                <p className="text-gray-400 text-sm">
                  Automatically create a new production order for the scrapped
                  quantity
                </p>
              </div>
            </label>
          </div>

          {/* GL Warning */}
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
            <div className="flex gap-2">
              <svg
                className="w-5 h-5 text-yellow-400 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <div>
                <p className="text-yellow-400 text-sm font-medium">
                  GL Journal Entry
                </p>
                <p className="text-yellow-400/80 text-sm">
                  DR: Scrap Expense (5020)
                  {cascadeData?.total_cost
                    ? ` ${formatCurrency(cascadeData.total_cost)}`
                    : ''}{' '}
                  / CR: WIP Inventory (1210)
                </p>
              </div>
            </div>
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
            disabled={!scrapReason || quantity <= 0 || submitting}
            className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting
              ? 'Processing...'
              : `Scrap ${quantity} Unit${quantity > 1 ? 's' : ''}`}
          </button>
        </div>
    </Modal>
  );
}
