/**
 * AdjustmentReasonModal - Modal for selecting inventory adjustment reason and notes.
 */
import Modal from "../Modal";

const ADJUSTMENT_REASONS = [
  { value: "Physical count", label: "Physical count" },
  { value: "Found inventory", label: "Found inventory" },
  { value: "Damaged goods", label: "Damaged goods" },
  { value: "Theft/Loss", label: "Theft/Loss" },
  { value: "Expired material", label: "Expired material" },
  { value: "Quality issue", label: "Quality issue" },
  { value: "Returned goods", label: "Returned goods" },
  { value: "Vendor error", label: "Vendor error" },
  { value: "System correction", label: "System correction" },
  { value: "Other", label: "Other" },
];

export default function AdjustmentReasonModal({
  isOpen,
  adjustmentReason,
  adjustmentNotes,
  adjustingQty,
  onReasonChange,
  onNotesChange,
  onConfirm,
  onClose,
}) {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Adjustment Reason"
      className="w-full max-w-md"
      disableClose={adjustingQty}
    >
      <div className="p-6">
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            Reason for Adjustment *
          </label>
          <select
            value={adjustmentReason}
            onChange={(e) => onReasonChange(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            autoFocus
          >
            <option value="">Select a reason...</option>
            {ADJUSTMENT_REASONS.map((reason) => (
              <option key={reason.value} value={reason.value}>
                {reason.label}
              </option>
            ))}
          </select>
        </div>

        {adjustmentReason === "Other" && (
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">
              Specify Reason *
            </label>
            <input
              type="text"
              value={adjustmentNotes}
              onChange={(e) => onNotesChange(e.target.value)}
              placeholder="Enter specific reason..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>
        )}

        {adjustmentReason && adjustmentReason !== "Other" && (
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">
              Additional Notes (Optional)
            </label>
            <textarea
              value={adjustmentNotes}
              onChange={(e) => onNotesChange(e.target.value)}
              placeholder="Add any additional notes..."
              rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white resize-none"
            />
          </div>
        )}

        <div className="flex gap-3">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!adjustmentReason.trim() || (adjustmentReason === "Other" && !adjustmentNotes.trim())}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Confirm Adjustment
          </button>
        </div>
      </div>
    </Modal>
  );
}
