/**
 * OrderLineItemsTable - Line items table with inline qty/price editing.
 *
 * Extracted from OrderDetail.jsx (DEBT-1 D1-C). Markup and handlers moved
 * verbatim; edit state is local, order refresh flows via onOrderUpdated.
 */
import { useState } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../Toast";

export default function OrderLineItemsTable({ order, orderId, onOrderUpdated }) {
  const api = useApi();
  const toast = useToast();

  // Line editing state
  const [editingLineId, setEditingLineId] = useState(null);
  const [editQty, setEditQty] = useState("");
  const [editPrice, setEditPrice] = useState("");
  const [editReason, setEditReason] = useState("");
  const [savingLineEdit, setSavingLineEdit] = useState(false);
  const [removingLineId, setRemovingLineId] = useState(null);

  const handleSaveLineEdit = async (lineId) => {
    if ((editQty === "" && editPrice === "") || !editReason.trim()) return;
    setSavingLineEdit(true);
    try {
      await api.patch(`/api/v1/sales-orders/${orderId}/lines`, {
        lines: [{
          line_id: lineId,
          new_quantity: editQty !== "" ? parseFloat(editQty) : undefined,
          new_unit_price: editPrice !== "" ? parseFloat(editPrice) : undefined,
          reason: editReason,
        }],
      });
      toast.success("Line updated");
      setEditingLineId(null);
      setEditQty("");
      setEditPrice("");
      setEditReason("");
      onOrderUpdated();
    } catch (err) {
      toast.error(err.message || "Failed to update line");
    } finally {
      setSavingLineEdit(false);
    }
  };

  const handleRemoveLine = async (line) => {
    const label = line.product_name || line.material_name || line.description || `Line ${line.id}`;
    if (!window.confirm(`Remove "${label}" from this order? This cannot be undone.`)) return;
    setRemovingLineId(line.id);
    try {
      await api.del(`/api/v1/sales-orders/${orderId}/lines/${line.id}`);
      toast.success(`${label} removed from order`);
      onOrderUpdated();
    } catch (err) {
      toast.error(err.message || "Failed to remove line");
    } finally {
      setRemovingLineId(null);
    }
  };

  const canEditLines = () => {
    return order && ["pending", "confirmed", "in_production", "on_hold"].includes(order.status);
  };

  return (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-white mb-4">Line Items</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700 text-gray-400">
                <th className="text-left py-2 px-3">Product</th>
                <th className="text-left py-2 px-3">SKU</th>
                <th className="text-right py-2 px-3">Qty</th>
                <th className="text-right py-2 px-3">Shipped</th>
                <th className="text-right py-2 px-3">Unit Price</th>
                <th className="text-right py-2 px-3">Total</th>
                {canEditLines() && <th className="text-center py-2 px-3 w-16"></th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {order.lines.map((line, idx) => {
                const isEditing = editingLineId === line.id;
                const shipped = parseFloat(line.shipped_quantity || 0);
                const lineLabel = line.product_name || line.material_name || line.description || "One-time line";
                const lineCode = line.product_sku || line.material_sku || line.sku || (line.line_type === "service" ? "FEE" : "\u2014");
                return (
                  <tr key={line.id || idx}>
                    <td className="py-2 px-3 text-white">
                      {lineLabel}
                    </td>
                    <td className="py-2 px-3 text-gray-400 font-mono text-xs">
                      {lineCode}
                    </td>
                    <td className="py-2 px-3 text-right text-white">
                      {isEditing ? (
                        <input
                          type="number"
                          value={editQty}
                          onChange={(e) => setEditQty(e.target.value)}
                          min={shipped}
                          step="1"
                          className="w-20 bg-gray-800 border border-blue-500 rounded px-2 py-1 text-right text-white text-sm"
                          autoFocus
                        />
                      ) : (
                        <span className="flex items-center justify-end gap-1">
                          {line.original_quantity && parseFloat(line.original_quantity) !== parseFloat(line.quantity) && (
                            <span className="text-gray-500 line-through text-xs">{line.original_quantity}</span>
                          )}
                          {line.quantity}
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3 text-right text-gray-400">
                      {shipped > 0 ? shipped : "\u2014"}
                    </td>
                    <td className="py-2 px-3 text-right text-gray-300">
                      {isEditing ? (
                        <input
                          type="number"
                          value={editPrice}
                          onChange={(e) => setEditPrice(e.target.value)}
                          min="0"
                          step="0.01"
                          className="w-24 bg-gray-800 border border-blue-500 rounded px-2 py-1 text-right text-white text-sm"
                        />
                      ) : (
                        `$${parseFloat(line.unit_price || 0).toFixed(2)}`
                      )}
                    </td>
                    <td className="py-2 px-3 text-right text-green-400 font-medium">
                      ${parseFloat(line.total || 0).toFixed(2)}
                    </td>
                    {canEditLines() && (
                      <td className="py-2 px-3 text-center">
                        {isEditing ? (
                          <div className="flex gap-1 justify-center">
                            <button
                              onClick={() => handleSaveLineEdit(line.id)}
                              disabled={savingLineEdit || (editQty === "" && editPrice === "") || !editReason.trim()}
                              className="text-green-400 hover:text-green-300 disabled:opacity-50 text-xs"
                              title="Save"
                            >
                              {savingLineEdit ? "..." : "\u2713"}
                            </button>
                            <button
                              onClick={() => { setEditingLineId(null); setEditQty(""); setEditPrice(""); setEditReason(""); }}
                              className="text-gray-400 hover:text-white text-xs"
                              title="Cancel"
                            >
                              \u2717
                            </button>
                          </div>
                        ) : (
                          <div className="flex gap-2 justify-center">
                            <button
                              onClick={() => {
                                setEditingLineId(line.id);
                                setEditQty(String(line.quantity));
                                setEditPrice(String(line.unit_price || 0));
                                setEditReason("");
                              }}
                              className="text-gray-500 hover:text-blue-400 text-xs"
                              title="Edit line"
                            >
                              Edit
                            </button>
                            {order.lines.length > 1 && parseFloat(line.shipped_quantity || 0) === 0 && (
                              <button
                                onClick={() => handleRemoveLine(line)}
                                disabled={removingLineId === line.id}
                                className="text-gray-600 hover:text-red-400 disabled:opacity-50 text-xs"
                                title="Remove line"
                              >
                                {removingLineId === line.id ? "…" : "✕"}
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                );
              })}
              {editingLineId && (
                <tr>
                  <td colSpan={canEditLines() ? 7 : 6} className="py-2 px-3">
                    <input
                      type="text"
                      value={editReason}
                      onChange={(e) => setEditReason(e.target.value)}
                      placeholder="Reason for change (required)..."
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm placeholder-gray-500 focus:border-blue-500"
                    />
                  </td>
                </tr>
              )}
            </tbody>
            <tfoot>
              {/* Break out subtotal / tax / shipping so the Order Total
                  (grand_total) doesn't look like it disagrees with the line
                  sum. The label spans cols 1-5 and the amount sits in the
                  Total column (6); the trailing cell fills the Actions column
                  when the table is editable so nothing lands under it. */}
              <tr className="border-t border-gray-700">
                <td colSpan={5} className="py-2 px-3 text-right text-gray-400">
                  Subtotal
                </td>
                <td className="py-2 px-3 text-right text-gray-300">
                  ${parseFloat(order.total_price || 0).toFixed(2)}
                </td>
                {canEditLines() && <td />}
              </tr>
              {parseFloat(order.tax_amount || 0) > 0 && (
                <tr>
                  <td colSpan={5} className="py-1 px-3 text-right text-gray-400">
                    Tax
                  </td>
                  <td className="py-1 px-3 text-right text-gray-300">
                    ${parseFloat(order.tax_amount || 0).toFixed(2)}
                  </td>
                  {canEditLines() && <td />}
                </tr>
              )}
              {parseFloat(order.shipping_cost || 0) > 0 && (
                <tr>
                  <td colSpan={5} className="py-1 px-3 text-right text-gray-400">
                    Shipping
                  </td>
                  <td className="py-1 px-3 text-right text-gray-300">
                    ${parseFloat(order.shipping_cost || 0).toFixed(2)}
                  </td>
                  {canEditLines() && <td />}
                </tr>
              )}
              <tr className="border-t border-gray-700">
                <td colSpan={5} className="py-3 px-3 text-right text-white font-medium">
                  Order Total
                </td>
                <td className="py-3 px-3 text-right text-green-400 font-bold">
                  ${parseFloat(
                    order.grand_total ??
                      (parseFloat(order.total_price || 0) +
                        parseFloat(order.tax_amount || 0) +
                        parseFloat(order.shipping_cost || 0))
                  ).toFixed(2)}
                </td>
                {canEditLines() && <td />}
              </tr>
            </tfoot>
          </table>
        </div>
  );
}
