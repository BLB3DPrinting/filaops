/**
 * SkipOperationModal - Confirmation modal for skipping an operation
 *
 * Requires a reason before skipping.
 */
import { useState } from 'react';
import { API_URL } from '../../config/api';
import Modal from '../Modal';

export default function SkipOperationModal({
  isOpen,
  onClose,
  operation,
  productionOrderId,
  onSkipped
}) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!reason.trim()) {
      setError('Please provide a reason for skipping');
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrderId}/operations/${operation.id}/skip`,
        {
          method: 'POST',
          credentials: "include",
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ reason: reason.trim() })
        }
      );

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to skip operation');
      }

      onSkipped?.();
      handleClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleClose = () => {
    setReason('');
    setError(null);
    onClose();
  };

  if (!isOpen || !operation) return null;

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Skip Operation" disableClose={submitting} className="w-full max-w-md mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <h2 className="text-xl font-semibold text-white">Skip Operation</h2>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          <p className="text-gray-300">
            Are you sure you want to skip this operation?
          </p>

          {/* Operation info */}
          <div className="bg-gray-800/50 rounded-lg p-4">
            <div className="text-white font-medium">
              {operation.sequence}: {operation.operation_code}
            </div>
            {operation.operation_name && (
              <div className="text-gray-400 text-sm">{operation.operation_name}</div>
            )}
          </div>

          {/* Reason input */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Reason for skipping <span className="text-red-400">*</span>
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="e.g., Customer requested rush delivery, Operation not needed for this order..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white placeholder-gray-500 focus:ring-2 focus:ring-yellow-500 focus:border-transparent resize-none"
            />
          </div>

          {/* Warning */}
          <div className="flex items-start gap-2 text-yellow-400/70 text-sm">
            <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>Skipped operations cannot be undone.</span>
          </div>

          {/* Error */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !reason.trim()}
              className="px-6 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? 'Skipping...' : 'Skip Operation'}
            </button>
          </div>
        </form>
    </Modal>
  );
}
