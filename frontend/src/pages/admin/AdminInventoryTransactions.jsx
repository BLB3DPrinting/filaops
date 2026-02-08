import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../hooks/useApi";

export default function AdminInventoryTransactions() {
  const api = useApi();
  const [transactions, setTransactions] = useState([]);
  const [products, setProducts] = useState([]);
  const [locations, setLocations] = useState([]);
  const [adjustmentReasons, setAdjustmentReasons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [formData, setFormData] = useState({
    product_id: "",
    location_id: "",
    transaction_type: "receipt",
    quantity: "",
    cost_per_unit: "",
    reference_type: "",
    reference_id: "",
    lot_number: "",
    serial_number: "",
    notes: "",
    to_location_id: "",
    reason_code: "",
  });
  const [filters, setFilters] = useState({
    product_id: "",
    transaction_type: "",
    location_id: "",
  });

  useEffect(() => {
    fetchTransactions();
    fetchProducts();
    fetchLocations();
  }, [filters]);

  // Fetch adjustment reasons for dropdown
  useEffect(() => {
    api.get("/api/v1/admin/inventory/transactions/adjustment-reasons")
      .then(data => setAdjustmentReasons(data))
      .catch(() => {}); // Non-critical, will fallback to empty dropdown
  }, []);

  const fetchTransactions = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filters.product_id) params.append("product_id", filters.product_id);
      if (filters.transaction_type)
        params.append("transaction_type", filters.transaction_type);
      if (filters.location_id)
        params.append("location_id", filters.location_id);

      const data = await api.get(`/api/v1/admin/inventory/transactions?${params.toString()}`);
      setTransactions(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const data = await api.get(`/api/v1/items?limit=2000`);
      setProducts(data.items || []);
    } catch {
      // Non-critical: Products fetch failure - dropdown will be empty but page still works
    }
  };

  const fetchLocations = async () => {
    try {
      const data = await api.get(`/api/v1/admin/inventory/transactions/locations`);
      setLocations(data);
    } catch {
      // Locations fetch failure is non-critical - location selector will be empty
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const payload = {
        ...formData,
        product_id: parseInt(formData.product_id),
        location_id: formData.location_id
          ? parseInt(formData.location_id)
          : null,
        quantity: parseFloat(formData.quantity),
        cost_per_unit: formData.cost_per_unit
          ? parseFloat(formData.cost_per_unit)
          : null,
        reference_id: formData.reference_id
          ? parseInt(formData.reference_id)
          : null,
        to_location_id:
          formData.transaction_type === "transfer" && formData.to_location_id
            ? parseInt(formData.to_location_id)
            : null,
        ...(formData.reason_code && { reason_code: formData.reason_code }),
      };

      await api.post(`/api/v1/admin/inventory/transactions`, payload);

      // Reset form and refresh
      setFormData({
        product_id: "",
        location_id: "",
        transaction_type: "receipt",
        quantity: "",
        cost_per_unit: "",
        reference_type: "",
        reference_id: "",
        lot_number: "",
        serial_number: "",
        notes: "",
        to_location_id: "",
        reason_code: "",
      });
      setShowForm(false);
      fetchTransactions();
    } catch (err) {
      setError(err.message);
    }
  };

  const getTransactionTypeColor = (type) => {
    const colors = {
      receipt: "bg-green-500/20 text-green-400",
      issue: "bg-red-500/20 text-red-400",
      transfer: "bg-blue-500/20 text-blue-400",
      adjustment: "bg-yellow-500/20 text-yellow-400",
      consumption: "bg-orange-500/20 text-orange-400",
      scrap: "bg-gray-500/20 text-gray-400",
    };
    return colors[type] || "bg-gray-500/20 text-gray-400";
  };

  if (loading && transactions.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Inventory Transactions
          </h1>
          <p className="text-gray-400 mt-1">
            Manage receipts, issues, transfers, and adjustments
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          {showForm ? "Cancel" : "+ New Transaction"}
        </button>
      </div>

      {/* Error Message */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Transaction Form */}
      {showForm && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">
            Create Transaction
          </h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Product *
                </label>
                <select
                  required
                  value={formData.product_id}
                  onChange={(e) =>
                    setFormData({ ...formData, product_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">Select product</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} - {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Transaction Type *
                </label>
                <select
                  required
                  value={formData.transaction_type}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      transaction_type: e.target.value,
                    })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="receipt">Receipt</option>
                  <option value="issue">Issue</option>
                  <option value="transfer">Transfer</option>
                  <option value="adjustment">Adjustment</option>
                  <option value="consumption">Consumption</option>
                  <option value="scrap">Scrap</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Location
                </label>
                <select
                  value={formData.location_id}
                  onChange={(e) =>
                    setFormData({ ...formData, location_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">Default (Main Warehouse)</option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name} ({loc.code})
                    </option>
                  ))}
                </select>
              </div>

              {formData.transaction_type === "transfer" && (
                <div>
                  <label className="block text-sm font-medium text-gray-400 mb-1">
                    To Location *
                  </label>
                  <select
                    required={formData.transaction_type === "transfer"}
                    value={formData.to_location_id}
                    onChange={(e) =>
                      setFormData({
                        ...formData,
                        to_location_id: e.target.value,
                      })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  >
                    <option value="">Select destination</option>
                    {locations.map((loc) => (
                      <option key={loc.id} value={loc.id}>
                        {loc.name} ({loc.code})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Quantity *
                </label>
                <input
                  type="number"
                  step="0.01"
                  required
                  value={formData.quantity}
                  onChange={(e) =>
                    setFormData({ ...formData, quantity: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Cost per Unit
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={formData.cost_per_unit}
                  onChange={(e) =>
                    setFormData({ ...formData, cost_per_unit: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Reference Type
                </label>
                <select
                  value={formData.reference_type}
                  onChange={(e) =>
                    setFormData({ ...formData, reference_type: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">None</option>
                  <option value="purchase_order">Purchase Order</option>
                  <option value="production_order">Production Order</option>
                  <option value="sales_order">Sales Order</option>
                  <option value="adjustment">Adjustment</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Reference ID
                </label>
                <input
                  type="number"
                  value={formData.reference_id}
                  onChange={(e) =>
                    setFormData({ ...formData, reference_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Lot Number
                </label>
                <input
                  type="text"
                  value={formData.lot_number}
                  onChange={(e) =>
                    setFormData({ ...formData, lot_number: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Serial Number
                </label>
                <input
                  type="text"
                  value={formData.serial_number}
                  onChange={(e) =>
                    setFormData({ ...formData, serial_number: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                Notes
              </label>
              <textarea
                value={formData.notes}
                onChange={(e) =>
                  setFormData({ ...formData, notes: e.target.value })
                }
                rows={3}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
            </div>

            {formData.transaction_type === "adjustment" && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Adjustment Reason
                </label>
                <select
                  value={formData.reason_code}
                  onChange={(e) =>
                    setFormData({ ...formData, reason_code: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="">Select reason...</option>
                  {adjustmentReasons.map((r) => (
                    <option key={r.code} value={r.code}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex gap-4">
              <button
                type="submit"
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Create Transaction
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filters */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Product
            </label>
            <select
              value={filters.product_id}
              onChange={(e) =>
                setFilters({ ...filters, product_id: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">All Products</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} - {p.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">
              Type
            </label>
            <select
              value={filters.transaction_type}
              onChange={(e) =>
                setFilters({ ...filters, transaction_type: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">All Types</option>
              <option value="receipt">Receipt</option>
              <option value="issue">Issue</option>
              <option value="transfer">Transfer</option>
              <option value="adjustment">Adjustment</option>
              <option value="consumption">Consumption</option>
              <option value="scrap">Scrap</option>
            </select>
          </div>

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
        </div>
      </div>

      {/* Transactions Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Date
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Product
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Type
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Quantity
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Location
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Reference
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Cost/Unit
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Total Cost
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Unit
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Notes
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Reason
                </th>
              </tr>
            </thead>
            <tbody>
              {transactions.length > 0 ? (
                transactions.map((txn) => (
                  <tr
                    key={txn.id}
                    className="border-b border-gray-800 hover:bg-gray-800/50"
                  >
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {new Date(txn.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3 px-4">
                      <div className="text-white font-medium">
                        {txn.product_sku}
                      </div>
                      <div className="text-gray-500 text-xs">
                        {txn.product_name}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-1 rounded-full text-xs ${getTransactionTypeColor(
                          txn.transaction_type
                        )}`}
                      >
                        {txn.transaction_type}
                      </span>
                      {txn.to_location_name && (
                        <div className="text-gray-500 text-xs mt-1">
                          → {txn.to_location_name}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-white">
                      {/* SINGLE SOURCE OF TRUTH: Display stored quantity and unit directly */}
                      {parseFloat(txn.quantity).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                      {txn.unit && (
                        <span className="text-gray-500 text-xs ml-1">{txn.unit}</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {txn.location_name || "N/A"}
                    </td>
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {txn.reference_type && txn.reference_id
                        ? `${txn.reference_type} #${txn.reference_id}`
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-400">
                      {/* SINGLE SOURCE OF TRUTH: Display stored cost_per_unit with unit */}
                      {txn.cost_per_unit
                        ? "$" + parseFloat(txn.cost_per_unit).toFixed(4) + "/" + (txn.unit || "EA")
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-white font-medium">
                      {/* SINGLE SOURCE OF TRUTH: Display stored total_cost directly - NO client-side math */}
                      {txn.total_cost != null
                        ? "$" + parseFloat(txn.total_cost).toFixed(2)
                        : "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-xs">
                      {/* SINGLE SOURCE OF TRUTH: Display stored unit directly */}
                      {txn.unit || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-sm max-w-xs truncate">
                      {txn.notes || "-"}
                    </td>
                    <td className="py-3 px-4 text-gray-500 text-sm">
                      {txn.reason_code || "-"}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={11} className="py-8 text-center text-gray-500">
                    No transactions found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
