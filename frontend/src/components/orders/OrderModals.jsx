/**
 * CancelOrderModal + DeleteOrderModal - Confirmation modals for order actions.
 *
 * Extracted from OrderDetail.jsx (ARCHITECT-002)
 */
import { useState } from "react";

export function CancelOrderModal({ orderNumber, onCancel, onClose }) {
  const [reason, setReason] = useState("");

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
        <div
          className="fixed inset-0 bg-black/70"
          onClick={onClose}
        />
        <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-md w-full mx-auto p-6">
          <h3 className="text-lg font-semibold text-white mb-4">
            Cancel Order {orderNumber}?
          </h3>
          <p className="text-gray-400 mb-4">
            This will cancel the order. The order can still be deleted after
            cancellation.
          </p>
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">
              Cancellation Reason (optional)
            </label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              rows={3}
              placeholder="Enter reason for cancellation..."
            />
          </div>
          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
            >
              Keep Order
            </button>
            <button
              onClick={() => onCancel(reason)}
              className="px-4 py-2 bg-yellow-600 text-white rounded-lg hover:bg-yellow-500"
            >
              Cancel Order
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export function DeleteOrderModal({ orderNumber, onDelete, onClose }) {
  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
        <div
          className="fixed inset-0 bg-black/70"
          onClick={onClose}
        />
        <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-md w-full mx-auto p-6">
          <h3 className="text-lg font-semibold text-white mb-4">
            Delete Order {orderNumber}?
          </h3>
          <p className="text-gray-400 mb-4">
            This action cannot be undone. All order data, including line
            items and payment records, will be permanently deleted.
          </p>
          <div className="flex justify-end gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
            >
              Keep Order
            </button>
            <button
              onClick={onDelete}
              className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-500"
            >
              Delete Permanently
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
