import { useState, useEffect, useCallback } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";

export default function AdminCycleCount() {
  const [inventoryItems, setInventoryItems] = useState([]);
  const [countEntries, setCountEntries] = useState({});
  const [reasonEntries, setReasonEntries] = useState({}); // Per-item reason overrides
  const [defaultReason, setDefaultReason] = useState("Physical count variance");
  const [locations, setLocations] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [results, setResults] = useState(null);
  const [filters, setFilters] = useState({
    location_id: "",
    category_id: "",
    search: "",
    show_zero: false,
  });
  const [countReference, setCountReference] = useState(
    `Cycle Count ${new Date().toISOString().split("T")[0]}`
  );
  const toast = useToast();

  // Common cycle count adjustment reasons (required for accounting audit trail)
  const REASON_OPTIONS = [
    "Physical count variance",
    "Damaged/defective - scrapped",
    "Found in alternate location",
    "Data entry error correction",
    "Theft/loss suspected",
    "Received but not recorded",
    "Shipped but not recorded",
    "Sample/testing usage",
    "Other - see notes",
  ];

  useEffect(() => {
    fetchInventorySummary();
    fetchLocations();
    fetchCategories();
  }, [filters.location_id, filters.category_id, filters.show_zero]);

  const fetchInventorySummary = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.location_id)
        params.append("location_id", filters.location_id);
      if (filters.category_id)
        params.append("category_id", filters.category_id);
      if (filters.search) params.append("search", filters.search);
      params.append("show_zero", filters.show_zero.toString());
      params.append("limit", "500");

      const res = await fetch(
        `${API_URL}/api/v1/admin/inventory/transactions/inventory-summary?${params.toString()}`,
        {
          credentials: "include",
        }
      );

      if (!res.ok) throw new Error("Failed to fetch inventory");
      const data = await res.json();
      setInventoryItems(data.items || []);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchLocations = async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/admin/inventory/transactions/locations`,
        {
          credentials: "include",
        }
      );
      if (res.ok) {
        const data = await res.json();
        setLocations(data);
      }
    } catch {
      // Non-critical
    }
  };

  const fetchCategories = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/items/categories`);
      if (res.ok) {
        const data = await res.json();
        setCategories(data);
      }
    } catch {
      // Non-critical
    }
  };

  const handleCountChange = (productId, value) => {
    setCountEntries((prev) => ({
      ...prev,
      [productId]: value,
    }));
  };

  const handleReasonChange = (productId, value) => {
    setReasonEntries((prev) => ({
      ...prev,
      [productId]: value,
    }));
  };

  const getItemReason = (productId) => {
    return reasonEntries[productId] || defaultReason;
  };

  const handleSearch = useCallback(() => {
    fetchInventorySummary();
  }, [filters.search]);

  const getVariance = (item) => {
    const counted = countEntries[item.product_id];
    if (counted === undefined || counted === "") return null;
    return parseFloat(counted) - item.on_hand_quantity;
  };

  const hasChanges = () => {
    return Object.entries(countEntries).some(([productId, value]) => {
      if (value === "" || value === undefined) return false;
      const item = inventoryItems.find((i) => i.product_id === parseInt(productId));
      if (!item) return false;
      return parseFloat(value) !== item.on_hand_quantity;
    });
  };

  const handleSubmit = async () => {
    // Build items array from entries that have changes
    const items = [];
    for (const [productId, value] of Object.entries(countEntries)) {
      if (value === "" || value === undefined) continue;
      const item = inventoryItems.find((i) => i.product_id === parseInt(productId));
      if (!item) continue;
      if (parseFloat(value) === item.on_hand_quantity) continue;

      // Get reason for this item (required for accounting audit trail)
      const reason = getItemReason(parseInt(productId));

      items.push({
        product_id: parseInt(productId),
        counted_quantity: parseFloat(value),
        reason: reason, // Required field for GL journal entry
      });
    }

    if (items.length === 0) {
      toast.warning("No changes to submit");
      return;
    }

    // Validate all items have reasons
    const missingReason = items.some((i) => !i.reason || i.reason.trim() === "");
    if (missingReason) {
      toast.error("All items must have a reason for accounting compliance");
      return;
    }

    try {
      setSubmitting(true);
      const res = await fetch(
        `${API_URL}/api/v1/admin/inventory/transactions/batch`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            items,
            location_id: filters.location_id
              ? parseInt(filters.location_id)
              : null,
            count_reference: countReference,
          }),
        }
      );

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || "Failed to submit count");
      }

      const data = await res.json();
      setResults(data);
      const message = `Cycle count complete: ${data.successful} items updated, ${data.failed} failed`;
      if (data.failed > 0) {
        toast.warning(message);
      } else {
        toast.success(message);
      }

      // Clear entries and refresh
      setCountEntries({});
      setReasonEntries({});
      fetchInventorySummary();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const clearAllEntries = () => {
    setCountEntries({});
    setReasonEntries({});
    setResults(null);
  };

  const setAllToCurrentQuantity = () => {
    const entries = {};
    inventoryItems.forEach((item) => {
      entries[item.product_id] = item.on_hand_quantity.toString();
    });
    setCountEntries(entries);
  };

  const filteredItems = inventoryItems.filter((item) => {
    if (!filters.search) return true;
    const search = filters.search.toLowerCase();
    return (
      item.product_sku.toLowerCase().includes(search) ||
      item.product_name.toLowerCase().includes(search)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold text-white">Cycle Count</h1>
          <p className="text-gray-400 mt-1">
            Batch update inventory quantities from physical counts
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={clearAllEntries}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Clear All
          </button>
          <button
            onClick={setAllToCurrentQuantity}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Fill Current Qty
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting || !hasChanges()}
            className={`px-4 py-2 rounded-lg font-medium ${
              hasChanges()
                ? "bg-blue-600 text-white hover:bg-blue-700"
                : "bg-gray-700 text-gray-400 cursor-not-allowed"
            }`}
          >
            {submitting ? "Submitting..." : "Submit Count"}
          </button>
        </div>
      </div>

      {/* Count Reference & Default Reason */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-400 whitespace-nowrap">
              Count Reference:
            </label>
            <input
              type="text"
              value={countReference}
              onChange={(e) => setCountReference(e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
              placeholder="e.g., Cycle Count 2025-01-20"
            />
          </div>
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-gray-400 whitespace-nowrap">
              Default Reason:
              <span className="text-red-400 ml-1">*</span>
            </label>
            <select
              value={defaultReason}
              onChange={(e) => setDefaultReason(e.target.value)}
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              {REASON_OPTIONS.map((reason) => (
                <option key={reason} value={reason}>
                  {reason}
                </option>
              ))}
            </select>
          </div>
        </div>
        <p className="text-xs text-gray-500 mt-2">
          * Reason is required for all adjustments (accounting audit trail). Override per-item in the table if needed.
        </p>
      </div>

      {/* Filters */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Location
            </label>
            <select
              value={filters.location_id}
              onChange={(e) =>
                setFilters({ ...filters, location_id: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">All Locations</option>
              {locations.map((loc) => (
                <option key={loc.id} value={loc.id}>
                  {loc.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Category
            </label>
            <select
              value={filters.category_id}
              onChange={(e) =>
                setFilters({ ...filters, category_id: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">All Categories</option>
              {categories.map((cat) => (
                <option key={cat.id} value={cat.id}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>

          <div className="relative z-10">
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Search
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={filters.search}
                onChange={(e) =>
                  setFilters({ ...filters, search: e.target.value })
                }
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                placeholder="SKU or Name"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
              <button
                onClick={handleSearch}
                className="px-3 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 relative z-10"
              >
                Search
              </button>
            </div>
          </div>

          <div className="flex items-end pb-1">
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={filters.show_zero}
                onChange={(e) =>
                  setFilters({ ...filters, show_zero: e.target.checked })
                }
                className="rounded bg-gray-800 border-gray-700 text-blue-600 focus:ring-blue-500"
              />
              Show zero quantity items
            </label>
          </div>
        </div>
      </div>

      {/* Results Summary */}
      {results && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <h3 className="text-lg font-semibold text-white mb-3">
            Last Count Results: {results.count_reference}
          </h3>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="bg-gray-800 rounded-lg p-3">
              <div className="text-2xl font-bold text-white">
                {results.total_items}
              </div>
              <div className="text-sm text-gray-400">Total Items</div>
            </div>
            <div className="bg-green-900/30 rounded-lg p-3">
              <div className="text-2xl font-bold text-green-400">
                {results.successful}
              </div>
              <div className="text-sm text-gray-400">Successful</div>
            </div>
            <div className="bg-red-900/30 rounded-lg p-3">
              <div className="text-2xl font-bold text-red-400">
                {results.failed}
              </div>
              <div className="text-sm text-gray-400">Failed</div>
            </div>
          </div>

          {/* Variance Details */}
          <div className="overflow-x-auto max-h-48">
            <table className="w-full text-sm">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-2 px-3 text-gray-400">SKU</th>
                  <th className="text-left py-2 px-3 text-gray-400">Name</th>
                  <th className="text-right py-2 px-3 text-gray-400">
                    Previous
                  </th>
                  <th className="text-right py-2 px-3 text-gray-400">
                    Counted
                  </th>
                  <th className="text-right py-2 px-3 text-gray-400">
                    Variance
                  </th>
                  <th className="text-center py-2 px-3 text-gray-400">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {results.results
                  .filter((r) => r.variance !== 0 || !r.success)
                  .map((r) => (
                    <tr key={r.product_id} className="border-t border-gray-800">
                      <td className="py-2 px-3 text-white">{r.product_sku}</td>
                      <td className="py-2 px-3 text-gray-400">
                        {r.product_name}
                      </td>
                      <td className="py-2 px-3 text-right text-gray-400">
                        {parseFloat(r.previous_quantity).toLocaleString()}
                      </td>
                      <td className="py-2 px-3 text-right text-white">
                        {parseFloat(r.counted_quantity).toLocaleString()}
                      </td>
                      <td
                        className={`py-2 px-3 text-right font-medium ${
                          r.variance > 0
                            ? "text-green-400"
                            : r.variance < 0
                              ? "text-red-400"
                              : "text-gray-400"
                        }`}
                      >
                        {r.variance > 0 ? "+" : ""}
                        {parseFloat(r.variance).toLocaleString()}
                      </td>
                      <td className="py-2 px-3 text-center">
                        {r.success ? (
                          <span className="text-green-400">OK</span>
                        ) : (
                          <span className="text-red-400" title={r.error}>
                            FAILED
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Inventory Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 flex justify-between items-center">
          <h3 className="text-lg font-semibold text-white">
            Inventory Items ({filteredItems.length})
          </h3>
          <div className="text-sm text-gray-400">
            {Object.keys(countEntries).length} items with entries
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    SKU
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Product Name
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    System Qty
                  </th>
                  <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase w-32">
                    Counted Qty
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Variance
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase w-44">
                    Reason
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((item) => {
                  const variance = getVariance(item);
                  const hasVariance = variance !== null && variance !== 0;

                  return (
                    <tr
                      key={item.product_id}
                      className={`border-b border-gray-800 hover:bg-gray-800/50 ${
                        hasVariance ? "bg-yellow-900/10" : ""
                      }`}
                    >
                      <td className="py-3 px-4">
                        <span className="text-white font-mono text-sm">
                          {item.product_sku}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <div className="text-gray-300 text-sm">{item.product_name}</div>
                        <div className="text-gray-500 text-xs">
                          {item.category_name || "No category"} · {item.unit}
                        </div>
                      </td>
                      <td className="py-3 px-4 text-right text-white">
                        {item.on_hand_quantity.toLocaleString(undefined, {
                          maximumFractionDigits: 2,
                        })}
                      </td>
                      <td className="py-3 px-4">
                        <input
                          type="number"
                          step="0.01"
                          value={countEntries[item.product_id] ?? ""}
                          onChange={(e) =>
                            handleCountChange(item.product_id, e.target.value)
                          }
                          placeholder={item.on_hand_quantity.toString()}
                          className={`w-full bg-gray-800 border rounded-lg px-3 py-1.5 text-white text-right ${
                            hasVariance
                              ? "border-yellow-500"
                              : "border-gray-700"
                          }`}
                        />
                      </td>
                      <td
                        className={`py-3 px-4 text-right font-medium ${
                          variance > 0
                            ? "text-green-400"
                            : variance < 0
                              ? "text-red-400"
                              : "text-gray-500"
                        }`}
                      >
                        {variance !== null ? (
                          <>
                            {variance > 0 ? "+" : ""}
                            {variance.toLocaleString(undefined, {
                              maximumFractionDigits: 2,
                            })}
                          </>
                        ) : (
                          "-"
                        )}
                      </td>
                      <td className="py-3 px-4">
                        {hasVariance ? (
                          <select
                            value={reasonEntries[item.product_id] || ""}
                            onChange={(e) =>
                              handleReasonChange(item.product_id, e.target.value)
                            }
                            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-2 py-1.5 text-white text-xs"
                          >
                            <option value="">Use default</option>
                            {REASON_OPTIONS.map((reason) => (
                              <option key={reason} value={reason}>
                                {reason}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-gray-600 text-xs">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {filteredItems.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-gray-500">
                      No inventory items found
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Help Text */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <h4 className="text-sm font-medium text-gray-300 mb-2">
          How to use Cycle Count:
        </h4>
        <ol className="text-sm text-gray-400 space-y-1 list-decimal list-inside">
          <li>Filter items by location or category to focus your count</li>
          <li>Set a default reason (required for accounting audit trail)</li>
          <li>Enter the physical count quantity for each item</li>
          <li>Items with variances will be highlighted - override reason per item if needed</li>
          <li>Click "Submit Count" to create adjustment transactions + GL journal entries</li>
          <li>Review the results summary to see all changes made</li>
        </ol>
        <p className="text-xs text-gray-500 mt-3">
          Note: All adjustments create GL journal entries (DR/CR Inventory Adjustment expense account 5030).
        </p>
      </div>
    </div>
  );
}
