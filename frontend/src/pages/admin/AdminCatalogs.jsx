import { useState, useEffect, useRef, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useCRUD } from "../../hooks/useCRUD";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

export default function AdminCatalogs() {
  const toast = useToast();
  const api = useApi();
  const { isPro, loading: flagsLoading } = useFeatureFlags();

  const {
    items: catalogs,
    loading,
    error,
    refresh,
  } = useCRUD("/api/v1/pro/catalogs", {
    extractKey: null,
    immediate: false,
  });

  const [showModal, setShowModal] = useState(false);
  const [editingCatalog, setEditingCatalog] = useState(null);
  const [detailCatalog, setDetailCatalog] = useState(null);

  useEffect(() => {
    if (isPro && !flagsLoading) {
      refresh().catch(() => {});
    }
  }, [isPro, flagsLoading, refresh]);

  // -- PRO gate --
  if (flagsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!isPro) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Catalogs</h1>
          <p className="text-gray-400 mt-1">
            Control which products your B2B customers can see and order
          </p>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-6 text-center">
          <svg className="w-12 h-12 text-blue-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <h3 className="text-lg font-semibold text-white mb-2">PRO Feature</h3>
          <p className="text-gray-400 mb-4">
            Catalogs let you create curated product collections for different
            customer groups. Assign products, set price overrides, and control
            who sees what on the B2B portal.
          </p>
          <a href="/pricing" className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors">
            Upgrade to PRO
          </a>
        </div>
      </div>
    );
  }

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
        <div><h1 className="text-2xl font-bold text-white">Catalogs</h1></div>
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">{error}</div>
      </div>
    );
  }

  // -- Handlers --
  const handleSave = async (formData) => {
    try {
      if (editingCatalog) {
        await api.patch(`/api/v1/pro/catalogs/${editingCatalog.id}`, formData);
        toast.success("Catalog updated");
      } else {
        await api.post("/api/v1/pro/catalogs", formData);
        toast.success("Catalog created");
      }
      setShowModal(false);
      setEditingCatalog(null);
      await refresh();
    } catch (err) {
      toast.error(err.message);
      throw err;
    }
  };

  const handleDelete = async (catalog) => {
    if (catalog.code === "PUBLIC") {
      toast.error("Cannot delete the default PUBLIC catalog");
      return;
    }
    if (!window.confirm(`Deactivate catalog "${catalog.name}"? This won't delete products.`)) return;
    try {
      await api.del(`/api/v1/pro/catalogs/${catalog.id}`);
      toast.success("Catalog deactivated");
      await refresh();
    } catch (err) {
      toast.error(err.message);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Catalogs</h1>
          <p className="text-gray-400 mt-1">
            Product collections for B2B portal customers
          </p>
        </div>
        <button
          onClick={() => { setEditingCatalog(null); setShowModal(true); }}
          className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Catalog
        </button>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
        <div className="flex gap-3">
          <svg className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-blue-400 text-sm">
            <strong>Public</strong> catalogs are visible to all portal users.
            <strong> Private</strong> catalogs are only visible to assigned customers.
            Products in the <strong>default</strong> catalog are automatically included
            for new items. Catalogs sync to the hosted portal every 15 minutes.
          </p>
        </div>
      </div>

      {/* Catalogs Grid */}
      {catalogs.length === 0 ? (
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-8 text-center text-gray-500">
          No catalogs yet. Click "Add Catalog" to create your first product collection.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {catalogs.map((catalog) => (
            <div
              key={catalog.id}
              className={`bg-gray-900 rounded-lg border border-gray-800 p-4 hover:border-gray-700 transition-colors ${
                !catalog.active ? "opacity-50" : ""
              }`}
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-white font-semibold">{catalog.name}</h3>
                  <span className="text-gray-500 text-xs font-mono">{catalog.code}</span>
                </div>
                <div className="flex gap-1">
                  {catalog.is_public && (
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-green-500/20 text-green-400">
                      Public
                    </span>
                  )}
                  {catalog.is_default && (
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-500/20 text-blue-400">
                      Default
                    </span>
                  )}
                  {!catalog.active && (
                    <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-500/20 text-gray-400">
                      Inactive
                    </span>
                  )}
                </div>
              </div>

              {catalog.description && (
                <p className="text-gray-400 text-sm mb-3 line-clamp-2">{catalog.description}</p>
              )}

              <div className="flex items-center gap-4 text-sm text-gray-500 mb-3">
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
                  </svg>
                  {catalog.product_count} products
                </span>
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                  {catalog.customer_count} customers
                </span>
              </div>

              <div className="flex items-center gap-2 border-t border-gray-800 pt-3">
                <button
                  onClick={() => setDetailCatalog(catalog)}
                  className="flex-1 text-center text-sm text-blue-400 hover:text-blue-300 py-1 rounded hover:bg-gray-800 transition-colors"
                >
                  Manage
                </button>
                <button
                  onClick={() => { setEditingCatalog(catalog); setShowModal(true); }}
                  className="text-gray-400 hover:text-white p-1"
                  title="Edit"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                  </svg>
                </button>
                {catalog.code !== "PUBLIC" && (
                  <button
                    onClick={() => handleDelete(catalog)}
                    className="text-gray-400 hover:text-red-400 p-1"
                    title="Deactivate"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                    </svg>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create/Edit Modal */}
      {showModal && (
        <CatalogModal
          catalog={editingCatalog}
          onSave={handleSave}
          onClose={() => { setShowModal(false); setEditingCatalog(null); }}
        />
      )}

      {/* Detail/Management Panel */}
      {detailCatalog && (
        <CatalogDetailPanel
          catalogId={detailCatalog.id}
          onClose={() => { setDetailCatalog(null); refresh(); }}
        />
      )}
    </div>
  );
}


// -- Catalog Create/Edit Modal --

function CatalogModal({ catalog, onSave, onClose }) {
  const firstInputRef = useRef(null);
  const [formData, setFormData] = useState({
    code: catalog?.code || "",
    name: catalog?.name || "",
    description: catalog?.description || "",
    is_default: catalog?.is_default ?? false,
    is_public: catalog?.is_public ?? true,
    sort_order: catalog?.sort_order ?? 0,
    active: catalog?.active ?? true,
  });
  const [errors, setErrors] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => { if (firstInputRef.current) firstInputRef.current.focus(); }, []);
  useEffect(() => {
    const handleEsc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  const validate = () => {
    const newErrors = {};
    if (!formData.code.trim()) newErrors.code = "Code is required";
    if (!formData.name.trim()) newErrors.name = "Name is required";
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validate()) return;
    setIsSubmitting(true);
    try {
      await onSave({
        ...formData,
        code: formData.code.toUpperCase().trim(),
        sort_order: parseInt(formData.sort_order, 10) || 0,
      });
    } catch { /* handled by parent */ } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-md mx-4 p-6" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <h2 className="text-xl font-bold text-white mb-4">
          {catalog ? "Edit Catalog" : "Create Catalog"}
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Code *</label>
            <input
              ref={firstInputRef}
              type="text"
              value={formData.code}
              onChange={(e) => {
                setFormData({ ...formData, code: e.target.value.toUpperCase().replace(/[^A-Z0-9-_]/g, "") });
                if (errors.code) setErrors({ ...errors, code: undefined });
              }}
              className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-white focus:outline-none ${
                errors.code ? "border-red-500" : "border-gray-700 focus:border-blue-500"
              }`}
              placeholder="e.g., WHOLESALE"
              maxLength={50}
              disabled={!!catalog || isSubmitting}
            />
            {errors.code && <p className="text-red-400 text-sm mt-1">{errors.code}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Name *</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => {
                setFormData({ ...formData, name: e.target.value });
                if (errors.name) setErrors({ ...errors, name: undefined });
              }}
              className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-white focus:outline-none ${
                errors.name ? "border-red-500" : "border-gray-700 focus:border-blue-500"
              }`}
              placeholder="e.g., Wholesale Collection"
              maxLength={100}
              disabled={isSubmitting}
            />
            {errors.name && <p className="text-red-400 text-sm mt-1">{errors.name}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Description</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500 h-20 resize-none"
              disabled={isSubmitting}
              placeholder="What this catalog is for"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_public"
                checked={formData.is_public}
                onChange={(e) => setFormData({ ...formData, is_public: e.target.checked })}
                className="rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
                disabled={isSubmitting}
              />
              <label htmlFor="is_public" className="text-sm text-gray-400">Public</label>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_default"
                checked={formData.is_default}
                onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                className="rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
                disabled={isSubmitting}
              />
              <label htmlFor="is_default" className="text-sm text-gray-400">Default</label>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-400 mb-1">Sort Order</label>
            <input
              type="number"
              value={formData.sort_order}
              onChange={(e) => setFormData({ ...formData, sort_order: parseInt(e.target.value, 10) || 0 })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-blue-500"
              disabled={isSubmitting}
              min="0"
            />
          </div>

          {catalog && (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="active"
                checked={formData.active}
                onChange={(e) => setFormData({ ...formData, active: e.target.checked })}
                className="rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
                disabled={isSubmitting}
              />
              <label htmlFor="active" className="text-sm text-gray-400">Active</label>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-gray-400 hover:text-white transition-colors" disabled={isSubmitting}>Cancel</button>
            <button type="submit" className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition-colors disabled:opacity-50" disabled={isSubmitting}>
              {isSubmitting ? "Saving..." : catalog ? "Save Changes" : "Create Catalog"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}


// -- Catalog Detail Panel (products + customers management) --

function CatalogDetailPanel({ catalogId, onClose }) {
  const api = useApi();
  const toast = useToast();
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState("products");
  const [showAddProducts, setShowAddProducts] = useState(false);
  const [showAddCustomers, setShowAddCustomers] = useState(false);

  const fetchCatalog = useCallback(async () => {
    try {
      const data = await api.get(`/api/v1/pro/catalogs/${catalogId}`);
      setCatalog(data);
    } catch (err) {
      toast.error("Failed to load catalog details");
    } finally {
      setLoading(false);
    }
  }, [api, catalogId, toast]);

  useEffect(() => { fetchCatalog(); }, [fetchCatalog]);

  useEffect(() => {
    const handleEsc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [onClose]);

  // Product actions
  const handleRemoveProduct = async (productId) => {
    try {
      await api.del(`/api/v1/pro/catalogs/${catalogId}/products/${productId}`);
      toast.success("Product removed from catalog");
      fetchCatalog();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleAddProducts = async (productIds) => {
    try {
      const result = await api.post(`/api/v1/pro/catalogs/${catalogId}/products/bulk`, {
        product_ids: productIds,
      });
      toast.success(`Added ${result.added} products (${result.skipped} already in catalog)`);
      setShowAddProducts(false);
      fetchCatalog();
    } catch (err) {
      toast.error(err.message);
    }
  };

  // Customer actions
  const handleRemoveCustomer = async (customerId) => {
    try {
      await api.del(`/api/v1/pro/catalogs/${catalogId}/customers/${customerId}`);
      toast.success("Customer removed from catalog");
      fetchCatalog();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleAddCustomers = async (customerIds) => {
    try {
      const result = await api.post(`/api/v1/pro/catalogs/${catalogId}/customers/bulk`, {
        customer_ids: customerIds,
      });
      toast.success(`Added ${result.added} customers (${result.skipped} already assigned)`);
      setShowAddCustomers(false);
      fetchCatalog();
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!catalog) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-gray-900 rounded-t-lg sm:rounded-lg border border-gray-800 w-full max-w-3xl mx-0 sm:mx-4 max-h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <div>
            <h2 className="text-lg font-bold text-white">{catalog.name}</h2>
            <span className="text-gray-500 text-xs font-mono">{catalog.code}</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white p-1">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-800 px-4">
          {["products", "customers"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab
                  ? "border-blue-500 text-white"
                  : "border-transparent text-gray-400 hover:text-white"
              }`}
            >
              {tab === "products"
                ? `Products (${catalog.products?.length || 0})`
                : `Customers (${catalog.customers?.length || 0})`}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === "products" && (
            <div>
              <div className="flex justify-end mb-3">
                <button
                  onClick={() => setShowAddProducts(true)}
                  className="text-sm bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add Products
                </button>
              </div>

              {catalog.products?.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-6">
                  No products in this catalog. Click "Add Products" to get started.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-gray-800/50">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">SKU</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-400 uppercase">Name</th>
                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">Base Price</th>
                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">Override</th>
                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-400 uppercase">Effective</th>
                        <th className="px-3 py-2 w-10"></th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800">
                      {catalog.products.map((p) => (
                        <tr key={p.product_id} className="hover:bg-gray-800/50">
                          <td className="px-3 py-2 text-gray-400 font-mono text-sm">{p.sku}</td>
                          <td className="px-3 py-2 text-white text-sm">{p.name}</td>
                          <td className="px-3 py-2 text-right text-gray-400 text-sm">
                            ${parseFloat(p.selling_price || 0).toFixed(2)}
                          </td>
                          <td className="px-3 py-2 text-right text-sm">
                            {p.price_override != null ? (
                              <span className="text-yellow-400">${parseFloat(p.price_override).toFixed(2)}</span>
                            ) : (
                              <span className="text-gray-600">—</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right text-white text-sm font-medium">
                            ${parseFloat(p.effective_price || p.selling_price || 0).toFixed(2)}
                          </td>
                          <td className="px-3 py-2">
                            <button
                              onClick={() => handleRemoveProduct(p.product_id)}
                              className="text-gray-500 hover:text-red-400 p-1"
                              title="Remove"
                            >
                              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {activeTab === "customers" && (
            <div>
              <div className="flex justify-end mb-3">
                <button
                  onClick={() => setShowAddCustomers(true)}
                  className="text-sm bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg flex items-center gap-1 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  Add Customers
                </button>
              </div>

              {catalog.customers?.length === 0 ? (
                <p className="text-gray-500 text-sm text-center py-6">
                  No customers assigned. {catalog.is_public ? "This is a public catalog — all portal users can see it." : "Add customers to give them access."}
                </p>
              ) : (
                <div className="space-y-1">
                  {catalog.customers.map((c) => (
                    <div key={c.customer_id} className="flex items-center justify-between bg-gray-800/50 rounded px-3 py-2">
                      <div>
                        <span className="text-white text-sm">{c.company_name || c.customer_number}</span>
                        {c.email && <span className="text-gray-500 text-xs ml-2">{c.email}</span>}
                      </div>
                      <button
                        onClick={() => handleRemoveCustomer(c.customer_id)}
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
              )}
            </div>
          )}
        </div>
      </div>

      {/* Add Products Picker */}
      {showAddProducts && (
        <ProductPicker
          catalogProducts={catalog.products || []}
          onAdd={handleAddProducts}
          onClose={() => setShowAddProducts(false)}
        />
      )}

      {/* Add Customers Picker */}
      {showAddCustomers && (
        <CustomerPicker
          catalogCustomers={catalog.customers || []}
          onAdd={handleAddCustomers}
          onClose={() => setShowAddCustomers(false)}
        />
      )}
    </div>
  );
}


// -- Product Picker (bulk add) --

function ProductPicker({ catalogProducts, onAdd, onClose }) {
  const api = useApi();
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(new Set());

  useEffect(() => {
    const fetchProducts = async () => {
      try {
        const data = await api.get("/api/v1/items?limit=500&item_type=finished_good");
        const items = Array.isArray(data) ? data : data.items || [];
        setProducts(items);
      } catch { /* silently fail */ } finally {
        setLoading(false);
      }
    };
    fetchProducts();
  }, [api]);

  const existingIds = new Set(catalogProducts.map((p) => p.product_id));
  const filtered = products.filter(
    (p) =>
      !existingIds.has(p.id) &&
      (p.name?.toLowerCase().includes(search.toLowerCase()) ||
        p.sku?.toLowerCase().includes(search.toLowerCase()))
  );

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(filtered.map((p) => p.id)));
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-lg mx-4 max-h-[70vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-bold text-white">Add Products</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-white p-1">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or SKU..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            autoFocus
          />
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mx-auto" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-4">
              {search ? "No matching products" : "All products are already in this catalog"}
            </p>
          ) : (
            <>
              <button onClick={selectAll} className="text-xs text-blue-400 hover:text-blue-300 mb-2">
                Select all ({filtered.length})
              </button>
              <div className="space-y-1">
                {filtered.map((p) => (
                  <label
                    key={p.id}
                    className={`flex items-center gap-3 rounded px-3 py-2 cursor-pointer transition-colors ${
                      selected.has(p.id) ? "bg-blue-600/20" : "hover:bg-gray-800"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(p.id)}
                      onChange={() => toggleSelect(p.id)}
                      className="rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
                    />
                    <div className="flex-1 min-w-0">
                      <span className="text-white text-sm block truncate">{p.name}</span>
                      <span className="text-gray-500 text-xs">{p.sku}</span>
                    </div>
                    <span className="text-gray-400 text-sm">
                      ${parseFloat(p.selling_price || 0).toFixed(2)}
                    </span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="p-4 border-t border-gray-800 flex justify-between items-center">
          <span className="text-gray-400 text-sm">{selected.size} selected</span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-gray-400 hover:text-white text-sm transition-colors">Cancel</button>
            <button
              onClick={() => onAdd([...selected])}
              disabled={selected.size === 0}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              Add {selected.size > 0 ? `(${selected.size})` : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}


// -- Customer Picker (bulk add) --

function CustomerPicker({ catalogCustomers, onAdd, onClose }) {
  const api = useApi();
  const [customers, setCustomers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState(new Set());

  useEffect(() => {
    const fetchCustomers = async () => {
      try {
        const data = await api.get("/api/v1/pro/catalogs/available-customers");
        setCustomers(Array.isArray(data) ? data : data.customers || []);
      } catch { /* silently fail */ } finally {
        setLoading(false);
      }
    };
    fetchCustomers();
  }, [api]);

  const existingIds = new Set(catalogCustomers.map((c) => c.customer_id));
  const filtered = customers.filter(
    (c) =>
      !existingIds.has(c.id) &&
      (c.display_name?.toLowerCase().includes(search.toLowerCase()) ||
        c.company_name?.toLowerCase().includes(search.toLowerCase()) ||
        c.email?.toLowerCase().includes(search.toLowerCase()))
  );

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="bg-gray-900 rounded-lg border border-gray-800 w-full max-w-lg mx-4 max-h-[70vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="p-4 border-b border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-lg font-bold text-white">Add Customers</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-white p-1">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name, company, or email..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
            autoFocus
          />
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-center py-4">
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500 mx-auto" />
            </div>
          ) : filtered.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-4">
              {search ? "No matching customers" : "All customers are already assigned"}
            </p>
          ) : (
            <div className="space-y-1">
              {filtered.map((c) => (
                <label
                  key={c.id}
                  className={`flex items-center gap-3 rounded px-3 py-2 cursor-pointer transition-colors ${
                    selected.has(c.id) ? "bg-blue-600/20" : "hover:bg-gray-800"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggleSelect(c.id)}
                    className="rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-white text-sm block truncate">{c.company_name || c.display_name || c.email}</span>
                    {c.email && c.company_name && <span className="text-gray-500 text-xs">{c.email}</span>}
                  </div>
                </label>
              ))}
            </div>
          )}
        </div>

        <div className="p-4 border-t border-gray-800 flex justify-between items-center">
          <span className="text-gray-400 text-sm">{selected.size} selected</span>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-3 py-1.5 text-gray-400 hover:text-white text-sm transition-colors">Cancel</button>
            <button
              onClick={() => onAdd([...selected])}
              disabled={selected.size === 0}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              Add {selected.size > 0 ? `(${selected.size})` : ""}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
