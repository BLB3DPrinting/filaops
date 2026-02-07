import { useState, useEffect } from "react";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";

export default function CompleteOrderModal({
  productionOrder,
  onClose,
  onComplete,
}) {
  const toast = useToast();
  const [quantityCompleted, setQuantityCompleted] = useState(
    productionOrder.quantity_ordered || 1
  );
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [bomMaterials, setBomMaterials] = useState([]);
  const [selectedSpools, setSelectedSpools] = useState({}); // { materialProductId: spoolId }
  const [availableSpoolsByMaterial, setAvailableSpoolsByMaterial] = useState({}); // { materialProductId: [spools] }
  const [loadingMaterials, setLoadingMaterials] = useState(false);

  const [acknowledgeShort, setAcknowledgeShort] = useState(false);
  const [createRemakeForShortfall, setCreateRemakeForShortfall] = useState(true); // Default to creating remake

  const quantityOrdered = productionOrder.quantity_ordered || 1;
  const quantityScrapped = productionOrder.quantity_scrapped || 0;
  const isOverrun = quantityCompleted > quantityOrdered;

  // Calculate if order would be closed short (fewer units than ordered)
  const totalAccounted = quantityCompleted + quantityScrapped;
  const shortfall = quantityOrdered - totalAccounted;
  const isClosingShort = shortfall > 0;

  // Fetch BOM materials on mount
  useEffect(() => {
    fetchBomMaterials();
  }, [productionOrder.id]);

  const fetchBomMaterials = async () => {
    if (!productionOrder.product_id) return;
    
    setLoadingMaterials(true);
    try {
      // Get BOM for the product
      const bomRes = await fetch(
        `${API_URL}/api/v1/admin/bom/product/${productionOrder.product_id}`,
        { credentials: "include" }
      );
      
      if (bomRes.ok) {
        const bom = await bomRes.json();
        if (bom && bom.lines) {
          // Filter for filament/supply materials (production stage)
          const materials = bom.lines
            .filter((line) => line.consume_stage === "production" && !line.is_cost_only)
            .map((line) => ({
              component_id: line.component_id,
              component_sku: line.component_sku,
              component_name: line.component_name,
              quantity: parseFloat(line.quantity || 0),
              unit: line.unit || "EA",
            }));
          
          setBomMaterials(materials);
          
          // Fetch available spools for each material
          const spoolsMap = {};
          for (const material of materials) {
            try {
              const spoolsRes = await fetch(
                `${API_URL}/api/v1/spools/product/${material.component_id}/available`,
                { credentials: "include" }
              );
              if (spoolsRes.ok) {
                const spoolsData = await spoolsRes.json();
                spoolsMap[material.component_id] = spoolsData.spools || [];
                // Auto-select first available spool if only one
                if (spoolsData.spools && spoolsData.spools.length === 1) {
                  setSelectedSpools((prev) => ({
                    ...prev,
                    [material.component_id]: spoolsData.spools[0].id,
                  }));
                }
              } else {
                spoolsMap[material.component_id] = [];
              }
            } catch {
              // Non-critical - spool selection is optional
              spoolsMap[material.component_id] = [];
            }
          }
          setAvailableSpoolsByMaterial(spoolsMap);
        }
      }
    } catch {
      // Non-critical - spool tracking is optional
    } finally {
      setLoadingMaterials(false);
    }
  };

  const handleSubmit = async () => {
    if (quantityCompleted < 1) {
      toast.error("Quantity must be at least 1");
      return;
    }

    setSubmitting(true);
    try {
      const params = new URLSearchParams({
        quantity_completed: quantityCompleted.toString(),
      });

      // If closing short and user acknowledged, add force flag
      if (isClosingShort && acknowledgeShort) {
        params.append("force_close_short", "true");
      }

      // Prepare request body with optional notes and spool selections
      const requestBody = {};
      if (notes.trim()) {
        requestBody.notes = notes.trim();
      }
      if (Object.keys(selectedSpools).length > 0) {
        requestBody.spools_used = Object.entries(selectedSpools).map(([productId, spoolId]) => ({
          product_id: parseInt(productId),
          spool_id: spoolId,
        }));
      }

      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/complete?${params}`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(requestBody),
        }
      );

      if (res.ok) {
        let remakeOrderCode = null;

        // If closing short and user wants a remake order, create it
        if (isClosingShort && createRemakeForShortfall && shortfall > 0) {
          try {
            const remakeRes = await fetch(`${API_URL}/api/v1/production-orders/`, {
              method: "POST",
              credentials: "include",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                product_id: productionOrder.product_id,
                quantity_ordered: shortfall,
                priority: Math.max(1, (productionOrder.priority || 3) - 1), // Bump priority
                sales_order_id: productionOrder.sales_order_id || null,
                sales_order_line_id: productionOrder.sales_order_line_id || null,
                notes: `Remake for shortfall from ${productionOrder.code} (closed short by ${shortfall} units)`,
                source: "remake",
              }),
            });
            if (remakeRes.ok) {
              const remakeData = await remakeRes.json();
              remakeOrderCode = remakeData.code;
            }
          } catch (remakeErr) {
            console.error("Failed to create remake order:", remakeErr);
            // Don't block completion success, but warn user
          }
        }

        // Show appropriate success message
        if (isClosingShort && remakeOrderCode) {
          toast.success(
            <div>
              <p>Order completed (short by {shortfall} units).</p>
              <p className="mt-1 text-green-300">
                Remake order <strong>{remakeOrderCode}</strong> created for remaining {shortfall} units.
              </p>
            </div>,
            { duration: 6000 }
          );
        } else if (isClosingShort && createRemakeForShortfall) {
          toast.success(`Order completed short. Failed to create remake order - please create manually.`);
        } else if (isClosingShort) {
          toast.success(`Order completed short by ${shortfall} units (no remake created).`);
        } else if (isOverrun) {
          toast.success(
            `Order completed with ${
              quantityCompleted - quantityOrdered
            } extra units (MTS overrun)`
          );
        } else {
          toast.success("Production order completed");
        }
        onComplete();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Failed to complete order");
      }
    } catch (err) {
      toast.error(err.message || "Network error");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Complete Production Order" className="w-full max-w-lg p-6" disableClose={submitting}>
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-xl font-bold text-white">
              Complete Production Order
            </h2>
            <p className="text-gray-400 text-sm mt-1">
              {productionOrder.code} -{" "}
              {productionOrder.product_name || productionOrder.product_sku}
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

        {/* Order Details */}
        <div className="bg-gray-800/50 rounded-lg p-4 mb-6">
          <div className="flex justify-between text-sm mb-2">
            <span className="text-gray-400">Quantity Ordered:</span>
            <span className="text-white font-medium">
              {quantityOrdered} units
            </span>
          </div>
          {productionOrder.scheduled_start && (
            <div className="flex justify-between text-sm">
              <span className="text-gray-400">Scheduled:</span>
              <span className="text-white">
                {new Date(productionOrder.scheduled_start).toLocaleDateString()}
              </span>
            </div>
          )}
        </div>

        {/* Quantity Completed */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            Quantity Completed *
          </label>
          <input
            type="number"
            value={quantityCompleted}
            onChange={(e) =>
              setQuantityCompleted(parseInt(e.target.value) || 0)
            }
            min="1"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white text-lg"
          />
          <p className="text-gray-500 text-sm mt-1">
            Enter actual quantity produced (can exceed ordered qty for MTS
            overruns)
          </p>
        </div>

        {/* Spool Selection */}
        {bomMaterials.length > 0 && (
          <div className="mb-4">
            <label className="block text-sm text-gray-400 mb-2">
              Material Spools Used (Optional)
            </label>
            <div className="space-y-3 bg-gray-800/50 rounded-lg p-3">
              {loadingMaterials ? (
                <div className="text-gray-500 text-sm">Loading materials...</div>
              ) : (
                bomMaterials.map((material) => {
                  const availableSpools = availableSpoolsByMaterial[material.component_id] || [];
                  const requiredWeight = material.quantity * quantityCompleted;
                  
                  return (
                    <div key={material.component_id} className="border-b border-gray-700 pb-3 last:border-0 last:pb-0">
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <div className="text-white text-sm font-medium">
                            {material.component_name || material.component_sku}
                          </div>
                          <div className="text-gray-500 text-xs">
                            Required: {requiredWeight.toFixed(3)} {material.unit}
                          </div>
                        </div>
                      </div>
                      {availableSpools.length > 0 ? (
                        <select
                          value={selectedSpools[material.component_id] || ""}
                          onChange={(e) => {
                            setSelectedSpools((prev) => ({
                              ...prev,
                              [material.component_id]: e.target.value ? parseInt(e.target.value) : null,
                            }));
                          }}
                          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
                        >
                          <option value="">No spool selected</option>
                          {availableSpools.map((spool) => (
                            <option key={spool.id} value={spool.id}>
                              {spool.spool_number} - {spool.current_weight_kg.toFixed(3)}kg remaining ({spool.weight_remaining_percent.toFixed(1)}%)
                            </option>
                          ))}
                        </select>
                      ) : (
                        <div className="text-gray-500 text-xs">No active spools available</div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
            <p className="text-gray-500 text-xs mt-2">
              Select spools to track material consumption and weight remaining
            </p>
          </div>
        )}

        {/* Notes */}
        <div className="mb-4">
          <label className="block text-sm text-gray-400 mb-2">
            Completion Notes (Optional)
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Add any notes about the completion (e.g., quality issues, early completion, etc.)"
            rows={3}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white resize-none"
          />
        </div>

        {/* Overrun Info Banner */}
        {isOverrun && (
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4 mb-6">
            <div className="flex gap-3">
              <svg
                className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5"
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
                <p className="text-blue-400 font-medium">MTS Overrun</p>
                <p className="text-blue-400/80 text-sm">
                  {quantityCompleted - quantityOrdered} extra unit
                  {quantityCompleted - quantityOrdered > 1 ? "s" : ""} will be
                  added to inventory as Make-to-Stock.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Closing Short Warning - requires acknowledgment */}
        {isClosingShort && quantityCompleted > 0 && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 mb-6 space-y-4">
            <label className="flex items-start gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={acknowledgeShort}
                onChange={(e) => setAcknowledgeShort(e.target.checked)}
                className="mt-1 w-5 h-5 rounded bg-gray-700 border-gray-600 text-red-500 focus:ring-red-500 focus:ring-offset-0"
              />
              <div>
                <p className="text-red-400 font-medium">
                  Closing Order Short ({shortfall} units unaccounted)
                </p>
                <p className="text-red-400/80 text-sm">
                  Ordered: {quantityOrdered}, Completing: {quantityCompleted}, Already Scrapped: {quantityScrapped}.
                  <br />
                  <strong>{shortfall} units</strong> were neither completed nor scrapped.
                  Check this box to confirm.
                </p>
              </div>
            </label>

            {/* Create Remake Order Toggle */}
            {acknowledgeShort && (
              <div className="border-t border-red-500/20 pt-4">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={createRemakeForShortfall}
                    onChange={(e) => setCreateRemakeForShortfall(e.target.checked)}
                    className="mt-1 w-5 h-5 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
                  />
                  <div>
                    <p className="text-white font-medium">
                      Create Remake Order for {shortfall} units
                    </p>
                    <p className="text-gray-400 text-sm">
                      Automatically create a new production order for the shortfall
                      {productionOrder.sales_order_id && (
                        <span className="text-blue-400"> (linked to same Sales Order)</span>
                      )}
                    </p>
                  </div>
                </label>
              </div>
            )}
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
            disabled={quantityCompleted < 1 || submitting || (isClosingShort && !acknowledgeShort)}
            className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? "Processing..." : isClosingShort ? "Complete Order (Short)" : "Complete Order"}
          </button>
        </div>
    </Modal>
  );
}
