import { useState, useEffect } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";

export default function ScrapOrderModal({ productionOrder, onClose, onScrap }) {
  const toast = useToast();
  const [scrapReason, setScrapReason] = useState("");
  const [quantityScrapped, setQuantityScrapped] = useState(
    productionOrder.quantity_ordered - (productionOrder.quantity_completed || 0) - (productionOrder.quantity_scrapped || 0)
  );
  const [notes, setNotes] = useState("");
  const [createRemake, setCreateRemake] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [scrapReasons, setScrapReasons] = useState([]);  // Array of { code, name, description }
  const [loading, setLoading] = useState(true);

  // Calculate remaining quantity that can be scrapped
  const remainingQty = productionOrder.quantity_ordered - (productionOrder.quantity_completed || 0) - (productionOrder.quantity_scrapped || 0);
  const isPartialScrap = quantityScrapped < remainingQty;

  // Fetch available scrap reasons from database
  useEffect(() => {
    const fetchReasons = async () => {
      try {
        console.log("Fetching scrap reasons from:", `${API_URL}/api/v1/production-orders/scrap-reasons`);
        const res = await fetch(`${API_URL}/api/v1/production-orders/scrap-reasons`, {
          credentials: "include",
        });
        console.log("Scrap reasons response:", res.status, res.statusText);
        if (res.ok) {
          const data = await res.json();
          // API returns { reasons: [], details: [], descriptions: {} }
          console.log("Scrap reasons API response:", data);
          const reasons = data.details || data.reasons || [];
          console.log("Parsed scrap reasons:", reasons);
          setScrapReasons(reasons);
          if (reasons.length === 0) {
            console.warn("No scrap reasons found in database");
          }
        } else {
          const errorText = await res.text();
          console.error("Failed to fetch scrap reasons:", res.status, errorText);
          toast.error(`Failed to load scrap reasons: ${res.status}`);
        }
      } catch (err) {
        console.error("Error fetching scrap reasons:", err);
        toast.error(`Network error: ${err.message}. Is the backend running on ${API_URL}?`);
      } finally {
        setLoading(false);
      }
    };
    fetchReasons();
  }, []);

  const handleSubmit = async () => {
    if (!scrapReason) {
      toast.error("Please select a scrap reason");
      return;
    }

    if (quantityScrapped <= 0) {
      toast.error("Quantity must be greater than 0");
      return;
    }

    if (quantityScrapped > remainingQty) {
      toast.error(`Cannot scrap more than ${remainingQty} units`);
      return;
    }

    setSubmitting(true);
    try {
      const params = new URLSearchParams({
        scrap_reason: scrapReason,
        quantity_scrapped: quantityScrapped.toString(),
        create_remake: createRemake.toString(),
      });
      if (notes.trim()) {
        params.append("notes", notes.trim());
      }

      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/scrap?${params}`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (res.ok) {
        const data = await res.json();
        if (data.remake_order_code) {
          // Show success with remake order info
          toast.success(
            <div>
              <p>Scrapped {quantityScrapped} units.</p>
              <p className="mt-1 text-green-300">
                Remake order <strong>{data.remake_order_code}</strong> created and ready for scheduling.
              </p>
            </div>,
            { duration: 6000 }
          );
        } else if (isPartialScrap) {
          toast.success(`Scrapped ${quantityScrapped} of ${remainingQty} units. Order remains in progress.`);
        } else {
          toast.success("Order marked as scrapped");
        }
        onScrap(data); // Pass data to parent so it can navigate to remake if needed
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to scrap order");
      }
    } catch (catchErr) {
      toast.error(catchErr.message || "Network error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Scrap Production Order" className="w-full max-w-lg p-6">
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-bold text-white">Scrap Production Order</h2>
            <p className="text-gray-400 text-sm mt-1">
              {productionOrder.code} - {productionOrder.product_name || productionOrder.product_sku}
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
          <div className="grid grid-cols-3 gap-4 text-sm">
            <div>
              <span className="text-gray-400">Ordered:</span>
              <span className="text-white font-medium ml-2">{productionOrder.quantity_ordered}</span>
            </div>
            <div>
              <span className="text-gray-400">Completed:</span>
              <span className="text-green-400 font-medium ml-2">{productionOrder.quantity_completed || 0}</span>
            </div>
            <div>
              <span className="text-gray-400">Remaining:</span>
              <span className="text-white font-medium ml-2">{remainingQty}</span>
            </div>
          </div>
        </div>

        {/* Quantity to Scrap */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            Quantity to Scrap *
          </label>
          <input
            type="number"
            value={quantityScrapped}
            onChange={(e) => setQuantityScrapped(parseInt(e.target.value) || 0)}
            min="1"
            max={remainingQty}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white text-lg"
          />
          <p className="text-gray-500 text-sm mt-1">
            How many units failed? (max: {remainingQty})
          </p>
        </div>

        {/* Partial Scrap Info */}
        {isPartialScrap && (
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-4">
            <div className="flex gap-3">
              <svg className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-blue-400 font-medium">Partial Scrap</p>
                <p className="text-blue-400/80 text-sm">
                  Scrapping {quantityScrapped} of {remainingQty} remaining units.
                  Order will stay in progress for the remaining {remainingQty - quantityScrapped} units.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Scrap Reason */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            Failure Reason *
          </label>
          {loading ? (
            <div className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-gray-500">
              Loading reasons...
            </div>
          ) : (
            <select
              value={scrapReason}
              onChange={(e) => setScrapReason(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white"
              required
            >
              <option value="">Select reason...</option>
              {scrapReasons.map((reason) => (
                <option key={reason.code} value={reason.code}>
                  {reason.name}
                </option>
              ))}
            </select>
          )}
          {scrapReason && (
            <p className="text-gray-500 text-sm mt-1">
              {scrapReasons.find(r => r.code === scrapReason)?.description}
            </p>
          )}
        </div>

        {/* Notes */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            Additional Notes
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white h-24 resize-none"
            placeholder="Describe what happened, approximate failure point, etc..."
          />
        </div>

        {/* Create Remake Toggle - only show for full scrap */}
        {!isPartialScrap && (
          <div className="bg-gray-800/50 rounded-lg p-4 mb-6">
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={createRemake}
                onChange={(e) => setCreateRemake(e.target.checked)}
                className="w-5 h-5 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
              />
              <div>
                <span className="text-white font-medium">Create Remake Order</span>
                <p className="text-gray-400 text-sm">
                  Automatically create a new production order to replace this failed print
                </p>
              </div>
            </label>
          </div>
        )}

        {/* Material Cost Warning */}
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3 mb-6">
          <p className="text-yellow-400 text-sm">
            Material costs for {quantityScrapped} scrapped unit{quantityScrapped > 1 ? "s" : ""} will be added to the order's total COGS.
            {createRemake && !isPartialScrap && " The remake order will use additional material."}
          </p>
        </div>

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
            disabled={!scrapReason || quantityScrapped <= 0 || quantityScrapped > remainingQty || submitting}
            className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Processing..." : `Scrap ${quantityScrapped} Unit${quantityScrapped > 1 ? "s" : ""}`}
          </button>
        </div>
    </Modal>
  );
}
