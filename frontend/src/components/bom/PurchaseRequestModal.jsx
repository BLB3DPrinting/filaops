import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";

// Purchase Request Modal content - Creates actual PO from BOM shortage
export default function PurchaseRequestModal({ line, onClose, token, onSuccess }) {
  const [quantity, setQuantity] = useState(line?.shortage || 1);
  const [vendorId, setVendorId] = useState("");
  const [unitCost, setUnitCost] = useState(line?.component_cost || 0);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [vendors, setVendors] = useState([]);
  const [loadingVendors, setLoadingVendors] = useState(true);
  const [error, setError] = useState(null);
  const [createdPO, setCreatedPO] = useState(null);

  // Fetch vendors on mount
  useEffect(() => {
    const fetchVendors = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/vendors/?active_only=true`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setVendors(data);
        }
      } catch {
        setError("Failed to load vendors. Please refresh the page.");
      } finally {
        setLoadingVendors(false);
      }
    };
    fetchVendors();
  }, [token]);

  const handleSubmit = async () => {
    if (!vendorId) {
      setError("Please select a vendor");
      return;
    }
    if (quantity <= 0) {
      setError("Quantity must be greater than 0");
      return;
    }
    if (unitCost < 0) {
      setError("Unit cost cannot be negative");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/purchase-orders/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          vendor_id: parseInt(vendorId),
          notes: notes || `PO for ${line.component_name}`,
          lines: [
            {
              product_id: line.component_id,
              quantity_ordered: quantity,
              unit_cost: unitCost,
              notes: `From BOM shortage`,
            },
          ],
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to create PO");
      }

      const po = await res.json();
      setCreatedPO(po);
      if (onSuccess) onSuccess(po);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Success state - show created PO
  if (createdPO) {
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
        <h4 className="text-white font-medium mb-2">Purchase Order Created</h4>
        <p className="text-gray-400 text-sm mb-2">
          {createdPO.po_number} for {quantity} {line.component_unit} of{" "}
          {line.component_name}
        </p>
        <p className="text-gray-500 text-xs mb-4">
          Total: ${(quantity * unitCost).toFixed(2)} • Status: Draft
        </p>
        <div className="flex gap-2 justify-center">
          <button
            onClick={() => (window.location.href = "/admin/purchasing")}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            View in Purchasing
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

      <div className="bg-gray-800 rounded-lg p-4">
        <div className="text-sm text-gray-400 mb-1">Component</div>
        <div className="text-white font-medium">{line.component_name}</div>
        <div className="text-gray-500 text-xs">{line.component_sku}</div>
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-400">Current Stock:</span>
          <span className="text-white ml-2">
            {(line.inventory_available || 0).toFixed(2)} {line.component_unit}
          </span>
        </div>
        <div>
          <span className="text-gray-400">Shortage:</span>
          <span className="text-red-400 ml-2">
            {(line.shortage || 0).toFixed(2)} {line.component_unit}
          </span>
        </div>
      </div>

      <div>
        <label className="block text-sm text-gray-400 mb-1">Vendor *</label>
        <select
          value={vendorId}
          onChange={(e) => setVendorId(e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          disabled={loadingVendors}
        >
          <option value="">
            {loadingVendors ? "Loading vendors..." : "Select vendor..."}
          </option>
          {vendors.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} ({v.code})
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Quantity to Order *
          </label>
          <input
            type="number"
            step="0.01"
            value={quantity}
            onChange={(e) => setQuantity(parseFloat(e.target.value) || 0)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Unit Cost ($) *
          </label>
          <input
            type="number"
            step="0.01"
            value={unitCost}
            onChange={(e) => setUnitCost(parseFloat(e.target.value) || 0)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          />
        </div>
      </div>

      <div className="bg-gray-800 rounded-lg p-3 text-sm">
        <span className="text-gray-400">Line Total:</span>
        <span className="text-white font-medium ml-2">
          ${(quantity * unitCost).toFixed(2)}
        </span>
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
          placeholder="Additional notes for the purchase order..."
        />
      </div>

      <div className="flex gap-2 pt-2">
        <button
          onClick={handleSubmit}
          disabled={loading || !vendorId || quantity <= 0}
          className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Creating..." : "Create Purchase Order"}
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
