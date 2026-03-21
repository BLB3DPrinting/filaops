/**
 * SuggestPricesModal — Calculate and bulk-apply selling prices at a target margin.
 *
 * Fetches candidate items from the server, then does margin math client-side
 * for instant slider feedback. Only the apply step hits the server.
 */
import { useState, useEffect, useMemo, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../Toast";
import { useFormatCurrency } from "../../hooks/useFormatCurrency";

export default function SuggestPricesModal({
  isOpen,
  onClose,
  onSuccess,
  selectedCategory,
  filters,
}) {
  const api = useApi();
  const toast = useToast();
  const formatCurrency = useFormatCurrency();

  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [marginPercent, setMarginPercent] = useState(71.43);
  const [selectedIds, setSelectedIds] = useState(new Set());

  // Fetch settings + candidates when modal opens
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;

    const fetchData = async () => {
      setLoading(true);
      try {
        // Fetch default margin from settings
        const settings = await api.get("/api/v1/settings/company");
        if (cancelled) return;
        if (settings.default_margin_percent != null) {
          setMarginPercent(settings.default_margin_percent);
        }

        // Fetch eligible items
        const params = new URLSearchParams();
        if (selectedCategory) params.set("category_id", selectedCategory.toString());
        if (filters?.itemType && filters.itemType !== "all") {
          params.set("item_type", filters.itemType);
        }
        const qs = params.toString();
        const items = await api.get(`/api/v1/items/price-candidates${qs ? `?${qs}` : ""}`);
        if (cancelled) return;
        setCandidates(items);
        // Default: select all items
        setSelectedIds(new Set(items.map((i) => i.id)));
      } catch (err) {
        if (!cancelled) toast.error(err.message || "Failed to load price candidates");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchData();
    return () => { cancelled = true; };
  }, [isOpen, selectedCategory, filters, api, toast]);

  // Client-side margin calculation
  const calculatedItems = useMemo(() => {
    if (marginPercent >= 100 || marginPercent < 0) return [];
    return candidates.map((c) => {
      const suggested = c.standard_cost / (1 - marginPercent / 100);
      const current = c.current_selling_price || 0;
      const diff = suggested - current;
      return { ...c, suggested_price: suggested, diff };
    });
  }, [candidates, marginPercent]);

  const selectedCount = calculatedItems.filter((c) => selectedIds.has(c.id)).length;
  const changedItems = calculatedItems.filter(
    (c) => Math.abs(c.diff) > 0.01
  );

  const toggleItem = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIds.size === calculatedItems.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(calculatedItems.map((c) => c.id)));
    }
  }, [calculatedItems, selectedIds.size]);

  const selectAllChanged = useCallback(() => {
    setSelectedIds(new Set(changedItems.map((c) => c.id)));
  }, [changedItems]);

  const handleApply = async () => {
    const itemsToApply = calculatedItems
      .filter((c) => selectedIds.has(c.id))
      .map((c) => ({
        id: c.id,
        selling_price: c.suggested_price.toFixed(4),
      }));

    if (itemsToApply.length === 0) return;

    setApplying(true);
    try {
      const result = await api.post("/api/v1/items/apply-suggested-prices", {
        items: itemsToApply,
      });
      toast.success(`Updated prices for ${result.updated} items`);
      onSuccess(result);
    } catch (err) {
      toast.error(err.message || "Failed to apply prices");
    } finally {
      setApplying(false);
    }
  };

  if (!isOpen) return null;

  const multiplier = marginPercent < 100 ? (1 / (1 - marginPercent / 100)).toFixed(3) : "---";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-gray-900 border border-gray-700 rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-white">Suggest Prices</h2>
            <p className="text-sm text-gray-400 mt-1">
              Calculate selling prices from cost at a target margin
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        {/* Margin Control */}
        <div className="p-6 border-b border-gray-700 bg-gray-800/50">
          <div className="flex items-center gap-6">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Target Margin
              </label>
              <input
                type="range"
                min="10"
                max="95"
                step="0.5"
                value={marginPercent}
                onChange={(e) => setMarginPercent(parseFloat(e.target.value))}
                className="w-full accent-purple-500"
              />
            </div>
            <div className="w-24">
              <input
                type="number"
                min="0"
                max="99.99"
                step="0.01"
                value={marginPercent}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  if (!isNaN(val) && val >= 0 && val < 100) setMarginPercent(val);
                }}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-center"
              />
              <span className="text-xs text-gray-400 block text-center mt-1">%</span>
            </div>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            cost / (1 - {marginPercent}%) = cost &times; {multiplier}
          </p>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="text-center text-gray-400 py-12">Loading candidates...</div>
          ) : calculatedItems.length === 0 ? (
            <div className="text-center text-gray-400 py-12">
              No eligible items with costs found.
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-gray-400">
                  {calculatedItems.length} items &middot; {selectedCount} selected
                </span>
                <button
                  type="button"
                  onClick={selectAllChanged}
                  className="text-sm text-purple-400 hover:text-purple-300"
                >
                  Select All Changed ({changedItems.length})
                </button>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-400 border-b border-gray-700">
                    <th className="pb-2 pr-2 w-8">
                      <input
                        type="checkbox"
                        checked={selectedIds.size === calculatedItems.length}
                        onChange={toggleAll}
                        className="accent-purple-500"
                        aria-label="Select all items"
                      />
                    </th>
                    <th className="pb-2 pr-4">SKU</th>
                    <th className="pb-2 pr-4">Name</th>
                    <th className="pb-2 pr-4 text-right">Cost</th>
                    <th className="pb-2 pr-4 text-right">Current</th>
                    <th className="pb-2 pr-4 text-right">Suggested</th>
                    <th className="pb-2 text-right">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {calculatedItems.map((item) => {
                    const isIncrease = item.diff > 0.01;
                    const isDecrease = item.diff < -0.01;
                    const rowBg = isIncrease
                      ? "bg-green-500/5"
                      : isDecrease
                        ? "bg-amber-500/5"
                        : "";

                    return (
                      <tr
                        key={item.id}
                        className={`border-b border-gray-800 ${rowBg}`}
                      >
                        <td className="py-2 pr-2">
                          <input
                            type="checkbox"
                            checked={selectedIds.has(item.id)}
                            onChange={() => toggleItem(item.id)}
                            className="accent-purple-500"
                            aria-label={`Select ${item.sku}`}
                          />
                        </td>
                        <td className="py-2 pr-4 font-mono text-gray-300">
                          {item.sku}
                        </td>
                        <td className="py-2 pr-4 text-gray-300 truncate max-w-[200px]">
                          {item.name}
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-400">
                          {formatCurrency(item.standard_cost)}
                        </td>
                        <td className="py-2 pr-4 text-right text-gray-400">
                          {item.current_selling_price != null
                            ? formatCurrency(item.current_selling_price)
                            : "---"}
                        </td>
                        <td className="py-2 pr-4 text-right text-white font-medium">
                          {formatCurrency(item.suggested_price)}
                        </td>
                        <td className="py-2 text-right">
                          {isIncrease && (
                            <span className="text-green-400">
                              +{formatCurrency(item.diff)}
                            </span>
                          )}
                          {isDecrease && (
                            <span className="text-amber-400">
                              {formatCurrency(item.diff)}
                            </span>
                          )}
                          {!isIncrease && !isDecrease && (
                            <span className="text-gray-600">---</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 p-6 border-t border-gray-700">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApply}
            disabled={applying || selectedCount === 0}
            className="px-6 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {applying
              ? "Applying..."
              : `Apply to ${selectedCount} Item${selectedCount !== 1 ? "s" : ""}`}
          </button>
        </div>
      </div>
    </div>
  );
}
