/**
 * QuoteFormModal - 2-step form for creating/editing quotes.
 *
 * Step 1: Select one or more products (multi-line support).
 * Step 2: Customer info, tax, shipping, notes.
 *
 * Extracted from AdminQuotes.jsx (ARCHITECT-002), extended for multi-line quotes.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";

export default function QuoteFormModal({ quote, onSave, onClose }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [step, setStep] = useState(quote ? 2 : 1);
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [companySettings, setCompanySettings] = useState(null);
  const [taxRates, setTaxRates] = useState([]);
  const [productSearch, setProductSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveAsCustomer, setSaveAsCustomer] = useState(false);

  // Multi-line items state
  const [lineItems, setLineItems] = useState(() => {
    if (quote?.lines?.length > 0) {
      return quote.lines.map((l) => ({
        product_id: l.product_id,
        product_name: l.product_name,
        product_sku: "",
        quantity: l.quantity,
        unit_price: l.unit_price,
        material_type: l.material_type || "",
        color: l.color || "",
        notes: l.notes || "",
      }));
    }
    if (quote?.product_name) {
      return [{
        product_id: quote.product_id,
        product_name: quote.product_name,
        product_sku: "",
        quantity: quote.quantity || 1,
        unit_price: quote.unit_price || "",
        material_type: quote.material_type || "",
        color: quote.color || "",
        notes: "",
      }];
    }
    return [];
  });

  // Customer discount from price level (PRO feature, gracefully degrades)
  const [customerDiscount, setCustomerDiscount] = useState(null);

  const [form, setForm] = useState({
    customer_id: quote?.customer_id || null,
    customer_name: quote?.customer_name || "",
    customer_email: quote?.customer_email || "",
    customer_notes: quote?.customer_notes || "",
    admin_notes: quote?.admin_notes || "",
    apply_tax: quote?.tax_rate ? true : null,
    tax_rate_id: null,
    shipping_cost: quote?.shipping_cost || "",
    valid_days: 30,
  });

  useEffect(() => {
    fetchProducts();
    fetchCustomers();
    fetchCompanySettings();
    fetchTaxRates();
  }, []);

  // Fetch customer discount when customer changes
  useEffect(() => {
    if (!form.customer_id) {
      setCustomerDiscount(null);
      return;
    }
    const fetchDiscount = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/pro/catalogs/price-levels`, {
          credentials: "include",
        });
        if (res.ok) {
          const levels = await res.json();
          const assigned = (Array.isArray(levels) ? levels : []).find((l) =>
            l.customers?.some((c) => c.customer_id === form.customer_id)
          );
          setCustomerDiscount(
            assigned && assigned.discount_percent > 0
              ? assigned.discount_percent
              : null
          );
        } else {
          setCustomerDiscount(null);
        }
      } catch {
        // PRO not installed or endpoint unavailable
        setCustomerDiscount(null);
      }
    };
    fetchDiscount();
  }, [form.customer_id]);

  const fetchProducts = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/items?limit=500&active_only=true&item_type=finished_good`, {
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
      // Non-critical
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
        if (form.apply_tax === null && !quote) {
          setForm((f) => ({ ...f, apply_tax: data.tax_enabled }));
        }
      }
    } catch {
      // Non-critical
    }
  };

  const fetchTaxRates = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/tax-rates`, { credentials: "include" });
      if (res.ok) setTaxRates(await res.json());
    } catch {
      // Non-critical
    }
  };

  // Filter products — show all active finished goods (no BOM/routing filter)
  const filteredProducts = products.filter((p) => {
    if (!productSearch.trim()) return true;
    const search = productSearch.toLowerCase();
    return (
      (p.name || "").toLowerCase().includes(search) ||
      (p.sku || "").toLowerCase().includes(search)
    );
  });

  // Add product to line items (or increment qty if already present)
  const handleAddProduct = (product) => {
    setLineItems((prev) => {
      const existing = prev.find((li) => li.product_id === product.id);
      if (existing) {
        return prev.map((li) =>
          li.product_id === product.id
            ? { ...li, quantity: li.quantity + 1 }
            : li
        );
      }
      return [
        ...prev,
        {
          product_id: product.id,
          product_name: product.name,
          product_sku: product.sku,
          quantity: 1,
          unit_price: product.selling_price ?? "",
          material_type: "",
          color: "",
          notes: "",
        },
      ];
    });
  };

  const handleRemoveLine = (index) => {
    setLineItems((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpdateLine = (index, field, value) => {
    setLineItems((prev) =>
      prev.map((li, i) => (i === index ? { ...li, [field]: value } : li))
    );
  };

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

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (lineItems.length === 0) {
      toast.error("Add at least one product");
      return;
    }

    for (const li of lineItems) {
      if (!li.product_name || li.unit_price === "" || li.unit_price === null || isNaN(Number(li.unit_price))) {
        toast.error("Each line item needs a product name and unit price");
        return;
      }
    }

    if (saveAsCustomer && !form.customer_email) {
      toast.error("Customer email is required to save as new customer");
      return;
    }

    setSaving(true);

    // Create customer if needed
    let customerId = form.customer_id;
    if (saveAsCustomer && !customerId && form.customer_email) {
      try {
        const nameParts = (form.customer_name || "").trim().split(" ");
        const firstName = nameParts[0] || "";
        const lastName = nameParts.slice(1).join(" ") || "";

        const customerRes = await fetch(`${API_URL}/api/v1/admin/customers`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
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
          if (err.detail?.includes("already exists")) {
            toast.info("Customer already exists, linking to quote");
          }
        }
      } catch (err) {
        console.error("Failed to create customer:", err);
      }
    }

    // Build payload with lines array
    const payload = {
      lines: lineItems.map((li) => ({
        product_id: li.product_id || null,
        product_name: li.product_name,
        quantity: li.quantity,
        unit_price: parseFloat(li.unit_price),
        material_type: li.material_type || null,
        color: li.color || null,
        notes: li.notes || null,
      })),
      customer_id: customerId || null,
      customer_name: form.customer_name || null,
      customer_email: form.customer_email || null,
      customer_notes: form.customer_notes || null,
      admin_notes: form.admin_notes || null,
      apply_tax: form.apply_tax,
      tax_rate_id: form.tax_rate_id || null,
      shipping_cost: form.shipping_cost ? parseFloat(form.shipping_cost) : null,
    };

    if (!quote) {
      payload.valid_days = form.valid_days;
    }

    try {
      await onSave(payload);
    } finally {
      setSaving(false);
    }
  };

  // Calculate totals
  const subtotal = lineItems.reduce(
    (sum, li) => sum + (parseFloat(li.unit_price) || 0) * (li.quantity || 1),
    0
  );
  const taxRate = form.apply_tax && companySettings?.tax_rate_percent ? companySettings.tax_rate_percent / 100 : 0;
  const taxAmount = subtotal * taxRate;
  const shippingCost = parseFloat(form.shipping_cost) || 0;
  const grandTotal = subtotal + taxAmount + shippingCost;

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex items-center justify-center min-h-screen px-4 pt-4 pb-20">
        <div className="fixed inset-0 bg-black/70" onClick={onClose} />
        <div className="relative bg-gray-900 border border-gray-700 rounded-xl shadow-xl max-w-4xl w-full mx-auto p-6">
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
                <h4 className="text-white font-medium mb-2">Add Products</h4>
                <p className="text-gray-400 text-sm mb-4">
                  Select products for this quote, or{" "}
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
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 max-h-[300px] overflow-auto">
                {loading ? (
                  <div className="col-span-full flex justify-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                  </div>
                ) : filteredProducts.length === 0 ? (
                  <div className="col-span-full text-center py-8 text-gray-500">
                    {productSearch.trim()
                      ? `No products found matching "${productSearch}"`
                      : "No finished goods available."}
                  </div>
                ) : (
                  filteredProducts.map((product) => {
                    const inCart = lineItems.some((li) => li.product_id === product.id);
                    return (
                      <button
                        key={product.id}
                        onClick={() => handleAddProduct(product)}
                        className={`text-left p-4 bg-gray-800 border rounded-lg hover:border-blue-500 transition-colors ${
                          inCart ? "border-blue-500 bg-blue-900/20" : "border-gray-700"
                        }`}
                      >
                        <div className="text-white font-medium truncate">{product.name}</div>
                        <div className="text-gray-500 text-xs font-mono mt-1">{product.sku}</div>
                        <div className="flex justify-between items-center mt-2">
                          <span className="text-green-400 font-medium">
                            ${parseFloat(product.selling_price || 0).toFixed(2)}
                          </span>
                          {inCart && (
                            <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">
                              Added
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>

              {/* Selected Items Table */}
              {lineItems.length > 0 && (
                <div className="border-t border-gray-700 pt-4">
                  <h4 className="text-white font-medium mb-3">
                    Selected Items ({lineItems.length})
                  </h4>
                  <div className="bg-gray-800/50 rounded-lg border border-gray-700 divide-y divide-gray-700">
                    {lineItems.map((li, idx) => (
                      <div key={idx} className="p-3 flex items-center gap-4">
                        <div className="flex-1 min-w-0">
                          <div className="text-white font-medium truncate">{li.product_name}</div>
                          {li.product_sku && (
                            <div className="text-gray-500 text-xs">{li.product_sku}</div>
                          )}
                        </div>
                        <div className="flex items-center gap-2">
                          <label className="text-gray-400 text-sm">Qty:</label>
                          <input
                            type="number"
                            min="1"
                            value={li.quantity}
                            onChange={(e) =>
                              handleUpdateLine(idx, "quantity", parseInt(e.target.value) || 1)
                            }
                            className="w-16 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm text-center"
                          />
                        </div>
                        <div className="flex items-center gap-2">
                          <label className="text-gray-400 text-sm">$</label>
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={li.unit_price}
                            onChange={(e) =>
                              handleUpdateLine(idx, "unit_price", e.target.value)
                            }
                            className="w-24 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-white text-sm text-right"
                          />
                        </div>
                        <div className="text-green-400 font-medium w-24 text-right">
                          ${((parseFloat(li.unit_price) || 0) * (li.quantity || 1)).toFixed(2)}
                        </div>
                        <button
                          onClick={() => handleRemoveLine(idx)}
                          className="text-red-400 hover:text-red-300 p-1"
                          title="Remove"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                    <div className="p-3 flex justify-between bg-gray-800/80">
                      <span className="text-white font-medium">Subtotal</span>
                      <span className="text-green-400 font-bold">${subtotal.toFixed(2)}</span>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex justify-between pt-4 border-t border-gray-700">
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  onClick={() => setStep(2)}
                  disabled={lineItems.length === 0}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Continue
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Line Items Summary */}
              <div className="bg-gray-800 rounded-lg p-4">
                <div className="flex justify-between items-center mb-3">
                  <h4 className="text-white font-medium">
                    {lineItems.length === 1
                      ? lineItems[0].product_name
                      : `${lineItems.length} items`}
                  </h4>
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="text-blue-400 text-sm hover:underline"
                  >
                    Edit Items
                  </button>
                </div>
                {lineItems.length > 1 && (
                  <div className="space-y-1">
                    {lineItems.map((li, idx) => (
                      <div key={idx} className="flex justify-between text-sm">
                        <span className="text-gray-300 truncate">
                          {li.product_name} x{li.quantity}
                        </span>
                        <span className="text-gray-400">
                          ${((parseFloat(li.unit_price) || 0) * li.quantity).toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Customer Info */}
              <div className="border-t border-gray-700 pt-4">
                <h4 className="text-sm font-medium text-gray-300 mb-3">Customer Information</h4>

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

                {/* Customer Discount Notice */}
                {customerDiscount && (
                  <div className="bg-green-900/20 border border-green-500/30 rounded-lg px-4 py-3 mb-4 flex items-center gap-2">
                    <span className="text-green-400 font-medium text-sm">
                      {customerDiscount}% customer discount will be applied
                    </span>
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
                {taxRates.length >= 2 ? (
                  <div>
                    <label className="block text-sm text-gray-400 mb-1">Tax Rate</label>
                    <select
                      value={form.tax_rate_id || ""}
                      onChange={(e) => setForm((f) => ({
                        ...f,
                        tax_rate_id: e.target.value ? parseInt(e.target.value) : null,
                        apply_tax: !!e.target.value,
                      }))}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
                    >
                      <option value="">No tax</option>
                      {taxRates.map((tr) => (
                        <option key={tr.id} value={tr.id}>
                          {tr.name} ({tr.rate_percent.toFixed(2)}%){tr.is_default ? " ★" : ""}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : companySettings?.tax_enabled && (
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

              {/* Total Preview */}
              <div className="bg-gray-800 rounded-lg p-4 space-y-2">
                <div className="flex justify-between items-center text-sm">
                  <span className="text-gray-400">Subtotal ({lineItems.length} item{lineItems.length !== 1 ? "s" : ""}):</span>
                  <span className="text-white">${subtotal.toFixed(2)}</span>
                </div>
                {customerDiscount && (
                  <div className="flex justify-between items-center text-sm">
                    <span className="text-green-400">Customer Discount ({customerDiscount}%):</span>
                    <span className="text-green-400">Applied to line prices</span>
                  </div>
                )}
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
