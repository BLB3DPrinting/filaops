/**
 * ShortageModal - Shown when a PO completes with fewer pieces than ordered
 *
 * Displays shortage summary and offers to create a replacement PO.
 */
import { useState } from 'react';
import { API_URL } from '../../config/api';
import Modal from '../Modal';

export default function ShortageModal({
  isOpen,
  onClose,
  poCode,
  quantityOrdered,
  quantityCompleted,
  quantityShort,
  salesOrderId,
  salesOrderCode,
  productId,
  onReplacementCreated,
}) {
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState(null);

  const handleCreateReplacement = async () => {
    setCreating(true);
    setError(null);

    try {
      // Create a new PO for the shortage quantity
      const res = await fetch(`${API_URL}/api/v1/production-orders`, {
        method: 'POST',
        credentials: "include",
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          product_id: productId,
          quantity_ordered: quantityShort,
          sales_order_id: salesOrderId || null,
          source: 'manual',
          notes: `Replacement for ${poCode} (short by ${quantityShort})`,
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to create replacement PO');
      }

      const newPo = await res.json();
      onReplacementCreated?.(newPo);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Order Short" variant="workbench" disableClose={creating} className="w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center gap-3 p-6 border-b border-[var(--rule-hair)]">
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-[var(--status-amber-tint)]">
            <svg
              className="w-6 h-6 text-[var(--status-amber)]"
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
          </div>
          <div>
            <h2 className="text-xl font-semibold text-[var(--ink)]">Order Short</h2>
            <p className="text-sm text-[var(--ink-3)]">{poCode}</p>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {/* Shortage Summary */}
          <div className="bg-[var(--paper-sunk)] rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-[var(--ink-3)]">Ordered</span>
              <span className="text-[var(--ink)] font-mono">{quantityOrdered}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-[var(--ink-3)]">Completed</span>
              <span className="text-[var(--status-green)] font-mono">{quantityCompleted}</span>
            </div>
            <div className="border-t border-[var(--rule-hair)] pt-2 flex justify-between text-sm">
              <span className="text-[var(--status-amber)] font-medium">Short</span>
              <span className="text-[var(--status-amber)] font-mono font-medium">
                {quantityShort}
              </span>
            </div>
          </div>

          {/* Sales Order Warning */}
          {salesOrderCode && (
            <div className="flex items-start gap-2 text-sm bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg p-3">
              <svg
                className="w-5 h-5 text-[var(--ink-3)] flex-shrink-0 mt-0.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div>
                <span className="text-[var(--ink-2)]">
                  Sales Order <span className="font-mono font-medium">{salesOrderCode}</span> requires{' '}
                  <span className="font-medium">{quantityShort} more</span> to fulfill.
                </span>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="bg-[var(--status-red-tint)] border border-[var(--status-red)]/30 rounded-lg p-3">
              <p className="text-[var(--status-red)] text-sm">{error}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={onClose}
              className="flex-1 px-4 py-2 bg-[var(--paper-sunk)] border border-[var(--rule-hair)] text-[var(--ink-2)] hover:text-[var(--ink)] rounded-lg transition-colors"
            >
              Dismiss
            </button>
            <button
              onClick={handleCreateReplacement}
              disabled={creating}
              className="flex-1 px-4 py-2 bg-[var(--orange)] hover:bg-[var(--orange-press)] text-white rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              {creating ? 'Creating...' : `Create Replacement (${quantityShort})`}
            </button>
          </div>
        </div>
    </Modal>
  );
}
