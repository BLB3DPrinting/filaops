import { useState } from "react";
import { API_URL } from "../../config/api";

/**
 * Work Order Request Modal content - Creates a production/work order for make items.
 * Used when a component has its own BOM (sub-assembly).
 */
export default function WorkOrderRequestModal({ line, onClose, onSuccess }) {
  const [quantity, setQuantity] = useState(line?.shortage || 1);
  const [priority, setPriority] = useState(3);
  const [dueDate, setDueDate] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createdWO, setCreatedWO] = useState(null);

  const handleSubmit = async () => {
    if (quantity <= 0) {
      setError("Quantity must be greater than 0");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/production-orders/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          product_id: line.component_id,
          quantity_ordered: quantity,
          priority: priority,
          due_date: dueDate || null,
          notes: notes || `WO for ${line.component_name} - from BOM shortage`,
          source: "mrp_planned",
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to create Work Order");
      }

      const wo = await res.json();
      setCreatedWO(wo);
      if (onSuccess) onSuccess(wo);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Success state - show created WO
  if (createdWO) {
    return (
      <div className="text-center py-4">
        <div className="w-12 h-12 bg-green-500/20 rounded-full flex items-center justify-center mx-auto mb-4">
          <svg
            className="w-6 h-6 text-green-400"
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
        </div>
        <h4 className="text-white font-medium mb-2">Work Order Created</h4>
        <p className="text-gray-400 text-sm mb-2">
          {createdWO.code} for {quantity} {line.component_unit || "EA"} of{" "}
          {line.component_name}
        </p>
        <p className="text-gray-500 text-xs mb-4">
          Status: {createdWO.status} • Priority: {priority}
        </p>
        <div className="flex gap-2 justify-center">
          <button
            onClick={() => (window.location.href = "/admin/manufacturing")}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700"
          >
            View in Manufacturing
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-500/20 border border-red-500 text-red-400 px-4 py-2 rounded-lg text-sm">
          {error}
        </div>
      )}

      <div className="bg-purple-900/30 border border-purple-500/30 rounded-lg p-4">
        <div className="flex items-center gap-2 mb-2">
          <svg
            className="w-5 h-5 text-purple-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"
            />
          </svg>
          <span className="text-purple-300 font-medium">
            Make Item (Has BOM)
          </span>
        </div>
        <div className="text-sm text-gray-400 mb-1">Component</div>
        <div className="text-white font-medium">{line.component_name}</div>
        <div className="text-gray-500 text-xs">{line.component_sku}</div>
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-400">Current Stock:</span>
          <span className="text-white ml-2">
            {(line.inventory_available || 0).toFixed(2)}{" "}
            {line.component_unit || "EA"}
          </span>
        </div>
        <div>
          <span className="text-gray-400">Shortage:</span>
          <span className="text-red-400 ml-2">
            {(line.shortage || 0).toFixed(2)} {line.component_unit || "EA"}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Quantity to Make *
          </label>
          <input
            type="number"
            step="1"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(parseFloat(e.target.value) || 0)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Priority</label>
          <select
            value={priority}
            onChange={(e) => setPriority(parseInt(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          >
            <option value={1}>1 - Urgent</option>
            <option value={2}>2 - High</option>
            <option value={3}>3 - Normal</option>
            <option value={4}>4 - Low</option>
            <option value={5}>5 - Lowest</option>
          </select>
        </div>
      </div>

      <div>
        <label className="block text-sm text-gray-400 mb-1">
          Due Date (optional)
        </label>
        <input
          type="date"
          value={dueDate}
          onChange={(e) => setDueDate(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          min="2000-01-01"
          max="2099-12-31"
        />
      </div>

      <div>
        <label className="block text-sm text-gray-400 mb-1">
          Notes (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          placeholder="Additional notes for the work order..."
        />
      </div>

      <div className="bg-amber-900/20 border border-amber-500/30 rounded-lg p-3 text-sm">
        <div className="flex items-center gap-2 text-amber-400">
          <svg
            className="w-4 h-4"
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
          <span>
            This will create a Work Order. Check the WO's BOM for material
            requirements.
          </span>
        </div>
      </div>

      <div className="flex gap-2 pt-2">
        <button
          onClick={handleSubmit}
          disabled={loading || quantity <= 0}
          className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50"
        >
          {loading ? "Creating..." : "Create Work Order"}
        </button>
        <button
          onClick={onClose}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
