import { useState } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";

export default function QCInspectionModal({
  productionOrder,
  onClose,
  onComplete,
}) {
  const toast = useToast();
  const [result, setResult] = useState("passed");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/qc`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            result,
            notes: notes.trim() || null,
          }),
        }
      );

      if (res.ok) {
        const data = await res.json();
        if (result === "passed") {
          toast.success(data.message || "QC inspection passed");
        } else {
          toast.warning(data.message || "QC inspection failed");
        }
        onComplete();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to submit QC inspection");
      }
    } catch (catchErr) {
      toast.error(catchErr.message || "Network error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="QC Inspection" className="w-full max-w-lg p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-bold text-white">QC Inspection</h2>
            <p className="text-gray-400 text-sm mt-1">
              {productionOrder.code} -{" "}
              {productionOrder.product_name || productionOrder.product_sku}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl"
          >
            &times;
          </button>
        </div>

        {/* Order Details */}
        <div className="bg-gray-800/50 rounded-lg p-4 mb-6">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">Quantity Completed:</span>
            <span className="text-white font-medium">
              {productionOrder.quantity_completed || productionOrder.quantity_ordered} units
            </span>
          </div>
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">Status:</span>
            <span className="text-green-400 font-medium">
              {productionOrder.status}
            </span>
          </div>
          {productionOrder.completed_at && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Completed:</span>
              <span className="text-white">
                {new Date(productionOrder.completed_at).toLocaleString()}
              </span>
            </div>
          )}
        </div>

        {/* QC Result Selection */}
        <div className="mb-6">
          <label className="block text-sm text-gray-400 mb-3">
            Inspection Result *
          </label>
          <div className="grid grid-cols-2 gap-4">
            <button
              type="button"
              onClick={() => setResult("passed")}
              className={`p-4 rounded-lg border-2 transition-all ${
                result === "passed"
                  ? "border-green-500 bg-green-500/10"
                  : "border-gray-700 bg-gray-800 hover:border-gray-600"
              }`}
            >
              <div className="flex items-center justify-center gap-2">
                <svg
                  className={`w-6 h-6 ${
                    result === "passed" ? "text-green-400" : "text-gray-400"
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                <span
                  className={`font-medium ${
                    result === "passed" ? "text-green-400" : "text-gray-300"
                  }`}
                >
                  Pass
                </span>
              </div>
              <p
                className={`text-xs mt-2 ${
                  result === "passed" ? "text-green-400/70" : "text-gray-500"
                }`}
              >
                Quality acceptable
              </p>
            </button>

            <button
              type="button"
              onClick={() => setResult("failed")}
              className={`p-4 rounded-lg border-2 transition-all ${
                result === "failed"
                  ? "border-red-500 bg-red-500/10"
                  : "border-gray-700 bg-gray-800 hover:border-gray-600"
              }`}
            >
              <div className="flex items-center justify-center gap-2">
                <svg
                  className={`w-6 h-6 ${
                    result === "failed" ? "text-red-400" : "text-gray-400"
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
                <span
                  className={`font-medium ${
                    result === "failed" ? "text-red-400" : "text-gray-300"
                  }`}
                >
                  Fail
                </span>
              </div>
              <p
                className={`text-xs mt-2 ${
                  result === "failed" ? "text-red-400/70" : "text-gray-500"
                }`}
              >
                Quality issues found
              </p>
            </button>
          </div>
        </div>

        {/* Notes */}
        <div className="mb-6">
          <label className="block text-sm text-gray-400 mb-2">
            Inspection Notes {result === "failed" ? "(Recommended)" : "(Optional)"}
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder={
              result === "failed"
                ? "Describe the quality issues found (e.g., surface defects, dimensional issues, etc.)"
                : "Add any notes about the inspection"
            }
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white resize-none"
          />
        </div>

        {/* Warning for failed QC */}
        {result === "failed" && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6">
            <div className="flex gap-3">
              <svg
                className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5"
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
                <p className="text-red-400 font-medium">QC Failed</p>
                <p className="text-red-400/80 text-sm">
                  After marking as failed, you can scrap this order and create a
                  remake if needed.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Success info for passed QC */}
        {result === "passed" && productionOrder.sales_order_id && (
          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4 mb-6">
            <div className="flex gap-3">
              <svg
                className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5"
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
                <p className="text-green-400 font-medium">Ready to Ship</p>
                <p className="text-green-400/80 text-sm">
                  Once QC passes, the linked sales order will be ready for shipping.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className={`flex-1 px-4 py-2 text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed ${
              result === "passed"
                ? "bg-green-600 hover:bg-green-500"
                : "bg-red-600 hover:bg-red-500"
            }`}
          >
            {submitting
              ? "Submitting..."
              : result === "passed"
              ? "Mark as Passed"
              : "Mark as Failed"}
          </button>
        </div>
    </Modal>
  );
}
