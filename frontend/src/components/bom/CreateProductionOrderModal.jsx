import { useState } from "react";
import { API_URL } from "../../config/api";

// Production Order Modal - creates a production order from a BOM
export default function CreateProductionOrderModal({
  bom,
  quoteContext,
  onClose,
  onSuccess,
}) {
  // Calculate max producible based on inventory
  const calculateMaxProducible = () => {
    if (!bom.lines || bom.lines.length === 0) return Infinity;

    let maxUnits = Infinity;
    for (const line of bom.lines) {
      const qtyPerUnit = parseFloat(line.quantity) || 0;
      const available = parseFloat(line.inventory_available) || 0;
      if (qtyPerUnit > 0) {
        const canMake = Math.floor(available / qtyPerUnit);
        maxUnits = Math.min(maxUnits, canMake);
      }
    }
    return maxUnits === Infinity ? 0 : maxUnits;
  };

  const maxProducible = calculateMaxProducible();
  const quotedQty = quoteContext?.quantity || 1;

  // Default to quoted quantity if available
  const [quantity, setQuantity] = useState(quotedQty);
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [createBackorder, setCreateBackorder] = useState(false);

  // Check if we can fulfill the entire order
  const canFulfillAll = maxProducible >= quantity;
  const backorderQty = quantity - maxProducible;

  // Find limiting component
  const getLimitingComponent = () => {
    if (!bom.lines || bom.lines.length === 0) return null;

    let limitingLine = null;
    let minUnits = Infinity;

    for (const line of bom.lines) {
      const qtyPerUnit = parseFloat(line.quantity) || 0;
      const available = parseFloat(line.inventory_available) || 0;
      if (qtyPerUnit > 0) {
        const canMake = Math.floor(available / qtyPerUnit);
        if (canMake < minUnits) {
          minUnits = canMake;
          limitingLine = line;
        }
      }
    }
    return limitingLine;
  };

  const limitingComponent = getLimitingComponent();

  const handleSubmit = async () => {
    setLoading(true);
    setError(null);

    try {
      // Determine actual quantity to produce
      const produceQty =
        createBackorder && !canFulfillAll ? maxProducible : quantity;

      const res = await fetch(
        `${API_URL}/api/v1/production-orders?auto_start_print=false`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            product_id: bom.product_id,
            quantity_ordered: produceQty,
            priority: 3, // normal priority (1=highest, 5=lowest)
            notes:
              createBackorder && backorderQty > 0
                ? `${
                    notes ? notes + "\n" : ""
                  }Partial fulfillment: ${produceQty} of ${quantity} ordered. Backorder: ${backorderQty} units pending materials.`
                : notes || null,
          }),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to create production order");
      }

      const newOrder = await res.json();

      // TODO: If createBackorder is true, could also create a backorder record
      // For now, just include it in the notes

      onSuccess(newOrder);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      <div className="bg-gray-800 rounded-lg p-4">
        <div className="text-sm text-gray-400 mb-1">Product</div>
        <div className="text-white font-medium">
          {bom.product_name || `Product #${bom.product_id}`}
        </div>
        <div className="text-gray-500 text-xs">{bom.product_sku}</div>
      </div>

      {/* Quote Context Banner */}
      {quoteContext && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 text-blue-400 text-sm">
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
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <span>
              From Quote: <strong>{quotedQty} units</strong> ordered
            </span>
          </div>
        </div>
      )}

      {/* Inventory Status */}
      <div className="bg-gray-800/50 rounded-lg p-3 border border-gray-700">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm text-gray-400">Inventory Status</span>
          <span
            className={`text-sm font-medium ${
              maxProducible >= quotedQty
                ? "text-green-400"
                : maxProducible > 0
                ? "text-yellow-400"
                : "text-red-400"
            }`}
          >
            Can produce: {maxProducible} units
          </span>
        </div>
        {limitingComponent && maxProducible < quotedQty && (
          <div className="text-xs text-gray-500">
            Limiting factor:{" "}
            <span className="text-yellow-400">
              {limitingComponent.component_name}
            </span>{" "}
            ({limitingComponent.inventory_available?.toFixed(2)}{" "}
            {limitingComponent.component_unit} available)
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <span className="text-gray-400">BOM:</span>
          <span className="text-white ml-2">{bom.code}</span>
        </div>
        <div>
          <span className="text-gray-400">Version:</span>
          <span className="text-white ml-2">v{bom.version}</span>
        </div>
        <div>
          <span className="text-gray-400">Components:</span>
          <span className="text-white ml-2">{bom.lines?.length || 0}</span>
        </div>
        <div>
          <span className="text-gray-400">Unit Cost:</span>
          <span className="text-green-400 ml-2">
            ${parseFloat(bom.total_cost || 0).toFixed(2)}
          </span>
        </div>
      </div>

      {/* Quantity Input with Quick Set Buttons */}
      <div>
        <label className="block text-sm text-gray-400 mb-1">
          Quantity to Produce
        </label>
        <div className="flex gap-2">
          <input
            type="number"
            min="1"
            value={quantity}
            onChange={(e) => setQuantity(parseInt(e.target.value) || 1)}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          />
          {quoteContext && (
            <button
              type="button"
              onClick={() => setQuantity(quotedQty)}
              className={`px-3 py-2 rounded-lg text-sm ${
                quantity === quotedQty
                  ? "bg-blue-600 text-white"
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
            >
              Quoted ({quotedQty})
            </button>
          )}
          {maxProducible > 0 && maxProducible !== quotedQty && (
            <button
              type="button"
              onClick={() => setQuantity(maxProducible)}
              className={`px-3 py-2 rounded-lg text-sm ${
                quantity === maxProducible
                  ? "bg-green-600 text-white"
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
            >
              Max ({maxProducible})
            </button>
          )}
        </div>
      </div>

      {/* Partial Fulfillment Warning & Option */}
      {!canFulfillAll && quantity > 0 && maxProducible > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 text-yellow-400 text-sm font-medium mb-2">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                clipRule="evenodd"
              />
            </svg>
            Insufficient Inventory
          </div>
          <p className="text-sm text-gray-300 mb-3">
            You can only produce <strong>{maxProducible}</strong> of{" "}
            <strong>{quantity}</strong> units with current inventory.
          </p>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={createBackorder}
              onChange={(e) => setCreateBackorder(e.target.checked)}
              className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-300">
              Create partial order ({maxProducible} units) + backorder (
              {backorderQty} units)
            </span>
          </label>
        </div>
      )}

      {/* Zero Inventory Warning */}
      {maxProducible === 0 && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
          <div className="flex items-center gap-2 text-red-400 text-sm font-medium">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clipRule="evenodd"
              />
            </svg>
            No inventory available - cannot produce any units
          </div>
          <p className="text-sm text-gray-400 mt-1">
            Order materials before creating a production order.
          </p>
        </div>
      )}

      <div>
        <label className="block text-sm text-gray-400 mb-1">
          Notes (optional)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
          placeholder="Production notes..."
        />
      </div>

      <div className="bg-gray-800 rounded-lg p-3">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Estimated Total Cost:</span>
          <span className="text-green-400 font-medium">
            $
            {(
              parseFloat(bom.total_cost || 0) *
              (createBackorder && !canFulfillAll ? maxProducible : quantity)
            ).toFixed(2)}
          </span>
        </div>
        {createBackorder && !canFulfillAll && (
          <div className="flex justify-between text-sm mt-1">
            <span className="text-gray-500">
              Backorder ({backorderQty} units):
            </span>
            <span className="text-gray-400">
              ${(parseFloat(bom.total_cost || 0) * backorderQty).toFixed(2)}{" "}
              (pending)
            </span>
          </div>
        )}
      </div>

      <div className="flex gap-2 pt-2">
        <button
          onClick={handleSubmit}
          disabled={
            loading || quantity < 1 || (maxProducible === 0 && !createBackorder)
          }
          className="flex-1 px-4 py-2 bg-gradient-to-r from-orange-600 to-amber-600 text-white rounded-lg hover:from-orange-500 hover:to-amber-500 disabled:opacity-50"
        >
          {loading
            ? "Creating..."
            : createBackorder && !canFulfillAll
            ? `Create Order (${maxProducible} units)`
            : "Create Production Order"}
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
