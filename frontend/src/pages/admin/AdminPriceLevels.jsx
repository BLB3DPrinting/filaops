import { useState, useEffect, useRef, useMemo } from "react";
import { useApi } from "../../hooks/useApi";
import { useCRUD } from "../../hooks/useCRUD";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

export default function AdminPriceLevels() {
  const toast = useToast();
  const api = useApi();
  const { isPro } = useFeatureFlags();

  const {
    items: priceLevels,
    loading,
    error,
    refresh,
  } = useCRUD("/api/v1/price-levels", {
    extractKey: null,
    immediate: true,
  });

  const [showModal, setShowModal] = useState(false);
  const [editingLevel, setEditingLevel] = useState(null);
  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assigningLevel, setAssigningLevel] = useState(null);

  // -- Loading / Error states --
  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Price Levels</h1>
        </div>
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
          {error}
        </div>
      </div>
    );
  }

  // -- Handlers --
  const handleSave = async (formData) => {
    try {
      if (editingLevel) {
        await api.patch(`/api/v1/price-levels/${editingLevel.id}`, formData);
        toast.success("Price level updated");
      } else {
        await api.post("/api/v1/price-levels", formData);
        toast.success("Price level created");
      }
      setShowModal(false);
      setEditingLevel(null);
      await refresh();
    } catch (err) {
      toast.error(err.message);
      throw err;
    }
  };

  // Assignment handlers use PRO routes — PRO manages pro_customer_price_levels
  const handleAssign = async (customerId) => {
    try {
      await api.post(
        `/api/v1/pro/catalogs/price-levels/${assigningLevel.id}/assign`,
        { customer_id: customerId }
      );
      toast.success("Customer assigned to price level");
      const data = await refresh();
      if (assigningLevel && Array.isArray(data)) {
        const fresh = data.find((l) => l.id === assigningLevel.id);
        if (fresh) setAssigningLevel(fresh);
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleUnassign = async (levelId, customerId) => {
    try {
      await api.del(
        `/api/v1/pro/catalogs/price-levels/${levelId}/customers/${customerId}`
      );
      toast.success("Customer removed from price level");
      const data = await refresh();
      if (assigningLevel && Array.isArray(data)) {
        const fresh = data.find((l) => l.id === assigningLevel.id);
        if (fresh) setAssigningLevel(fresh);
      }
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Price Levels</h1>
          <p className="text-gray-400 mt-1">
            Wholesale pricing tiers for your customers
          </p>
        </div>
        <button
          onClick={() => {
            setEditingLevel(null);
            setShowModal(true);
          }}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Price Level
        </button>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <div className="flex gap-3">
          <svg className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-blue-400 text-sm">
            Price levels define discount tiers for your customers.
            {isPro
              ? " Assign customers to a level and they'll automatically see discounted prices on the B2B portal."
              : " Customer assignment to price levels is available with FilaOps PRO."}
          </p>
        </div>
      </div>

      {/* Price Levels Table */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px]">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Discount
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Status
                </th>
                {isPro && (
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-400 uppercase tracking-wider">
                    Customers
                  </th>
                )}
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-400 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {!priceLevels || priceLevels.length === 0 ? (
                <tr>
                  <td colSpan={isPro ? 5 : 4} className="px-4 py-8 text-center text-gray-500">
                    No price levels yet. Click "Add Price Level" to create your first tier.
                  </td>
                </tr>
              ) : (
                priceLevels.map((level) => (
                  <tr
                    key={level.id}
                    className={`hover:bg-gray-800/50 ${!level.is_active ? "opacity-50" : ""}`}
                  >
                    <td className="px-4 py-3 text-white">{level.name}</td>
                    <td className="px-4 py-3">
                      <span className="text-green-400 font-medium">
                        {level.discount_percent}% off
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-1 rounded text-xs font-medium ${
                          level.is_active
                            ? "bg-green-500/20 text-green-400"
                            : "bg-gray-500/20 text-gray-400"
                        }`}
                      >
                        {level.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    {isPro && (
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            setAssigningLevel(level);
                            setShowAssignModal(true);
                          }}
                          className="text-blue-400 hover:text-blue-300 text-sm underline"
                        >
                          {level.customers?.length || 0} customers
                        </button>
                      </td>
                    )}
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => {
                            setEditingLevel(level);
                            setShowModal(true);
                          }}
                          className="text-gray-400 hover:text-white p-1"
                          title="Edit"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                          </svg>
                        </button>
                        {isPro && (
                          <button
                            onClick={() => {
                              setAssigningLevel(level);
                              setShowAssignModal(true);
                            }}
                            className="text-gray-400 hover:text-blue-400 p-1"
                            title="Manage customers"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create/Edit Modal */}
      {showModal && (
        <PriceLevelModal
          level={editingLevel}
          onSave={handleSave}
          onClose={() => {
            setShowModal(false);
            setEditingLevel(null);
          }}
        />
      )}

      {/* Customer Assignment Modal (PRO only) */}
      {isPro && showAssignModal && assigningLevel && (
        <AssignCustomersModal
          level={assigningLevel}
          allLevels={priceLevels || []}
          onAssign={handleAssign}
          onUnassign={handleUnassign}
          onClose={() => {
            setShowAssignModal(false);
            setAssigningLevel(null);
          }}
        />
      )}
    </div>
  );
}


// -- Price Level Create/Edit Modal --

function PriceLevelModal({ level, onSave, onClose }) {
  const firstInputRef = useRef(null);
  const [formData, setFormData] = useState({
    name: level?.name || "",
    discount_percent: level?.discount_percent ?? 0,
    description: level?.description || "",
    is_active: level?.is_active ?? true,
  });
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (firstInputRef.current) firstInputRef.current.focus();
  }, []);

  useEffect(() => {
    const handleEsc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const validate = () => {
    const newErrors = {};
    if (!formData.name.trim()) newErrors.name = "Name is required";
    const discount = Number(formData.discount_percent);
    if (formData.discount_percent === "" || !Number.isFinite(discount) || discount < 0 || discount > 100)
      newErrors.discount_percent = "Must be 0–100";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setIsSubmitting(true);
    try {
      await onSave({
        name: formData.name.trim(),
        discount_percent: Number(formData.discount_percent),
        description: formData.description || null,
        is_active: formData.is_active,
      });
    } catch {
      // handled by parent
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-md mx-4 p-6"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <h2 className="text-xl font-bold text-white mb-4">
          {level ? "Edit Price Level" : "Create Price Level"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Name *</label>
            <input
              ref={firstInputRef}
              type="text"
              value={formData.name}
              onChange={(e) => {
                setFormData({ ...formData, name: e.target.value });
                if (errors.name) setErrors({ ...errors, name: undefined });
              }}
              className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-white focus:outline-none ${
                errors.name ? "border-red-500" : "border-gray-700 focus:border-blue-500"
              }`}
              placeholder="e.g., Tier A, Wholesale, VIP"
              maxLength={100}
              disabled={isSubmitting}
            />
            {errors.name && <p className="text-red-400 text-sm mt-1">{errors.name}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Discount Percent *</label>
            <div className="relative">
              <input
                type="number"
                value={formData.discount_percent}
                onChange={(e) => {
                  setFormData({ ...formData, discount_percent: e.target.value });
                  if (errors.discount_percent) setErrors({ ...errors, discount_percent: undefined });
                }}
                className={`w-full bg-gray-800 border rounded-lg px-3 py-2 pr-8 text-white focus:outline-none ${
                  errors.discount_percent ? "border-red-500" : "border-gray-700 focus:border-blue-500"
                }`}
                min="0"
                max="100"
                step="0.01"
                disabled={isSubmitting}
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500">%</span>
            </div>
            {errors.discount_percent && <p className="text-red-400 text-sm mt-1">{errors.discount_percent}</p>}
            <p className="text-gray-500 text-xs mt-1">
              Applied to base product prices (e.g., 25 = 25% off)
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500 h-20 resize-none"
              disabled={isSubmitting}
              placeholder="Internal notes about this pricing tier"
            />
          </div>

          {level && (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active"
                checked={formData.is_active}
                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                className="rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
                disabled={isSubmitting}
              />
              <label htmlFor="is_active" className="text-sm text-gray-400">Active</label>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Saving..." : level ? "Save Changes" : "Create Level"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


// -- Customer Assignment Modal (PRO feature) --

function AssignCustomersModal({ level, allLevels = [], onAssign, onUnassign, onClose }) {
  const api = useApi();
  const [availableCustomers, setAvailableCustomers] = useState([]);
  const [loadingCustomers, setLoadingCustomers] = useState(true);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const fetchCustomers = async () => {
      try {
        const data = await api.get("/api/v1/pro/catalogs/available-customers");
        setAvailableCustomers(Array.isArray(data) ? data : data.customers || []);
      } catch {
        // Silently fail — still show assigned customers
      } finally {
        setLoadingCustomers(false);
      }
    };
    fetchCustomers();
  }, [api]);

  useEffect(() => {
    const handleEsc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const customerTierMap = useMemo(() => {
    const map = new Map();
    for (const lvl of allLevels) {
      for (const c of lvl.customers || []) {
        map.set(c.customer_id, { levelName: lvl.name, levelId: lvl.id });
      }
    }
    return map;
  }, [allLevels]);

  const assignedIds = new Set((level.customers || []).map((c) => c.customer_id));

  const matchesSearch = (c) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      c.display_name?.toLowerCase().includes(q) ||
      c.company_name?.toLowerCase().includes(q) ||
      c.email?.toLowerCase().includes(q)
    );
  };

  const unassigned = availableCustomers.filter(
    (c) => !assignedIds.has(c.id) && matchesSearch(c)
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-lg mx-4 p-6 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-xl font-bold text-white">{level.name}</h2>
            <p className="text-gray-400 text-sm">{level.discount_percent}% discount</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {level.customers?.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-400 mb-2">
              Assigned Customers ({level.customers.length})
            </h3>
            <div className="space-y-1 max-h-32 overflow-y-auto">
              {level.customers.map((c) => (
                <div key={c.customer_id} className="flex items-center justify-between bg-gray-800 rounded px-3 py-2">
                  <div>
                    <span className="text-white text-sm">{c.customer_name || c.company_name}</span>
                    {c.email && <span className="text-gray-500 text-xs ml-2">{c.email}</span>}
                  </div>
                  <button
                    onClick={() => onUnassign(level.id, c.customer_id)}
                    className="text-gray-500 hover:text-red-400 p-1"
                    title="Remove"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex-1 min-h-0">
          <h3 className="text-sm font-medium text-gray-400 mb-2">Add Customer</h3>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search customers..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500 mb-2"
          />
          {loadingCustomers ? (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mx-auto" />
            </div>
          ) : (
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {unassigned.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-3">
                  {search ? "No matching customers" : "All customers are assigned"}
                </p>
              ) : (
                unassigned.map((c) => {
                  const currentTier = customerTierMap.get(c.id);
                  return (
                    <button
                      key={c.id}
                      onClick={() => onAssign(c.id)}
                      className="w-full flex items-center justify-between bg-gray-800/50 hover:bg-gray-800 rounded px-3 py-2 text-left transition-colors"
                    >
                      <div>
                        <span className="text-white text-sm">
                          {c.company_name || c.display_name || c.email}
                        </span>
                        {c.email && c.company_name && (
                          <span className="text-gray-500 text-xs ml-2">{c.email}</span>
                        )}
                        {currentTier && (
                          <span className="text-amber-400/80 text-xs ml-2">— {currentTier.levelName}</span>
                        )}
                      </div>
                      <span className="text-gray-500 text-xs whitespace-nowrap ml-2">
                        {currentTier ? "Move" : "Add"}
                      </span>
                    </button>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
