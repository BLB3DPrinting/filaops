/**
 * POCreateModal - Create/Edit purchase order form
 *
 * Features:
 * - Searchable product selection with ProductSearchSelect
 * - Auto-populate cost from product's last_cost
 * - Enhanced line item management
 * - Running totals display
 * - Quick create new item inline
 */
import { useState, useEffect } from "react";
import { useToast } from "../Toast";
import Modal from "../Modal";
import ProductSearchSelect from "./ProductSearchSelect";
import QuickCreateItemModal from "./QuickCreateItemModal";
import { convertUOM } from "../../lib/uom";

export default function POCreateModal({
  po,
  vendors,
  products = [],
  onClose,
  onSave,
  onProductsRefresh,
  initialItems = [], // Pre-selected items from low stock
  companySettings = null, // For auto-calc tax
}) {
  const toast = useToast();
  const [showCreateItemModal, setShowCreateItemModal] = useState(false);
  const [createItemInitialName, setCreateItemInitialName] = useState("");
  const [pendingLineIndex, setPendingLineIndex] = useState(null);
  const [localProducts, setLocalProducts] = useState(products);
  const [taxOverridden, setTaxOverridden] = useState(false); // Track if user manually changed tax

  // Sync localProducts only on initial load (when still empty) to avoid
  // overwriting items added via Quick Create while a fetch is in-flight
  useEffect(() => {
    if (products.length > 0 && localProducts.length === 0) {
      setLocalProducts(products);
    }
  }, [products]);

  // Build initial lines from initialItems or existing PO
  const buildInitialLines = () => {
    if (po?.lines?.length > 0) {
      return po.lines.map((l) => ({
        product_id: l.product_id,
        product_sku: l.product_sku,
        product_name: l.product_name,
        product_unit: l.product_unit || "",
        quantity_ordered: l.quantity_ordered,
        purchase_unit: l.purchase_unit || l.product_unit || "",
        unit_cost: l.unit_cost,
        notes: l.notes || "",
      }));
    }
    if (initialItems.length > 0) {
      return initialItems.map((item) => ({
        product_id: item.id,
        product_sku: item.sku,
        product_name: item.name,
        product_unit: item.unit || "EA",
        quantity_ordered: item.shortfall || item.reorder_qty || 1,
        purchase_unit: item.unit || "EA",
        unit_cost: item.last_cost || item.cost || 0,
        notes: "",
      }));
    }
    return [];
  };

  const [form, setForm] = useState({
    vendor_id: po?.vendor_id || "",
    order_date: po?.order_date || new Date().toISOString().split("T")[0], // Default to today
    expected_date: po?.expected_date || "",
    tracking_number: po?.tracking_number || "",
    carrier: po?.carrier || "",
    tax_amount: po?.tax_amount || "0",
    shipping_cost: po?.shipping_cost || "0",
    payment_method: po?.payment_method || "",
    payment_reference: po?.payment_reference || "",
    document_url: po?.document_url || "",
    notes: po?.notes || "",
    lines: buildInitialLines(),
  });

  // Calculate line total for auto-tax
  const lineTotal = form.lines.reduce(
    (sum, l) =>
      sum +
      (parseFloat(l.quantity_ordered) || 0) * (parseFloat(l.unit_cost) || 0),
    0
  );

  // Calculate suggested tax based on company settings
  const suggestedTax = companySettings?.tax_rate_percent && !po
    ? (lineTotal * (parseFloat(companySettings.tax_rate_percent) / 100)).toFixed(2)
    : null;

  // Get effective tax amount (use suggested if not overridden)
  const effectiveTaxAmount = !taxOverridden && suggestedTax !== null
    ? suggestedTax
    : form.tax_amount;

  const addLine = () => {
    setForm({
      ...form,
      lines: [
        ...form.lines,
      {
        product_id: "",
        product_sku: "",
        product_name: "",
        product_unit: "",
        quantity_ordered: 1,
        purchase_unit: "",
        unit_cost: 0,
        notes: "",
      },
      ],
    });
  };

  const removeLine = (index) => {
    setForm({
      ...form,
      lines: form.lines.filter((_, i) => i !== index),
    });
  };

  const updateLine = (index, field, value) => {
    const newLines = [...form.lines];
    newLines[index] = { ...newLines[index], [field]: value };
    setForm({ ...form, lines: newLines });
  };

  // UOM conversion now uses shared lib/uom.js

  const handleProductSelect = (index, productId, product) => {
    const newLines = [...form.lines];
    const currentLine = newLines[index];
    
    if (product) {
      const productUnit = product.unit || 'EA';
      const hadProduct = currentLine.product_id && currentLine.product_id !== "";
      const currentPurchaseUnit = currentLine.purchase_unit || (hadProduct ? currentLine.purchase_unit : productUnit);
      const currentQty = parseFloat(currentLine.quantity_ordered) || 1;
      
      // If product changed, convert quantity from old purchase_unit to new product_unit
      let convertedQty = currentQty;
      let finalPurchaseUnit = productUnit; // Default to product's unit for new selections
      
      if (hadProduct && currentLine.product_id !== productId) {
        // Product changed - convert quantity and keep current purchase_unit if set
        finalPurchaseUnit = currentPurchaseUnit || productUnit;
        if (currentPurchaseUnit && currentPurchaseUnit !== productUnit) {
          convertedQty = convertUOM(currentQty, currentPurchaseUnit, productUnit);
        }
      } else if (!hadProduct) {
        // New product selection - use product's unit
        finalPurchaseUnit = productUnit;
      } else {
        // Same product - keep current purchase_unit
        finalPurchaseUnit = currentPurchaseUnit || productUnit;
      }
      
      newLines[index] = {
        ...newLines[index],
        product_id: productId,
        product_sku: product.sku,
        product_name: product.name,
        product_unit: productUnit,
        purchase_unit: finalPurchaseUnit,
        quantity_ordered: convertedQty,
        // Auto-populate unit_cost from product's last_cost if available
        unit_cost:
          product.last_cost || product.cost || newLines[index].unit_cost,
      };
    } else {
      newLines[index] = {
        ...newLines[index],
        product_id: "",
        product_sku: "",
        product_name: "",
        product_unit: "",
        purchase_unit: "",
      };
    }
    setForm({ ...form, lines: newLines });
  };

  // Handler for opening quick create item modal
  const handleCreateNewItem = (index, searchText) => {
    setPendingLineIndex(index);
    setCreateItemInitialName(searchText);
    setShowCreateItemModal(true);
  };

  // Handler for when a new item is created
  const handleItemCreated = (newItem) => {
    // Add the new item to local products list
    setLocalProducts([...localProducts, newItem]);

    // If we have a pending line, select this item for it
    if (pendingLineIndex !== null) {
      const newLines = [...form.lines];
      newLines[pendingLineIndex] = {
        ...newLines[pendingLineIndex],
        product_id: newItem.id,
        product_sku: newItem.sku,
        product_name: newItem.name,
        product_unit: newItem.unit || 'EA',
        purchase_unit: newItem.unit || 'EA',
        unit_cost:
          newItem.last_cost ||
          newItem.cost ||
          newLines[pendingLineIndex].unit_cost ||
          0,
      };
      setForm({ ...form, lines: newLines });
    }

    // Notify parent to refresh products list
    if (onProductsRefresh) {
      onProductsRefresh();
    }

    // Close modal and reset state
    setShowCreateItemModal(false);
    setPendingLineIndex(null);
    setCreateItemInitialName("");
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.vendor_id) {
      toast.warning("Please select a vendor");
      return;
    }
    if (!po && form.lines.length === 0) {
      toast.warning("Please add at least one line item");
      return;
    }

    // Validate all lines have products selected
    const invalidLines = form.lines.filter((l) => !l.product_id);
    if (invalidLines.length > 0) {
      toast.warning("Please select a product for all line items");
      return;
    }

    const data = {
      vendor_id: parseInt(form.vendor_id),
      order_date: form.order_date || null,
      expected_date: form.expected_date || null,
      tracking_number: form.tracking_number || null,
      carrier: form.carrier || null,
      tax_amount: parseFloat(effectiveTaxAmount) || 0,
      shipping_cost: parseFloat(form.shipping_cost) || 0,
      payment_method: form.payment_method || null,
      payment_reference: form.payment_reference || null,
      document_url: form.document_url || null,
      notes: form.notes || null,
    };

    if (!po) {
      // New PO - include lines
      data.lines = form.lines.map((l) => ({
        product_id: parseInt(l.product_id),
        quantity_ordered: parseFloat(l.quantity_ordered),
        purchase_unit: l.purchase_unit || l.product_unit || null,
        unit_cost: parseFloat(l.unit_cost),
        notes: l.notes || null,
      }));
    }

    onSave(data);
  };

  const grandTotal =
    lineTotal +
    (parseFloat(effectiveTaxAmount) || 0) +
    (parseFloat(form.shipping_cost) || 0);

  // Get selected vendor for display
  const selectedVendor = vendors.find(
    (v) => String(v.id) === String(form.vendor_id)
  );

  return (
    <Modal isOpen={true} onClose={onClose} title={po ? `Edit PO ${po.po_number}` : "New Purchase Order"} className="max-w-4xl w-full mx-auto p-6 max-h-[90vh] overflow-y-auto">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="text-xl font-semibold text-white">
                {po ? `Edit PO ${po.po_number}` : "New Purchase Order"}
              </h3>
              {selectedVendor && (
                <p className="text-sm text-gray-400 mt-1">
                  Vendor: {selectedVendor.name}
                </p>
              )}
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1"
            >
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-6">
            {/* Header Info */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Vendor *
                </label>
                <select
                  value={form.vendor_id}
                  onChange={(e) =>
                    setForm({ ...form, vendor_id: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white"
                  required
                >
                  <option value="">Select vendor...</option>
                  {vendors
                    .filter((v) => v.is_active)
                    .map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} ({v.code})
                      </option>
                    ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Order Date
                </label>
                <input
                  type="date"
                  value={form.order_date}
                  onChange={(e) =>
                    setForm({ ...form, order_date: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white"
                  min="2000-01-01"
                  max="2099-12-31"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Expected Date
                </label>
                <input
                  type="date"
                  value={form.expected_date}
                  onChange={(e) =>
                    setForm({ ...form, expected_date: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5 text-white"
                  min="2000-01-01"
                  max="2099-12-31"
                />
              </div>
            </div>

            {/* Line Items - only for new POs */}
            {!po && (
              <div className="border-t border-gray-800 pt-4">
                <div className="flex justify-between items-center mb-3">
                  <h4 className="text-sm font-medium text-gray-300 flex items-center gap-2">
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                      />
                    </svg>
                    Line Items ({form.lines.length})
                  </h4>
                  <button
                    type="button"
                    onClick={addLine}
                    className="px-3 py-1.5 bg-blue-600/20 hover:bg-blue-600/30 text-blue-400 rounded-lg text-sm font-medium transition-colors flex items-center gap-1"
                  >
                    <svg
                      className="w-4 h-4"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 4v16m8-8H4"
                      />
                    </svg>
                    Add Line
                  </button>
                </div>

                {/* Table Header */}
                {form.lines.length > 0 && (
                  <div className="grid grid-cols-12 gap-2 px-3 py-2 text-xs text-gray-400 font-medium border-b border-gray-800">
                    <div className="col-span-4">Product</div>
                    <div className="col-span-2 text-right">Qty</div>
                    <div className="col-span-1 text-center">UOM</div>
                    <div className="col-span-2 text-right">Unit Cost</div>
                    <div className="col-span-2 text-right">Total</div>
                    <div className="col-span-1"></div>
                  </div>
                )}

                <div className="space-y-2 mt-2">
                  {form.lines.map((line, index) => (
                    <div
                      key={index}
                      className="grid grid-cols-12 gap-2 items-center bg-gray-800/30 p-3 rounded-lg group hover:bg-gray-800/50 transition-colors"
                    >
                      {/* Product Search */}
                      <div className="col-span-4">
                        <ProductSearchSelect
                          value={line.product_id}
                          products={localProducts}
                          onChange={(productId, product) =>
                            handleProductSelect(index, productId, product)
                          }
                          onCreateNew={(searchText) =>
                            handleCreateNewItem(index, searchText)
                          }
                          placeholder="Search products..."
                        />
                      </div>

                      {/* Quantity */}
                      <div className="col-span-2">
                        <input
                          type="number"
                          value={line.quantity_ordered}
                          onChange={(e) =>
                            updateLine(index, "quantity_ordered", e.target.value)
                          }
                          placeholder="Qty"
                          min="0.01"
                          step="0.01"
                          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-right"
                          required
                        />
                      </div>

                      {/* UOM Dropdown */}
                      <div className="col-span-1">
                        <select
                          value={line.purchase_unit || line.product_unit || ""}
                          onChange={(e) => {
                            const newUnit = e.target.value;
                            const oldUnit = line.purchase_unit || line.product_unit || 'EA';
                            const currentQty = parseFloat(line.quantity_ordered) || 0;
                            
                            // Convert quantity when UOM changes
                            const convertedQty = convertUOM(currentQty, oldUnit, newUnit);
                            
                            // Update both fields in a single state update to avoid race conditions
                            const newLines = [...form.lines];
                            newLines[index] = {
                              ...newLines[index],
                              purchase_unit: newUnit,
                              quantity_ordered: convertedQty,
                            };
                            setForm({ ...form, lines: newLines });
                          }}
                          className="w-full bg-gray-700 border border-gray-600 rounded-lg px-2 py-2 text-white text-sm"
                          disabled={!line.product_id}
                        >
                          <option value="">-</option>
                          <option value="EA">EA</option>
                          <option value="G">G</option>
                          <option value="KG">KG</option>
                          <option value="LB">LB</option>
                          <option value="OZ">OZ</option>
                          <option value="PK">PK</option>
                          <option value="BOX">BOX</option>
                          <option value="ROLL">ROLL</option>
                        </select>
                      </div>

                      {/* Unit Cost */}
                      <div className="col-span-2">
                        <div className="relative">
                          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                            $
                          </span>
                          <input
                            type="number"
                            value={line.unit_cost}
                            onChange={(e) =>
                              updateLine(index, "unit_cost", e.target.value)
                            }
                            placeholder="0.00"
                            min="0"
                            step="0.0001"
                            className="w-full bg-gray-700 border border-gray-600 rounded-lg pl-7 pr-3 py-2 text-white text-right"
                            required
                          />
                        </div>
                      </div>

                      {/* Line Total */}
                      <div className="col-span-2 text-right">
                        <span className="text-white font-medium">
                          $
                          {(
                            (parseFloat(line.quantity_ordered) || 0) *
                            (parseFloat(line.unit_cost) || 0)
                          ).toFixed(2)}
                        </span>
                      </div>

                      {/* Remove Button */}
                      <div className="col-span-1 text-right">
                        <button
                          type="button"
                          onClick={() => removeLine(index)}
                          className="p-1.5 text-gray-500 hover:text-red-400 hover:bg-red-600/10 rounded transition-colors opacity-0 group-hover:opacity-100"
                        >
                          <svg
                            className="w-4 h-4"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                            />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}

                  {form.lines.length === 0 && (
                    <div className="text-center py-8 bg-gray-800/20 rounded-lg border-2 border-dashed border-gray-700">
                      <svg
                        className="w-12 h-12 mx-auto text-gray-600 mb-3"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                        />
                      </svg>
                      <p className="text-gray-400 mb-2">No line items yet</p>
                      <button
                        type="button"
                        onClick={addLine}
                        className="text-blue-400 hover:text-blue-300 text-sm font-medium"
                      >
                        + Add your first item
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Financials */}
            <div className="grid grid-cols-4 gap-4 border-t border-gray-800 pt-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1 flex items-center justify-between">
                  <span>Tax Amount</span>
                  {companySettings?.tax_rate_percent && (
                    <span className="text-xs text-gray-500">
                      {taxOverridden ? (
                        <button
                          type="button"
                          onClick={() => {
                            setTaxOverridden(false);
                            const taxRate = parseFloat(companySettings.tax_rate_percent) / 100;
                            const calculatedTax = (lineTotal * taxRate).toFixed(2);
                            setForm((prev) => ({ ...prev, tax_amount: calculatedTax }));
                          }}
                          className="text-blue-400 hover:text-blue-300"
                        >
                          Reset to {companySettings.tax_rate_percent}%
                        </button>
                      ) : (
                        `Auto: ${companySettings.tax_rate_percent}%`
                      )}
                    </span>
                  )}
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                    $
                  </span>
                  <input
                    type="number"
                    value={effectiveTaxAmount}
                    onChange={(e) => {
                      setTaxOverridden(true);
                      setForm({ ...form, tax_amount: e.target.value });
                    }}
                    min="0"
                    step="0.01"
                    className={`w-full bg-gray-800 border rounded-lg pl-7 pr-3 py-2 text-white ${
                      taxOverridden ? "border-yellow-600/50" : "border-gray-700"
                    }`}
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Shipping Cost
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                    $
                  </span>
                  <input
                    type="number"
                    value={form.shipping_cost}
                    onChange={(e) =>
                      setForm({ ...form, shipping_cost: e.target.value })
                    }
                    min="0"
                    step="0.01"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-7 pr-3 py-2 text-white"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Payment Method
                </label>
                <input
                  type="text"
                  value={form.payment_method}
                  onChange={(e) =>
                    setForm({ ...form, payment_method: e.target.value })
                  }
                  placeholder="Card, Check, etc."
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Payment Ref
                </label>
                <input
                  type="text"
                  value={form.payment_reference}
                  onChange={(e) =>
                    setForm({ ...form, payment_reference: e.target.value })
                  }
                  placeholder="Last 4, Check #"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
            </div>

            {/* Document & Tracking */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Document URL
                </label>
                <input
                  type="text"
                  value={form.document_url}
                  onChange={(e) =>
                    setForm({ ...form, document_url: e.target.value })
                  }
                  placeholder="Google Drive link, etc."
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Tracking Number
                </label>
                <input
                  type="text"
                  value={form.tracking_number}
                  onChange={(e) =>
                    setForm({ ...form, tracking_number: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Carrier
                </label>
                <input
                  type="text"
                  value={form.carrier}
                  onChange={(e) =>
                    setForm({ ...form, carrier: e.target.value })
                  }
                  placeholder="UPS, FedEx, etc."
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
            </div>

            {/* Notes */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Notes</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                rows={2}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
            </div>

            {/* Totals */}
            {!po && form.lines.length > 0 && (
              <div className="bg-gradient-to-r from-gray-800/50 to-gray-800/30 p-4 rounded-lg">
                <div className="flex justify-end">
                  <div className="text-right space-y-1">
                    <div className="text-sm text-gray-400">
                      Subtotal ({form.lines.length} items):{" "}
                      <span className="text-white">
                        ${lineTotal.toFixed(2)}
                      </span>
                    </div>
                    {parseFloat(effectiveTaxAmount) > 0 && (
                      <div className="text-sm text-gray-400">
                        Tax:{" "}
                        <span className="text-white">
                          ${parseFloat(effectiveTaxAmount).toFixed(2)}
                        </span>
                      </div>
                    )}
                    {parseFloat(form.shipping_cost) > 0 && (
                      <div className="text-sm text-gray-400">
                        Shipping:{" "}
                        <span className="text-white">
                          ${parseFloat(form.shipping_cost).toFixed(2)}
                        </span>
                      </div>
                    )}
                    <div className="text-lg font-semibold text-white pt-1 border-t border-gray-700">
                      Total: ${grandTotal.toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-between items-center pt-4 border-t border-gray-800">
              <div className="text-sm text-gray-400">
                {!po && form.lines.length > 0 && (
                  <>
                    {form.lines.length} item{form.lines.length !== 1 ? "s" : ""}{" "}
                    in order
                  </>
                )}
              </div>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-6 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium flex items-center gap-2"
                >
                  {po ? (
                    <>
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M5 13l4 4L19 7"
                        />
                      </svg>
                      Save Changes
                    </>
                  ) : (
                    <>
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 4v16m8-8H4"
                        />
                      </svg>
                      Create PO
                    </>
                  )}
                </button>
              </div>
            </div>
          </form>

      {/* Quick Create Item Modal */}
      {showCreateItemModal && (
        <QuickCreateItemModal
          onClose={() => {
            setShowCreateItemModal(false);
            setPendingLineIndex(null);
            setCreateItemInitialName("");
          }}
          onCreated={handleItemCreated}
          initialName={createItemInitialName}
        />
      )}
    </Modal>
  );
}
