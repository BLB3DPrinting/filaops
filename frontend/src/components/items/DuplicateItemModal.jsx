/**
 * DuplicateItemModal — Clone an item with inline BOM component swapping.
 *
 * Shows new SKU/name fields, and if the source item has a BOM, displays
 * its lines with the ability to swap components before saving.
 */
import { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../Toast";
import SearchableSelect from "../SearchableSelect";

export default function DuplicateItemModal({ isOpen, onClose, onSuccess, sourceItem }) {
  const api = useApi();
  const toast = useToast();

  const [newSku, setNewSku] = useState("");
  const [newName, setNewName] = useState("");
  const [bomLines, setBomLines] = useState([]);
  const [overrides, setOverrides] = useState({});
  const [swappingLineIdx, setSwappingLineIdx] = useState(null);
  const [allProducts, setAllProducts] = useState([]);
  const [loadingBom, setLoadingBom] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Reset state when modal opens with a new source item
  useEffect(() => {
    if (isOpen && sourceItem) {
      setNewSku("");
      setNewName(`${sourceItem.name} (Copy)`);
      setOverrides({});
      setSwappingLineIdx(null);
      setBomLines([]);
    }
  }, [isOpen, sourceItem]);

  // Fetch BOM lines for the source item
  useEffect(() => {
    if (!isOpen || !sourceItem?.id) return;

    const fetchBom = async () => {
      setLoadingBom(true);
      try {
        const data = await api.get(`/api/v1/admin/bom/product/${sourceItem.id}`);
        setBomLines(data.lines || []);
      } catch {
        // No BOM or not found — that's fine
        setBomLines([]);
      } finally {
        setLoadingBom(false);
      }
    };
    fetchBom();
  }, [isOpen, sourceItem, api]);

  // Fetch all products for the swap selector (lazy — only when a swap is initiated)
  const ensureProducts = useCallback(async () => {
    if (allProducts.length > 0) return;
    try {
      const data = await api.get("/api/v1/items?limit=500&active_only=true");
      setAllProducts(data.items || []);
    } catch {
      toast.error("Failed to load products for swap");
    }
  }, [api, allProducts.length, toast]);

  const handleSwapClick = async (idx) => {
    await ensureProducts();
    setSwappingLineIdx(idx);
  };

  const handleSwapSelect = (newComponentId) => {
    const line = bomLines[swappingLineIdx];
    const originalId = line.component_id;
    const newId = parseInt(newComponentId, 10);

    if (newId === originalId) {
      // Undo override if selecting the original component back
      const next = { ...overrides };
      delete next[originalId];
      setOverrides(next);
    } else {
      setOverrides((prev) => ({
        ...prev,
        [originalId]: newId,
      }));
    }
    setSwappingLineIdx(null);
  };

  const getDisplayComponent = (line) => {
    const overrideId = overrides[line.component_id];
    if (overrideId) {
      const product = allProducts.find((p) => p.id === overrideId);
      return product
        ? { sku: product.sku, name: product.name, swapped: true }
        : { sku: line.component_sku, name: line.component_name, swapped: false };
    }
    return { sku: line.component_sku, name: line.component_name, swapped: false };
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!newSku.trim()) {
      toast.error("SKU is required");
      return;
    }
    if (!newName.trim()) {
      toast.error("Name is required");
      return;
    }

    setSubmitting(true);
    try {
      const bomLineOverrides = Object.entries(overrides).map(
        ([originalId, newId]) => ({
          original_component_id: parseInt(originalId, 10),
          new_component_id: newId,
        })
      );

      const result = await api.post(`/api/v1/items/${sourceItem.id}/duplicate`, {
        new_sku: newSku.trim(),
        new_name: newName.trim(),
        bom_line_overrides: bomLineOverrides,
      });

      toast.success(result.message || "Item duplicated");
      onSuccess?.(result);
    } catch (err) {
      toast.error(err.message || "Failed to duplicate item");
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen || !sourceItem) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-white">Duplicate Item</h2>
            <p className="text-sm text-gray-400 mt-1">
              Cloning from <span className="text-blue-400 font-mono">{sourceItem.sku}</span>
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {/* New SKU & Name */}
          <div className="p-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                New SKU <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={newSku}
                onChange={(e) => setNewSku(e.target.value)}
                placeholder="Enter new SKU"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                autoFocus
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                New Name <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
                required
              />
            </div>
          </div>

          {/* BOM Lines */}
          {loadingBom && (
            <div className="px-6 pb-4 text-gray-400 text-sm">Loading BOM...</div>
          )}

          {!loadingBom && bomLines.length > 0 && (
            <div className="px-6 pb-4">
              <h3 className="text-sm font-medium text-gray-300 mb-3">
                BOM Lines
                <span className="text-gray-500 ml-2">({bomLines.length} components)</span>
              </h3>
              <div className="border border-gray-700 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-800/50">
                      <th className="text-left px-3 py-2 text-gray-400 font-medium">#</th>
                      <th className="text-left px-3 py-2 text-gray-400 font-medium">Component</th>
                      <th className="text-right px-3 py-2 text-gray-400 font-medium">Qty</th>
                      <th className="text-left px-3 py-2 text-gray-400 font-medium">Unit</th>
                      <th className="text-right px-3 py-2 text-gray-400 font-medium">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bomLines.map((line, idx) => {
                      const display = getDisplayComponent(line);
                      const isSwapping = swappingLineIdx === idx;

                      return (
                        <tr
                          key={line.id}
                          className={`border-t border-gray-700/50 ${
                            display.swapped ? "bg-blue-900/20" : ""
                          }`}
                        >
                          <td className="px-3 py-2 text-gray-500">{line.sequence || idx + 1}</td>
                          <td className="px-3 py-2">
                            {isSwapping ? (
                              <SearchableSelect
                                options={allProducts}
                                value={String(overrides[line.component_id] || line.component_id)}
                                onChange={handleSwapSelect}
                                placeholder="Search for replacement..."
                                displayKey="name"
                                valueKey="id"
                                formatOption={(opt) => `${opt.sku} — ${opt.name}`}
                              />
                            ) : (
                              <div>
                                <span className="text-white font-mono text-xs">{display.sku}</span>
                                <span className="text-gray-400 ml-2">{display.name}</span>
                                {display.swapped && (
                                  <span className="ml-2 text-xs text-blue-400">(swapped)</span>
                                )}
                              </div>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-white">
                            {parseFloat(line.quantity).toLocaleString()}
                          </td>
                          <td className="px-3 py-2 text-gray-400">{line.unit || "EA"}</td>
                          <td className="px-3 py-2 text-right">
                            {isSwapping ? (
                              <button
                                type="button"
                                onClick={() => setSwappingLineIdx(null)}
                                className="text-gray-400 hover:text-white text-xs"
                              >
                                Cancel
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={() => handleSwapClick(idx)}
                                className="text-amber-400 hover:text-amber-300 text-xs"
                              >
                                Swap
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {Object.keys(overrides).length > 0 && (
                <p className="text-xs text-blue-400 mt-2">
                  {Object.keys(overrides).length} component{Object.keys(overrides).length > 1 ? "s" : ""} will be swapped
                </p>
              )}
            </div>
          )}

          {!loadingBom && bomLines.length === 0 && sourceItem.has_bom && (
            <div className="px-6 pb-4 text-gray-500 text-sm">
              No active BOM found for this item.
            </div>
          )}

          {/* Footer */}
          <div className="flex justify-end gap-3 p-6 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white border border-gray-600 rounded-lg text-sm"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white rounded-lg text-sm font-medium"
            >
              {submitting ? "Duplicating..." : "Duplicate Item"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
