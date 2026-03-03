import { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import Modal from "../../components/Modal";
import ProGate from "../../components/ProGate";

const EMPTY_FORM = {
  code: "",
  name: "",
  discount_percent: "",
  is_active: true,
  notes: "",
};

export default function AdminPriceLevels() {
  return (
    <ProGate
      feature="Price Levels"
      description="Create wholesale pricing tiers and assign customers to get custom discount rates."
      benefits={[
        "Tiered pricing by customer account level",
        "Assign customers to specific pricing tiers",
        "Per-level discount percentages",
        "Bulk pricing management",
      ]}
    >
      <PriceLevelsContent />
    </ProGate>
  );
}

function PriceLevelsContent() {
  const toast = useToast();
  const api = useApi();

  const [priceLevels, setPriceLevels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [selectedLevel, setSelectedLevel] = useState(null);
  const [availableCustomers, setAvailableCustomers] = useState([]);
  const [loadingCustomers, setLoadingCustomers] = useState(false);
  const [assigningCustomer, setAssigningCustomer] = useState(false);
  const [selectedCustomerId, setSelectedCustomerId] = useState("");

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingLevel, setEditingLevel] = useState(null);
  const [saving, setSaving] = useState(false);

  const fetchPriceLevels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get("/api/v1/pro/catalogs/price-levels");
      setPriceLevels(Array.isArray(data) ? data : []);
      // Refresh the selected level with updated data
      setSelectedLevel((prev) => {
        if (!prev) return null;
        const updated = (Array.isArray(data) ? data : []).find(
          (l) => l.id === prev.id
        );
        return updated || null;
      });
    } catch (err) {
      setError(err.message || "Failed to load price levels");
    } finally {
      setLoading(false);
    }
  }, [api]);

  const fetchAvailableCustomers = useCallback(async () => {
    setLoadingCustomers(true);
    try {
      const data = await api.get("/api/v1/pro/catalogs/available-customers");
      setAvailableCustomers(Array.isArray(data) ? data : []);
    } catch (err) {
      toast.error(err.message || "Failed to load customers");
    } finally {
      setLoadingCustomers(false);
    }
  }, [api, toast]);

  useEffect(() => {
    fetchPriceLevels();
  }, [fetchPriceLevels]);

  useEffect(() => {
    if (selectedLevel) {
      fetchAvailableCustomers();
      setSelectedCustomerId("");
    }
  }, [selectedLevel?.id, fetchAvailableCustomers]);

  const handleRowClick = (level) => {
    if (selectedLevel?.id === level.id) {
      setSelectedLevel(null);
    } else {
      setSelectedLevel(level);
    }
  };

  const handleOpenCreate = () => {
    setEditingLevel(null);
    setShowModal(true);
  };

  const handleOpenEdit = (e, level) => {
    e.stopPropagation();
    setEditingLevel(level);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditingLevel(null);
  };

  const handleSave = async (formData) => {
    setSaving(true);
    try {
      if (editingLevel) {
        await api.patch(
          `/api/v1/pro/catalogs/price-levels/${editingLevel.id}`,
          formData
        );
        toast.success("Price level updated");
      } else {
        await api.post("/api/v1/pro/catalogs/price-levels", formData);
        toast.success("Price level created");
      }
      handleCloseModal();
      await fetchPriceLevels();
    } catch (err) {
      toast.error(err.message || "Failed to save price level");
    } finally {
      setSaving(false);
    }
  };

  const handleAssignCustomer = async () => {
    if (!selectedCustomerId || !selectedLevel) return;
    setAssigningCustomer(true);
    try {
      await api.post(
        `/api/v1/pro/catalogs/price-levels/${selectedLevel.id}/assign`,
        { customer_id: Number(selectedCustomerId) }
      );
      toast.success("Customer assigned");
      setSelectedCustomerId("");
      await fetchPriceLevels();
      await fetchAvailableCustomers();
    } catch (err) {
      toast.error(err.message || "Failed to assign customer");
    } finally {
      setAssigningCustomer(false);
    }
  };

  const handleRemoveCustomer = async (customerId) => {
    if (!selectedLevel) return;
    try {
      await api.del(
        `/api/v1/pro/catalogs/price-levels/${selectedLevel.id}/customers/${customerId}`
      );
      toast.success("Customer removed");
      await fetchPriceLevels();
      await fetchAvailableCustomers();
    } catch (err) {
      toast.error(err.message || "Failed to remove customer");
    }
  };

  // Customers already assigned to the selected level
  const assignedCustomers = selectedLevel?.customers ?? [];

  // Filter available customers to exclude already-assigned ones
  const assignableCustomers = availableCustomers.filter(
    (c) => !assignedCustomers.some((a) => a.id === c.id)
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Price Levels</h1>
          <p className="text-gray-400 mt-1">
            Manage wholesale pricing tiers and customer assignments
          </p>
        </div>
        <button
          onClick={handleOpenCreate}
          className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
        >
          + New Price Level
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Price Levels Table */}
      {!loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px]">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Code
                  </th>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Name
                  </th>
                  <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Discount %
                  </th>
                  <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Active
                  </th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {priceLevels.map((level) => (
                  <tr
                    key={level.id}
                    onClick={() => handleRowClick(level)}
                    className={`border-b border-gray-800 cursor-pointer transition-colors ${
                      selectedLevel?.id === level.id
                        ? "bg-blue-600/10 border-l-2 border-l-blue-500"
                        : "hover:bg-gray-800/50"
                    } ${!level.is_active ? "opacity-60" : ""}`}
                  >
                    <td className="py-3 px-4">
                      <span className="font-mono text-sm text-blue-300">
                        {level.code}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-white">{level.name}</td>
                    <td className="py-3 px-4 text-center text-gray-300">
                      {Number(level.discount_percent).toFixed(2)}%
                    </td>
                    <td className="py-3 px-4 text-center">
                      {level.is_active ? (
                        <span className="px-2 py-1 rounded-full text-xs bg-green-500/20 text-green-400">
                          Active
                        </span>
                      ) : (
                        <span className="px-2 py-1 rounded-full text-xs bg-gray-500/20 text-gray-400">
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={(e) => handleOpenEdit(e, level)}
                        className="text-blue-400 hover:text-blue-300 text-sm"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))}
                {priceLevels.length === 0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="py-12 text-center text-gray-500"
                    >
                      No price levels yet. Click "+ New Price Level" to create
                      one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Customer Selection Panel */}
      {selectedLevel && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">
              Customers &mdash; {selectedLevel.name}
            </h2>
            <button
              onClick={() => setSelectedLevel(null)}
              className="text-gray-500 hover:text-gray-300 text-sm"
            >
              Close
            </button>
          </div>

          {/* Assign Customer Row */}
          <div className="flex flex-col sm:flex-row gap-3">
            {loadingCustomers ? (
              <div className="flex items-center gap-2 text-gray-400 text-sm">
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                Loading customers…
              </div>
            ) : (
              <>
                <select
                  value={selectedCustomerId}
                  onChange={(e) => setSelectedCustomerId(e.target.value)}
                  className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
                >
                  <option value="">Select a customer to assign…</option>
                  {assignableCustomers.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name || c.company_name || `Customer #${c.id}`}
                    </option>
                  ))}
                </select>
                <button
                  onClick={handleAssignCustomer}
                  disabled={!selectedCustomerId || assigningCustomer}
                  className="w-full sm:w-auto px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm whitespace-nowrap"
                >
                  {assigningCustomer ? "Assigning…" : "Assign Customer"}
                </button>
              </>
            )}
          </div>

          {/* Assigned Customers List */}
          {assignedCustomers.length === 0 ? (
            <p className="text-gray-500 text-sm italic">
              No customers assigned to this price level yet.
            </p>
          ) : (
            <ul className="divide-y divide-gray-800">
              {assignedCustomers.map((customer) => (
                <li
                  key={customer.id}
                  className="flex items-center justify-between py-2"
                >
                  <span className="text-gray-300 text-sm">
                    {customer.name ||
                      customer.company_name ||
                      `Customer #${customer.id}`}
                  </span>
                  <button
                    onClick={() => handleRemoveCustomer(customer.id)}
                    className="text-red-400 hover:text-red-300 text-sm ml-4"
                    title="Remove customer from this price level"
                  >
                    &times;
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <PriceLevelModal
          level={editingLevel}
          onSave={handleSave}
          onClose={handleCloseModal}
          saving={saving}
        />
      )}
    </div>
  );
}

function PriceLevelModal({ level, onSave, onClose, saving }) {
  const [form, setForm] = useState(
    level
      ? {
          code: level.code ?? "",
          name: level.name ?? "",
          discount_percent: level.discount_percent ?? "",
          is_active: level.is_active ?? true,
          notes: level.notes ?? "",
        }
      : { ...EMPTY_FORM }
  );

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave({
      ...form,
      discount_percent: Number(form.discount_percent),
    });
  };

  const handleCodeChange = (e) => {
    setForm({ ...form, code: e.target.value.toUpperCase() });
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={level ? "Edit Price Level" : "New Price Level"}
      disableClose={saving}
    >
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-xl font-bold text-white">
          {level ? "Edit Price Level" : "New Price Level"}
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        {/* Code */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">Code *</label>
          <input
            type="text"
            value={form.code}
            onChange={handleCodeChange}
            required
            placeholder="e.g. TIER-A"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 font-mono"
          />
        </div>

        {/* Name */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">Name *</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
            placeholder="e.g. Tier A Partner"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>

        {/* Discount % */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Discount % *
          </label>
          <input
            type="number"
            value={form.discount_percent}
            onChange={(e) =>
              setForm({ ...form, discount_percent: e.target.value })
            }
            required
            min={0}
            max={100}
            step={0.01}
            placeholder="0.00"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>

        {/* Is Active */}
        <div>
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) =>
                setForm({ ...form, is_active: e.target.checked })
              }
              className="rounded bg-gray-800 border-gray-700 w-4 h-4"
            />
            <span className="text-sm text-gray-300">Active</span>
          </label>
        </div>

        {/* Notes */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Notes{" "}
            <span className="text-gray-600 font-normal">(optional)</span>
          </label>
          <textarea
            value={form.notes}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
            rows={3}
            placeholder="Internal notes about this pricing tier…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 resize-none"
          />
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-4 pt-4 border-t border-gray-800">
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="px-4 py-2 text-gray-400 hover:text-white disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving
              ? "Saving…"
              : level
              ? "Save Changes"
              : "Create Price Level"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
