import { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import Modal from "../../components/Modal";
import ProGate from "../../components/ProGate";

const EMPTY_CATALOG_FORM = {
  name: "",
  description: "",
  is_active: true,
};

export default function AdminCatalogs() {
  return (
    <ProGate
      feature="Catalogs"
      description="Create customer-specific product catalogs with optional price overrides."
      benefits={[
        "Customer-specific product visibility",
        "Per-product price overrides",
        "Assign catalogs to specific customers",
        "Multiple catalogs per customer",
      ]}
    >
      <CatalogsContent />
    </ProGate>
  );
}

function CatalogsContent() {
  const toast = useToast();
  const api = useApi();

  // Catalog list state
  const [catalogs, setCatalogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Selected catalog + detail
  const [selectedCatalog, setSelectedCatalog] = useState(null);
  const [catalogDetail, setCatalogDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Active tab in detail panel
  const [activeTab, setActiveTab] = useState("products");

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [editingCatalog, setEditingCatalog] = useState(null);
  const [saving, setSaving] = useState(false);

  // Products tab state
  const [allItems, setAllItems] = useState([]);
  const [productSearch, setProductSearch] = useState("");
  const [addProductId, setAddProductId] = useState("");
  const [addPriceOverride, setAddPriceOverride] = useState("");
  const [addingProduct, setAddingProduct] = useState(false);

  // Customers tab state
  const [availableCustomers, setAvailableCustomers] = useState([]);
  const [loadingCustomers, setLoadingCustomers] = useState(false);
  const [assignCustomerId, setAssignCustomerId] = useState("");
  const [assigningCustomer, setAssigningCustomer] = useState(false);

  // ──────────────────────────────────────────────
  // Fetch catalog list
  // ──────────────────────────────────────────────
  const fetchCatalogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get("/api/v1/pro/catalogs");
      setCatalogs(Array.isArray(data) ? data : []);
      // Keep selected catalog in sync after refresh
      setSelectedCatalog((prev) => {
        if (!prev) return null;
        const updated = (Array.isArray(data) ? data : []).find(
          (c) => c.id === prev.id
        );
        return updated || null;
      });
    } catch (err) {
      setError(err.message || "Failed to load catalogs");
    } finally {
      setLoading(false);
    }
  }, [api]);

  // ──────────────────────────────────────────────
  // Fetch full catalog detail (products + customers)
  // ──────────────────────────────────────────────
  const fetchCatalogDetail = useCallback(
    async (catalogId) => {
      setLoadingDetail(true);
      try {
        const data = await api.get(`/api/v1/pro/catalogs/${catalogId}`);
        setCatalogDetail(data);
      } catch (err) {
        toast.error(err.message || "Failed to load catalog details");
      } finally {
        setLoadingDetail(false);
      }
    },
    [api, toast]
  );

  // ──────────────────────────────────────────────
  // Fetch all items for product search
  // ──────────────────────────────────────────────
  const fetchAllItems = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/items");
      setAllItems(Array.isArray(data) ? data : (data?.items ?? []));
    } catch {
      // Non-critical — product search just won't work
    }
  }, [api]);

  // ──────────────────────────────────────────────
  // Fetch available customers for assignment
  // ──────────────────────────────────────────────
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

  // ──────────────────────────────────────────────
  // Effects
  // ──────────────────────────────────────────────
  useEffect(() => {
    fetchCatalogs();
    fetchAllItems();
  }, [fetchCatalogs, fetchAllItems]);

  useEffect(() => {
    if (selectedCatalog) {
      fetchCatalogDetail(selectedCatalog.id);
      fetchAvailableCustomers();
      setActiveTab("products");
      setProductSearch("");
      setAddProductId("");
      setAddPriceOverride("");
      setAssignCustomerId("");
    } else {
      setCatalogDetail(null);
    }
  }, [selectedCatalog?.id, fetchCatalogDetail, fetchAvailableCustomers]);

  // ──────────────────────────────────────────────
  // Catalog list actions
  // ──────────────────────────────────────────────
  const handleRowClick = (catalog) => {
    if (selectedCatalog?.id === catalog.id) {
      setSelectedCatalog(null);
    } else {
      setSelectedCatalog(catalog);
    }
  };

  const handleOpenCreate = () => {
    setEditingCatalog(null);
    setShowModal(true);
  };

  const handleOpenEdit = (e, catalog) => {
    e.stopPropagation();
    setEditingCatalog(catalog);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
    setEditingCatalog(null);
  };

  const handleSaveCatalog = async (formData) => {
    setSaving(true);
    try {
      if (editingCatalog) {
        await api.patch(`/api/v1/pro/catalogs/${editingCatalog.id}`, formData);
        toast.success("Catalog updated");
      } else {
        await api.post("/api/v1/pro/catalogs", formData);
        toast.success("Catalog created");
      }
      handleCloseModal();
      await fetchCatalogs();
      // Refresh detail if this was the selected catalog
      if (editingCatalog && selectedCatalog?.id === editingCatalog.id) {
        await fetchCatalogDetail(editingCatalog.id);
      }
    } catch (err) {
      toast.error(err.message || "Failed to save catalog");
    } finally {
      setSaving(false);
    }
  };

  // ──────────────────────────────────────────────
  // Products tab actions
  // ──────────────────────────────────────────────
  const handleAddProduct = useCallback(async () => {
    if (!addProductId || !selectedCatalog) return;
    setAddingProduct(true);
    try {
      await api.post(`/api/v1/pro/catalogs/${selectedCatalog.id}/products`, {
        product_id: Number(addProductId),
        price_override:
          addPriceOverride !== "" ? Number(addPriceOverride) : null,
      });
      toast.success("Product added to catalog");
      setAddProductId("");
      setAddPriceOverride("");
      setProductSearch("");
      await fetchCatalogDetail(selectedCatalog.id);
      await fetchCatalogs();
    } catch (err) {
      toast.error(err.message || "Failed to add product");
    } finally {
      setAddingProduct(false);
    }
  }, [
    addProductId,
    addPriceOverride,
    selectedCatalog,
    api,
    toast,
    fetchCatalogDetail,
    fetchCatalogs,
  ]);

  const handleRemoveProduct = useCallback(
    async (productId) => {
      if (!selectedCatalog) return;
      try {
        await api.del(
          `/api/v1/pro/catalogs/${selectedCatalog.id}/products/${productId}`
        );
        toast.success("Product removed");
        await fetchCatalogDetail(selectedCatalog.id);
        await fetchCatalogs();
      } catch (err) {
        toast.error(err.message || "Failed to remove product");
      }
    },
    [selectedCatalog, api, toast, fetchCatalogDetail, fetchCatalogs]
  );

  // ──────────────────────────────────────────────
  // Customers tab actions
  // ──────────────────────────────────────────────
  const handleAssignCustomer = useCallback(async () => {
    if (!assignCustomerId || !selectedCatalog) return;
    setAssigningCustomer(true);
    try {
      await api.post(`/api/v1/pro/catalogs/${selectedCatalog.id}/customers`, {
        customer_id: Number(assignCustomerId),
      });
      toast.success("Customer assigned");
      setAssignCustomerId("");
      await fetchCatalogDetail(selectedCatalog.id);
      await fetchCatalogs();
      await fetchAvailableCustomers();
    } catch (err) {
      toast.error(err.message || "Failed to assign customer");
    } finally {
      setAssigningCustomer(false);
    }
  }, [
    assignCustomerId,
    selectedCatalog,
    api,
    toast,
    fetchCatalogDetail,
    fetchCatalogs,
    fetchAvailableCustomers,
  ]);

  const handleRemoveCustomer = useCallback(
    async (customerId) => {
      if (!selectedCatalog) return;
      try {
        await api.del(
          `/api/v1/pro/catalogs/${selectedCatalog.id}/customers/${customerId}`
        );
        toast.success("Customer removed");
        await fetchCatalogDetail(selectedCatalog.id);
        await fetchCatalogs();
        await fetchAvailableCustomers();
      } catch (err) {
        toast.error(err.message || "Failed to remove customer");
      }
    },
    [
      selectedCatalog,
      api,
      toast,
      fetchCatalogDetail,
      fetchCatalogs,
      fetchAvailableCustomers,
    ]
  );

  // ──────────────────────────────────────────────
  // Derived state
  // ──────────────────────────────────────────────
  const assignedProducts = catalogDetail?.products ?? [];
  const assignedCustomers = catalogDetail?.customers ?? [];

  // Items filtered by search, excluding already-added products
  const assignedProductIds = new Set(assignedProducts.map((p) => p.product_id ?? p.id));
  const filteredItems = allItems.filter((item) => {
    if (assignedProductIds.has(item.id)) return false;
    if (!productSearch.trim()) return true;
    const q = productSearch.toLowerCase();
    return (
      (item.name || "").toLowerCase().includes(q) ||
      (item.sku || "").toLowerCase().includes(q)
    );
  });

  // Customers not already assigned to this catalog
  const assignedCustomerIds = new Set(assignedCustomers.map((c) => c.id));
  const assignableCustomers = availableCustomers.filter(
    (c) => !assignedCustomerIds.has(c.id)
  );

  // ──────────────────────────────────────────────
  // Render
  // ──────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Catalogs</h1>
          <p className="text-gray-400 mt-1">
            Manage customer-specific product catalogs with optional price overrides
          </p>
        </div>
        <button
          onClick={handleOpenCreate}
          className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
        >
          + New Catalog
        </button>
      </div>

      {/* Error banner */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 text-red-400">
          {error}
        </div>
      )}

      {/* Loading spinner */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
        </div>
      )}

      {/* Two-panel layout */}
      {!loading && (
        <div className={`flex gap-6 ${selectedCatalog ? "items-start" : ""}`}>
          {/* Left panel — catalog list */}
          <div
            className={`${
              selectedCatalog ? "w-80 flex-shrink-0" : "w-full"
            } bg-gray-900 border border-gray-800 rounded-xl overflow-hidden`}
          >
            {catalogs.length === 0 ? (
              <div className="py-12 text-center text-gray-500">
                No catalogs yet. Click &ldquo;+ New Catalog&rdquo; to create one.
              </div>
            ) : (
              <ul className="divide-y divide-gray-800">
                {catalogs.map((catalog) => {
                  const isSelected = selectedCatalog?.id === catalog.id;
                  return (
                    <li
                      key={catalog.id}
                      onClick={() => handleRowClick(catalog)}
                      className={`p-4 cursor-pointer transition-colors ${
                        isSelected
                          ? "bg-blue-600/10 border-l-2 border-l-blue-500"
                          : "hover:bg-gray-800/50"
                      } ${!catalog.is_active ? "opacity-60" : ""}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-medium text-white truncate">
                              {catalog.name}
                            </span>
                            {catalog.is_active ? (
                              <span className="flex-shrink-0 px-2 py-0.5 rounded-full text-xs bg-green-500/20 text-green-400">
                                Active
                              </span>
                            ) : (
                              <span className="flex-shrink-0 px-2 py-0.5 rounded-full text-xs bg-gray-500/20 text-gray-400">
                                Inactive
                              </span>
                            )}
                          </div>
                          {catalog.description && (
                            <p className="text-sm text-gray-400 mt-0.5 truncate">
                              {catalog.description}
                            </p>
                          )}
                          <div className="flex gap-3 mt-1 text-xs text-gray-500">
                            <span>{catalog.product_count ?? 0} products</span>
                            <span>{catalog.customer_count ?? 0} customers</span>
                          </div>
                        </div>
                        <button
                          onClick={(e) => handleOpenEdit(e, catalog)}
                          className="flex-shrink-0 text-blue-400 hover:text-blue-300 text-sm"
                        >
                          Edit
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {/* Right panel — catalog detail */}
          {selectedCatalog && (
            <div className="flex-1 min-w-0 bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              {/* Detail header */}
              <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
                <div className="flex items-center gap-3 min-w-0">
                  <h2 className="text-lg font-semibold text-white truncate">
                    {selectedCatalog.name}
                  </h2>
                  <button
                    onClick={(e) => handleOpenEdit(e, selectedCatalog)}
                    className="flex-shrink-0 text-blue-400 hover:text-blue-300 text-sm"
                  >
                    Edit
                  </button>
                </div>
                <button
                  onClick={() => setSelectedCatalog(null)}
                  className="text-gray-500 hover:text-gray-300 text-sm flex-shrink-0"
                >
                  Close
                </button>
              </div>

              {/* Tabs */}
              <div className="flex border-b border-gray-800">
                {["products", "customers"].map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-5 py-3 text-sm font-medium capitalize transition-colors ${
                      activeTab === tab
                        ? "text-white border-b-2 border-blue-500"
                        : "text-gray-400 hover:text-gray-300"
                    }`}
                  >
                    {tab}
                  </button>
                ))}
              </div>

              {/* Loading detail spinner */}
              {loadingDetail ? (
                <div className="flex items-center justify-center h-40">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
                </div>
              ) : (
                <div className="p-5">
                  {/* ── Products Tab ── */}
                  {activeTab === "products" && (
                    <div className="space-y-4">
                      {/* Products table */}
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[480px]">
                          <thead className="bg-gray-800/50">
                            <tr>
                              <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Product Name
                              </th>
                              <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                SKU
                              </th>
                              <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Price Override
                              </th>
                              <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Remove
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {assignedProducts.map((p) => (
                              <tr
                                key={p.product_id ?? p.id}
                                className="border-b border-gray-800 hover:bg-gray-800/30"
                              >
                                <td className="py-2 px-3 text-white text-sm">
                                  {p.name || p.product_name || "—"}
                                </td>
                                <td className="py-2 px-3 text-gray-300 text-sm font-mono">
                                  {p.sku || "—"}
                                </td>
                                <td className="py-2 px-3 text-right text-sm">
                                  {p.price_override != null ? (
                                    <span className="text-green-400">
                                      ${Number(p.price_override).toFixed(2)}
                                    </span>
                                  ) : (
                                    <span className="text-gray-500">—</span>
                                  )}
                                </td>
                                <td className="py-2 px-3 text-right">
                                  <button
                                    onClick={() =>
                                      handleRemoveProduct(p.product_id ?? p.id)
                                    }
                                    className="text-red-400 hover:text-red-300 text-sm"
                                    title="Remove product from catalog"
                                  >
                                    &times;
                                  </button>
                                </td>
                              </tr>
                            ))}
                            {assignedProducts.length === 0 && (
                              <tr>
                                <td
                                  colSpan={4}
                                  className="py-8 text-center text-gray-500 text-sm italic"
                                >
                                  No products in this catalog yet.
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>

                      {/* Add product row */}
                      <div className="bg-gray-800/50 rounded-lg p-4 space-y-3">
                        <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                          Add Product
                        </p>
                        <div className="flex flex-wrap gap-3">
                          {/* Search input */}
                          <div className="flex-1 min-w-48 relative">
                            <input
                              type="text"
                              value={productSearch}
                              onChange={(e) => {
                                setProductSearch(e.target.value);
                                setAddProductId("");
                              }}
                              placeholder="Search by name or SKU..."
                              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500"
                            />
                          </div>
                          {/* Product select dropdown (shown when search has results) */}
                          <select
                            value={addProductId}
                            onChange={(e) => setAddProductId(e.target.value)}
                            className="flex-1 min-w-48 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm"
                          >
                            <option value="">Select product…</option>
                            {filteredItems.map((item) => (
                              <option key={item.id} value={item.id}>
                                {item.name}
                                {item.sku ? ` (${item.sku})` : ""}
                              </option>
                            ))}
                          </select>
                          {/* Price override input */}
                          <input
                            type="number"
                            value={addPriceOverride}
                            onChange={(e) => setAddPriceOverride(e.target.value)}
                            placeholder="Price override (optional)"
                            min={0}
                            step={0.01}
                            className="w-52 bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm placeholder-gray-500"
                          />
                          <button
                            onClick={handleAddProduct}
                            disabled={!addProductId || addingProduct}
                            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm whitespace-nowrap"
                          >
                            {addingProduct ? "Adding…" : "Add"}
                          </button>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* ── Customers Tab ── */}
                  {activeTab === "customers" && (
                    <div className="space-y-4">
                      {/* Assign customer row */}
                      <div className="flex gap-3">
                        {loadingCustomers ? (
                          <div className="flex items-center gap-2 text-gray-400 text-sm">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
                            Loading customers…
                          </div>
                        ) : (
                          <>
                            <select
                              value={assignCustomerId}
                              onChange={(e) =>
                                setAssignCustomerId(e.target.value)
                              }
                              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm"
                            >
                              <option value="">
                                Select a customer to assign…
                              </option>
                              {assignableCustomers.map((c) => (
                                <option key={c.id} value={c.id}>
                                  {c.name ||
                                    c.company_name ||
                                    `Customer #${c.id}`}
                                </option>
                              ))}
                            </select>
                            <button
                              onClick={handleAssignCustomer}
                              disabled={!assignCustomerId || assigningCustomer}
                              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg text-sm whitespace-nowrap"
                            >
                              {assigningCustomer
                                ? "Assigning…"
                                : "Assign Customer"}
                            </button>
                          </>
                        )}
                      </div>

                      {/* Assigned customers table */}
                      <div className="overflow-x-auto">
                        <table className="w-full min-w-[360px]">
                          <thead className="bg-gray-800/50">
                            <tr>
                              <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Customer Name
                              </th>
                              <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Company
                              </th>
                              <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">
                                Remove
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {assignedCustomers.map((customer) => (
                              <tr
                                key={customer.id}
                                className="border-b border-gray-800 hover:bg-gray-800/30"
                              >
                                <td className="py-2 px-3 text-white text-sm">
                                  {customer.name || `Customer #${customer.id}`}
                                </td>
                                <td className="py-2 px-3 text-gray-400 text-sm">
                                  {customer.company_name || "—"}
                                </td>
                                <td className="py-2 px-3 text-right">
                                  <button
                                    onClick={() =>
                                      handleRemoveCustomer(customer.id)
                                    }
                                    className="text-red-400 hover:text-red-300 text-sm"
                                    title="Remove customer from catalog"
                                  >
                                    &times;
                                  </button>
                                </td>
                              </tr>
                            ))}
                            {assignedCustomers.length === 0 && (
                              <tr>
                                <td
                                  colSpan={3}
                                  className="py-8 text-center text-gray-500 text-sm italic"
                                >
                                  No customers assigned to this catalog yet.
                                </td>
                              </tr>
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Create / Edit Catalog Modal */}
      {showModal && (
        <CatalogModal
          catalog={editingCatalog}
          onSave={handleSaveCatalog}
          onClose={handleCloseModal}
          saving={saving}
        />
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// Create / Edit Modal
// ──────────────────────────────────────────────────────────────
function CatalogModal({ catalog, onSave, onClose, saving }) {
  const [form, setForm] = useState(
    catalog
      ? {
          name: catalog.name ?? "",
          description: catalog.description ?? "",
          is_active: catalog.is_active ?? true,
        }
      : { ...EMPTY_CATALOG_FORM }
  );

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(form);
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={catalog ? "Edit Catalog" : "New Catalog"}
      disableClose={saving}
    >
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-xl font-bold text-white">
          {catalog ? "Edit Catalog" : "New Catalog"}
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
        {/* Name */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">Name *</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
            placeholder="e.g. VIP Customer Catalog"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Description{" "}
            <span className="text-gray-600 font-normal">(optional)</span>
          </label>
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            rows={3}
            placeholder="Brief description of this catalog…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 resize-none"
          />
        </div>

        {/* Active */}
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
            {saving ? "Saving…" : catalog ? "Save Changes" : "Create Catalog"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
