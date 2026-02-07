import { useState } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";

export default function SplitOrderModal({ productionOrder, onClose, onSplit }) {
  const toast = useToast();
  const [splits, setSplits] = useState([
    { quantity: Math.floor(productionOrder.quantity_ordered / 2) },
    { quantity: Math.ceil(productionOrder.quantity_ordered / 2) },
  ]);
  const [submitting, setSubmitting] = useState(false);

  const totalQuantity = productionOrder.quantity_ordered;
  const splitTotal = splits.reduce((sum, s) => sum + (parseInt(s.quantity) || 0), 0);
  const isValid = splitTotal === parseInt(totalQuantity) && splits.length >= 2 && splits.every(s => s.quantity > 0);

  const handleAddSplit = () => {
    setSplits([...splits, { quantity: 0 }]);
  };

  const handleRemoveSplit = (index) => {
    if (splits.length <= 2) return;
    setSplits(splits.filter((_, i) => i !== index));
  };

  const handleQuantityChange = (index, value) => {
    const newSplits = [...splits];
    newSplits[index].quantity = parseInt(value) || 0;
    setSplits(newSplits);
  };

  const handleEvenSplit = () => {
    const count = splits.length;
    const baseQty = Math.floor(totalQuantity / count);
    const remainder = totalQuantity % count;

    const newSplits = splits.map((_, i) => ({
      quantity: baseQty + (i < remainder ? 1 : 0)
    }));
    setSplits(newSplits);
  };

  const handleSubmit = async () => {
    if (!isValid) return;

    setSubmitting(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/split`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            splits: splits.map(s => ({ quantity: s.quantity }))
          }),
        }
      );

      if (res.ok) {
        const data = await res.json();
        toast.success(data.message || `Split into ${splits.length} orders`);
        onSplit();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to split order");
      }
    } catch (catchErr) {
      toast.error(catchErr.message || "Network error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Split Production Order" className="w-full max-w-lg p-6" disableClose={submitting}>
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-bold text-white">Split Production Order</h2>
            <p className="text-gray-400 text-sm mt-1">
              {productionOrder.code} - {productionOrder.product_name || productionOrder.product_sku}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-xl"
            disabled={submitting}
          >
            &times;
          </button>
        </div>

        {/* Order Info */}
        <div className="bg-gray-800 rounded-lg p-4 mb-6">
          <div className="flex justify-between text-sm">
            <span className="text-gray-400">Total Quantity:</span>
            <span className="text-white font-medium">{totalQuantity} units</span>
          </div>
        </div>

        {/* Split Configuration */}
        <div className="space-y-4 mb-6">
          <div className="flex justify-between items-center">
            <h3 className="text-white font-medium">Split Quantities</h3>
            <button
              onClick={handleEvenSplit}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              Split Evenly
            </button>
          </div>

          {splits.map((split, index) => (
            <div key={index} className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-gray-300 text-sm font-medium">
                {String.fromCharCode(65 + index)}
              </div>
              <div className="flex-1">
                <input
                  type="number"
                  min="1"
                  max={totalQuantity}
                  value={split.quantity}
                  onChange={(e) => handleQuantityChange(index, e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  placeholder="Quantity"
                />
              </div>
              {splits.length > 2 && (
                <button
                  onClick={() => handleRemoveSplit(index)}
                  className="text-red-400 hover:text-red-300 p-2"
                  title="Remove split"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              )}
            </div>
          ))}

          <button
            onClick={handleAddSplit}
            className="w-full py-2 border border-dashed border-gray-600 rounded-lg text-gray-400 hover:text-white hover:border-gray-500 flex items-center justify-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Another Split
          </button>
        </div>

        {/* Validation Status */}
        <div className={`rounded-lg p-3 mb-6 ${isValid ? 'bg-green-500/10 border border-green-500/30' : 'bg-yellow-500/10 border border-yellow-500/30'}`}>
          <div className="flex justify-between text-sm">
            <span className={isValid ? 'text-green-400' : 'text-yellow-400'}>
              Split Total:
            </span>
            <span className={isValid ? 'text-green-400' : 'text-yellow-400'}>
              {splitTotal} / {totalQuantity} units
              {isValid && ' ✓'}
            </span>
          </div>
          {!isValid && splitTotal !== parseInt(totalQuantity) && (
            <p className="text-yellow-400 text-xs mt-1">
              Split quantities must equal total quantity ({totalQuantity - splitTotal > 0 ? `${totalQuantity - splitTotal} remaining` : `${splitTotal - totalQuantity} over`})
            </p>
          )}
        </div>

        {/* Preview */}
        {isValid && (
          <div className="bg-gray-800/50 rounded-lg p-4 mb-6">
            <h4 className="text-gray-400 text-sm mb-2">Preview - New Orders:</h4>
            <div className="space-y-1">
              {splits.map((split, index) => (
                <div key={index} className="flex justify-between text-sm">
                  <span className="text-white">{productionOrder.code}-{String.fromCharCode(65 + index)}</span>
                  <span className="text-gray-400">{split.quantity} units</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={submitting}
            className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!isValid || submitting}
            className="flex-1 px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Splitting..." : `Split into ${splits.length} Orders`}
          </button>
        </div>
    </Modal>
  );
}
