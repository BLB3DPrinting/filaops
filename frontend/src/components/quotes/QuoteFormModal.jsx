/**
 * QuoteFormModal - 2-step form for creating/editing quotes.
 *
 * Extracted from AdminQuotes.jsx (ARCHITECT-002)
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";

export default function QuoteFormModal({ quote, onSave, onClose }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState(quote ? 2 : 1); // 1=product, 2=customer+details
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [companySettings, setCompanySettings] = useState(null);
  const [productSearch, setProductSearch] = useState("");
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [loading, setLoading] = useState(true);

  const [form, setForm] = useState({
    product_id: quote?.product_id || null,
    product_name: quote?.product_name || "",
    quantity: quote?.quantity || 1,
    unit_price: quote?.unit_price || "",
    customer_id: quote?.customer_id || null,
    customer_name: quote?.customer_name || "",
    customer_email: quote?.customer_email || "",
    material_type: quote?.material_type || "",
    color: quote?.color || "",
    customer_notes: quote?.customer_notes || "",
    admin_notes: quote?.admin_notes || "",
    apply_tax: quote?.tax_rate ? true : null, // null = use company default
    shipping_cost: quote?.shipping_cost || "",
    valid_days: 30,
  });
  const [saveAsCustomer, setSaveAsCustomer] = useState(false);

  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchProducts();
    fetchCustomers();
    fetchCompanySettings();
  }, []);

  const fetchProducts = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/products?limit=500&active_only=true`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setProducts(data.items || data || []);
      }
    } catch {
      // Products fetch failure will show empty list
    } finally {
      setLoading(false);
    }
  };

  const fetchCustomers = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/admin/customers?limit=200`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setCustomers(data.items || data || []);
      }
    } catch {
      // Customers fetch failure is non-critical
    }
  };

  const fetchCompanySettings = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/settings/company`, {
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        setCompanySettings(data);
        // Default apply_tax based on company settings
        if (form.apply_tax === null && !quote) {
          setForm((f) => ({ ...f, apply_tax: data.tax_enabled }));
        }
      }
    } catch {
      // Company settings fetch failure is non-critical
    }
  };

  // Filter products that have a BOM
  const filteredProducts = products.filter((p) => {
    if (!p.has_bom) return false;
    if (!productSearch.trim()) return true;
    const search = productSearch.toLowerCase();
    return (
      (p.name || "").toLowerCase().includes(search) ||
      (p.sku || "").toLowerCase().includes(search)
    );
  });

  const handleSelectProduct = (product) => {
    setSelectedProduct(product);
    setForm((f) => ({
      ...f,
      product_id: product.id,
      product_name: product.name,
      unit_price: product.selling_price || "",
      material_type: product.category || "",
    }));
    setStep(2);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.product_name || !form.unit_price) {
      toast.error("Product and unit price are required");
      return;
    }

    // Validate save as customer requires email
    if (saveAsCustomer && !form.customer_email) {
      toast.error("Customer email is required to save as new customer");
      return;
    }

    setSaving(true);

    // If saving as new customer, create customer first
    let customerId = form.customer_id;
    if (saveAsCustomer && !customerId && form.customer_email) {
      try {
        // Parse name into first/last
        const nameParts = (form.customer_name || "").trim().split(" ");
        const firstName = nameParts[0] || "";
        const lastName = nameParts.slice(1).join(" ") || "";

        const customerRes = await fetch(`${API_URL}/api/v1/admin/customers`, {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email: form.customer_email,
            first_name: firstName || null,
            last_name: lastName || null,
          }),
        });

        if (customerRes.ok) {
          const newCustomer = await customerRes.json();
          customerId = newCustomer.id;
          toast.success(`Customer ${newCustomer.customer_number} created`);
        } else {
          const err = await customerRes.json();
          // If customer exists, try to find them
          if (err.detail?.includes("already exists")) {
            toast.info("Customer already exists, linking to quote");
          } else {
            throw new Error(err.detail || "Failed to create customer");
          }
        }
      } catch (err) {
        console.error("Failed to create customer:", err);
        // Continue with quote creation even if customer creation fails
      }
    }

    // Build the payload - only send fields the backend accepts
    const payload = {
      product_id: form.product_id || null,
      product_name: form.product_name,
      quantity: form.quantity,
      unit_price: parseFloat(form.unit_price),
      customer_id: customerId || null,
      customer_name: form.customer_name || null,
      customer_email: form.customer_email || null,
      material_type: form.material_type || null,
      color: form.color || null,
      customer_notes: form.customer_notes || null,
      admin_notes: form.admin_notes || null,
      apply_tax: form.apply_tax,
      shipping_cost: form.shipping_cost ? parseFloat(form.shipping_cost) : null,
    };

    // Only include valid_days for new quotes (not updates)
    if (!quote) {
      payload.valid_days = form.valid_days;
    }

    try {
      await onSave(payload);
    } finally {
      setSaving(false);
    }
  };

  // Handle customer selection from dropdown
  const handleCustomerSelect = (e) => {
    const customerId = e.target.value ? parseInt(e.target.value) : null;
    if (customerId) {
      const customer = customers.find((c) => c.id === customerId);
      if (customer) {
        setForm((f) => ({
          ...f,
          customer_id: customerId,
          customer_name: `${customer.first_name || ""} ${customer.last_name || ""}`.trim() || customer.email,
          customer_email: customer.email || "",
        }));
      }
    } else {
      setForm((f) => ({ ...f, customer_id: null }));
    }
  };

  // Calculate totals preview
  const subtotal = (parseFloat(form.unit_price) || 0) * (form.quantity || 1);
  const taxRate = form.apply_tax && companySettings?.tax_rate_percent ? companySettings.tax_rate_percent / 100 : 0;
  const taxAmount = subtotal * taxRate;
  const shippingCost = parseFloat(form.shipping_cost) || 0;
  const grandTotal = subtotal + taxAmount + shippingCost;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
        <div className="fixed inset-0 bg-black/70" onClick={onClose} />
        <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-3xl w-full mx-auto p-6">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-semibold text-white">
              {quote ? "Edit Quote" : "New Quote"} - Step {step} of 2
            </h3>
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Step indicator */}
          <div className="flex gap-2 mb-6">
            <div className={`flex-1 h-1 rounded ${step >= 1 ? "bg-blue-500" : "bg-gray-700"}`} />
            <div className={`flex-1 h-1 rounded ${step >= 2 ? "bg-blue-500" : "bg-gray-700"}`} />
          </div>

          {step === 1 && (
            <div className="space-y-4">
              <div>
                <h4 className="text-white font-medium mb-2">Select Product</h4>
                <p className="text-gray-400 text-sm mb-4">
                  Choose an existing product with BOM, or{" "}
                  <button
                    onClick={() => navigate("/admin/items?action=new")}
                    className="text-blue-400 hover:underline"
                  >
                    create a new product first
                  </button>
                </p>
              </div>

              {/* Product Search */}
              <div className="relative">
                <input
                  type="text"
                  placeholder="Search products by SKU or name..."
                  value={productSearch}
                  onChange={(e) => setProductSearch(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white pl-10"
                />
                <svg
                  className="w-5 h-5 absolute left-3 top-3.5 text-gray-500"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>

              {/* Product Grid */}
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 max-h-[400px] overflow-auto">
                {loading ? (
                  <div className="col-span-full flex justify-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                  </div>
                ) : filteredProducts.length === 0 ? (
                  <div className="col-span-full text-center py-8 text-gray-500">
                    {productSearch.trim()
                      ? `No products with BOM found matching "${productSearch}"`
                      : "No products with BOM available. Create a product with BOM first."}
                  </div>
                ) : (
                  filteredProducts.map((product) => (
                    <button
                      key={product.id}
                      onClick={() => handleSelectProduct(product)}
                      className={`text-left p-4 bg-gray-800 border rounded-lg hover:border-blue-500 transition-colors ${
                        selectedProduct?.id === product.id
                          ? "border-blue-500 bg-blue-900/20"
                          : "border-gray-700"
                      }`}
                    >
                      <div className="text-white font-medium truncate">{product.name}</div>
                      <div className="text-gray-500 text-xs font-mono mt-1">{product.sku}</div>
                      <div className="flex justify-between items-center mt-2">
                        <span className="text-green-400 font-medium">
                          ${parseFloat(product.selling_price || 0).toFixed(2)}
                        </span>
                        <span className="text-xs text-blue-400">Has BOM</span>
                      </div>
                    </button>
                  ))
                )}
              </div>

              <div className="flex justify-end pt-4 border-t border-gray-700">
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Selected Product */}
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex justify-between items-start">
                  <div>
                    <h4 className="text-white font-medium">{form.product_name}</h4>
                    <p className="text-gray-400 text-sm">{selectedProduct?.sku ?? quote?.product_sku ?? ""}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="text-blue-400 text-sm hover:underline"
                  >
                    Change
                  </button>
                </div>
              </div>

              {/* Quantity & Price */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Quantity *</label>
                  <input
                    type="number"
                    min="1"
                    value={form.quantity}
                    onChange={(e) => setForm((f) => ({ ...f, quantity: parseInt(e.target.value) || 1 }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Unit Price *</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={form.unit_price}
                    onChange={(e) => setForm((f) => ({ ...f, unit_price: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    required
                  />
                </div>
              </div>

              {/* Customer Info */}
              <div className="border-t border-gray-700 pt-4">
                <h4 className="text-sm font-medium text-gray-300 mb-3">Customer Information</h4>

                {/* Customer Selection Dropdown */}
                {customers.length > 0 && (
                  <div className="mb-4">
                    <label className="block text-sm text-gray-400 mb-1">Select Existing Customer</label>
                    <select
                      value={form.customer_id || ""}
                      onChange={handleCustomerSelect}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    >
                      <option value="">-- Enter customer manually --</option>
                      {customers.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.first_name} {c.last_name} ({c.email})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Customer Name</label>
                    <input
                      type="text"
                      value={form.customer_name}
                      onChange={(e) => setForm((f) => ({ ...f, customer_name: e.target.value }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Customer Email</label>
                    <input
                      type="email"
                      value={form.customer_email}
                      onChange={(e) => setForm((f) => ({ ...f, customer_email: e.target.value }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    />
                  </div>
                </div>

                {/* Save as new customer option - only show if not already a customer */}
                {!form.customer_id && form.customer_email && (
                  <div className="mt-3">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={saveAsCustomer}
                        onChange={(e) => setSaveAsCustomer(e.target.checked)}
                        className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-600"
                      />
                      <span className="text-sm text-gray-300">
                        Save as new customer record
                      </span>
                    </label>
                  </div>
                )}
              </div>

              {/* Tax & Shipping */}
              <div className="border-t border-gray-700 pt-4 space-y-4">
                {companySettings?.tax_enabled && (
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="apply_tax"
                      checked={form.apply_tax || false}
                      onChange={(e) => setForm((f) => ({ ...f, apply_tax: e.target.checked }))}
                      className="w-5 h-5 rounded bg-gray-700 border-gray-600 text-blue-600"
                    />
                    <label htmlFor="apply_tax" className="text-white">
                      Apply {companySettings.tax_name || "Sales Tax"} ({companySettings.tax_rate_percent?.toFixed(2)}%)
                    </label>
                  </div>
                )}
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Shipping Cost</label>
                  <div className="relative w-40">
                    <span className="absolute left-3 top-2 text-gray-400">$</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={form.shipping_cost}
                      onChange={(e) => setForm((f) => ({ ...f, shipping_cost: e.target.value }))}
                      placeholder="0.00"
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 pl-7 text-white"
                    />
                  </div>
                </div>
              </div>

              {/* Notes */}
              <div className="border-t border-gray-700 pt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Customer Notes</label>
                    <textarea
                      value={form.customer_notes}
                      onChange={(e) => setForm((f) => ({ ...f, customer_notes: e.target.value }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                      rows={2}
                      placeholder="Special requests..."
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Internal Notes</label>
                    <textarea
                      value={form.admin_notes}
                      onChange={(e) => setForm((f) => ({ ...f, admin_notes: e.target.value }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                      rows={2}
                      placeholder="Internal notes..."
                    />
                  </div>
                </div>
              </div>

              {/* Valid Days */}
              {!quote && (
                <div>
                  <label className="block text-sm text-gray-400 mb-1">Quote Valid For (days)</label>
                  <input
                    type="number"
                    min="1"
                    max="365"
                    value={form.valid_days}
                    onChange={(e) => setForm((f) => ({ ...f, valid_days: parseInt(e.target.value) || 30 }))}
                    className="w-32 bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                  />
                </div>
              )}

              {/* Total Preview with Tax & Shipping Breakdown */}
              <div className="bg-gray-800 rounded-lg p-4 space-y-2">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-gray-400">Subtotal:</span>
                  <span className="text-white">${subtotal.toFixed(2)}</span>
                </div>
                {form.apply_tax && taxAmount > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-400">
                      {companySettings?.tax_name || "Tax"} ({companySettings?.tax_rate_percent?.toFixed(2)}%):
                    </span>
                    <span className="text-white">${taxAmount.toFixed(2)}</span>
                  </div>
                )}
                {shippingCost > 0 && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-gray-400">Shipping:</span>
                    <span className="text-white">${shippingCost.toFixed(2)}</span>
                  </div>
                )}
                <div className="flex justify-between items-center pt-2 border-t border-gray-700">
                  <span className="text-gray-400 font-medium">Total:</span>
                  <span className="text-2xl font-bold text-green-400">${grandTotal.toFixed(2)}</span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex justify-between gap-3 pt-4 border-t border-gray-700">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
                >
                  Back
                </button>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                  >
                    {saving ? "Saving..." : quote ? "Update Quote" : "Create Quote"}
                  </button>
                </div>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
