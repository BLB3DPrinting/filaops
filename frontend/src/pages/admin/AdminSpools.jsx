import { useState, useEffect } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import EmptyState from "../../components/EmptyState";
import { SPOOL_COLORS as statusColors } from "../../lib/statusColors.js";
import { normalizeList } from "../../lib/normalizeList";

export default function AdminSpools() {
  const toast = useToast();
  const api = useApi();
  const [spools, setSpools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ status: "all", search: "" });
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedSpool, setSelectedSpool] = useState(null);
  const [products, setProducts] = useState([]);
  const [locations, setLocations] = useState([]);

  useEffect(() => {
    fetchSpools();
    fetchProducts();
    fetchLocations();
  }, []);

  useEffect(() => {
    fetchSpools();
  }, [filters.status]);

  const fetchSpools = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.status !== "all") params.set("status", filters.status);
      if (filters.search) params.set("search", filters.search);

      const data = await api.get(`/api/v1/spools?${params}`);
      setSpools(normalizeList(data, ["spools"]).items);
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchProducts = async () => {
    try {
      const data = await api.get("/api/v1/products?type=material&limit=200");
      setProducts(normalizeList(data, ["products"]).items);
    } catch (err) {
      console.error("Failed to fetch products:", err);
    }
  };

  const fetchLocations = async () => {
    try {
      const data = await api.get("/api/v1/admin/locations/");
      setLocations(normalizeList(data, ["locations"]).items);
    } catch (err) {
      console.error("Failed to fetch locations:", err);
    }
  };

  const handleDelete = async (spoolId) => {
    if (!confirm("Are you sure you want to delete this spool?")) return;

    try {
      await api.del(`/api/v1/spools/${spoolId}`);
      toast.success("Spool deleted");
      fetchSpools();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const filteredSpools = spools.filter((spool) => {
    if (filters.search) {
      const search = filters.search.toLowerCase();
      return (
        spool.spool_number?.toLowerCase().includes(search) ||
        spool.product_sku?.toLowerCase().includes(search) ||
        spool.product_name?.toLowerCase().includes(search)
      );
    }
    return true;
  });

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Material Spools</h1>
          <p className="text-gray-400 mt-1">Manage filament spools and material tracking</p>
        </div>
        <button
          onClick={() => {
            setSelectedSpool(null);
            setShowAddModal(true);
          }}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
        >
          + Add Spool
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <input
          type="text"
          placeholder="Search spools..."
          value={filters.search}
          onChange={(e) => setFilters({ ...filters, search: e.target.value })}
          className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        />
        <select
          value={filters.status}
          onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="all">All Status</option>
          <option value="active">Active</option>
          <option value="empty">Empty</option>
          <option value="expired">Expired</option>
          <option value="damaged">Damaged</option>
        </select>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="text-center py-12 text-gray-400">Loading spools...</div>
      ) : filteredSpools.length === 0 ? (
        spools.length === 0 ? (
          <EmptyState
            icon="inventory"
            title="No spools yet"
            description="Add your first filament spool to start tracking material inventory."
            actionLabel="Add Spool"
            onAction={() => setShowAddModal(true)}
          />
        ) : (
          <EmptyState
            icon="filter"
            title="No spools match your filters"
            onClearFilters={() => setFilters({ status: "all", search: "" })}
          />
        )
      ) : (
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full min-w-[640px]">
            <thead className="bg-gray-900">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">
                  Spool Number
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">
                  Material
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">
                  Weight
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">
                  Location
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {filteredSpools.map((spool) => {
                const weightRemaining = spool.current_weight_kg || 0;
                const initialWeight = spool.initial_weight_kg || 1;
                const percentRemaining = (weightRemaining / initialWeight) * 100;

                return (
                  <tr key={spool.id} className="hover:bg-gray-700/50">
                    <td className="px-4 py-3 text-white font-medium">
                      {spool.spool_number}
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-white">{spool.product_name || spool.product_sku}</div>
                      <div className="text-xs text-gray-400">{spool.product_sku}</div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="text-white">
                        {weightRemaining.toFixed(1)}g / {initialWeight.toFixed(1)}g
                      </div>
                      <div className="w-24 bg-gray-700 rounded-full h-1.5 mt-1">
                        <div
                          className={`h-1.5 rounded-full ${
                            percentRemaining > 20
                              ? "bg-green-500"
                              : percentRemaining > 10
                              ? "bg-yellow-500"
                              : "bg-red-500"
                          }`}
                          style={{ width: `${Math.min(100, percentRemaining)}%` }}
                        />
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-1 rounded text-xs font-medium ${
                          statusColors[spool.status] || statusColors.active
                        }`}
                      >
                        {spool.status || "active"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-sm">
                      {spool.location_name || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <button
                          onClick={() => {
                            setSelectedSpool(spool);
                            setShowAddModal(true);
                          }}
                          className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(spool.id)}
                          className="px-2 py-1 bg-red-600 hover:bg-red-700 text-white text-xs rounded"
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {/* Add/Edit Modal */}
      {showAddModal && (
        <SpoolModal
          spool={selectedSpool}
          products={products}
          locations={locations}
          onClose={() => {
            setShowAddModal(false);
            setSelectedSpool(null);
          }}
          onSave={() => {
            fetchSpools();
            setShowAddModal(false);
            setSelectedSpool(null);
          }}
        />
      )}
    </div>
  );
}

function SpoolModal({ spool, products, locations, onClose, onSave }) {
  const toast = useToast();
  const api = useApi();
  const [form, setForm] = useState({
    spool_number: spool?.spool_number || "",
    product_id: spool?.product_id ?? null,
    initial_weight_kg: spool?.initial_weight_kg || "",
    current_weight_kg: spool?.current_weight_kg || spool?.initial_weight_kg || "",
    status: spool?.status || "active",
    location_id: spool?.location_id ?? null,
    supplier_lot_number: spool?.supplier_lot_number || "",
    expiry_date: spool?.expiry_date ? spool.expiry_date.split("T")[0] : "",
    notes: spool?.notes || "",
  });
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      if (spool) {
        // EDIT — JSON body with exclude_unset semantics on the backend:
        // omit a field to leave it unchanged; send location_id/notes as null
        // to clear them. Picking "No location" must reach the backend as an
        // explicit null, not be silently dropped (Copilot PR #603 finding).
        const body = {};

        // Weight: the form initializes current_weight_kg from the spool, so
        // it's always populated. Only send current_weight_g when the user
        // has actually edited it — otherwise every PATCH would trigger the
        // backend's weight-adjustment branch, which requires a `reason` this
        // modal doesn't collect (the 400 then blocks status/location/notes
        // edits entirely). The dedicated weight-adjustment flow lives
        // elsewhere; we surface a clear error if the user tries to use this
        // form for it (CodeRabbit PR #603 finding).
        const originalWeight = Number(
          spool.current_weight_kg ?? spool.initial_weight_kg ?? 0
        );
        const editedWeight = Number(form.current_weight_kg);
        if (editedWeight !== originalWeight) {
          throw new Error(
            "Weight updates require a reason and aren't supported from this modal yet. Use the inventory adjustment flow."
          );
        }

        if (form.status) body.status = form.status;
        // Always send location_id, even when null, so "No location" clears.
        body.location_id = form.location_id;
        // Always send notes so the user can clear them by emptying the field.
        body.notes = form.notes || null;
        await api.patch(`/api/v1/spools/${spool.id}`, body);
      } else {
        // CREATE — full body. Optional fields included only when set.
        const body = {
          spool_number: form.spool_number,
          product_id: form.product_id,
          initial_weight_kg: parseFloat(form.initial_weight_kg),
        };
        if (form.current_weight_kg) {
          body.current_weight_kg = parseFloat(form.current_weight_kg);
        }
        if (form.location_id !== null) body.location_id = form.location_id;
        if (form.supplier_lot_number) body.supplier_lot_number = form.supplier_lot_number;
        if (form.expiry_date) body.expiry_date = form.expiry_date;
        if (form.notes) body.notes = form.notes;
        await api.post("/api/v1/spools/", body);
      }

      toast.success(spool ? "Spool updated" : "Spool created");
      onSave();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-auto bg-black/60 flex items-center justify-center p-4">
      <div className="bg-gray-800 rounded-lg max-w-2xl w-full mx-4 p-6">
        <h2 className="text-xl font-bold text-white mb-4">
          {spool ? "Edit Spool" : "Add Spool"}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">Spool Number *</label>
            <input
              type="text"
              required
              value={form.spool_number}
              onChange={(e) => setForm({ ...form, spool_number: e.target.value })}
              disabled={!!spool}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Material *</label>
            <select
              required
              value={form.product_id ?? ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  product_id: e.target.value ? parseInt(e.target.value, 10) : null,
                })
              }
              disabled={!!spool}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white disabled:opacity-50"
            >
              <option value="">Select material...</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} - {p.name}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Initial Weight (g) *</label>
              <input
                type="number"
                step="0.1"
                required
                value={form.initial_weight_kg}
                onChange={(e) => setForm({ ...form, initial_weight_kg: e.target.value })}
                disabled={!!spool}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white disabled:opacity-50"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Current Weight (g) *</label>
              <input
                type="number"
                step="0.1"
                required
                value={form.current_weight_kg}
                onChange={(e) => setForm({ ...form, current_weight_kg: e.target.value })}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Status</label>
              <select
                value={form.status}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              >
                <option value="active">Active</option>
                <option value="empty">Empty</option>
                <option value="expired">Expired</option>
                <option value="damaged">Damaged</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Location</label>
              <select
                value={form.location_id ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    location_id: e.target.value ? parseInt(e.target.value, 10) : null,
                  })
                }
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
              >
                <option value="">No location</option>
                {locations.map((loc) => (
                  <option key={loc.id} value={loc.id}>
                    {loc.code} - {loc.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Supplier Lot Number</label>
            <input
              type="text"
              value={form.supplier_lot_number}
              onChange={(e) => setForm({ ...form, supplier_lot_number: e.target.value })}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Expiry Date</label>
            <input
              type="date"
              value={form.expiry_date}
              onChange={(e) => setForm({ ...form, expiry_date: e.target.value })}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
            />
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              rows={3}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white"
            />
          </div>

          <div className="flex gap-3 pt-4">
            <button
              type="submit"
              disabled={saving}
              className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
            >
              {saving ? "Saving..." : spool ? "Update" : "Create"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
