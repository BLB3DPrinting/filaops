/**
 * ShippingAddressSection - Shipping address display and inline edit form.
 *
 * Extracted from OrderDetail.jsx (ARCHITECT-002)
 */
import { useState } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";

export default function ShippingAddressSection({ order, onOrderUpdated }) {
  const toast = useToast();
  const [editingAddress, setEditingAddress] = useState(false);
  const [savingAddress, setSavingAddress] = useState(false);
  const [addressForm, setAddressForm] = useState({});
  const shippingCharge = Number.parseFloat(order.shipping_cost || 0);
  const grandTotal = Number.parseFloat(order.grand_total ?? order.total_price ?? 0);

  const handleEditAddress = () => {
    setAddressForm({
      shipping_address_line1: order.shipping_address_line1 || "",
      shipping_address_line2: order.shipping_address_line2 || "",
      shipping_city: order.shipping_city || "",
      shipping_state: order.shipping_state || "",
      shipping_zip: order.shipping_zip || "",
      shipping_country: order.shipping_country || "USA",
      shipping_cost: order.shipping_cost || "0.00",
    });
    setEditingAddress(true);
  };

  const handleSaveAddress = async () => {
    setSavingAddress(true);
    try {
      const parsedShippingCost = Number.parseFloat(addressForm.shipping_cost);
      const payload = {
        ...addressForm,
        shipping_cost: Number.isNaN(parsedShippingCost) ? 0 : parsedShippingCost,
      };
      const res = await fetch(
        `${API_URL}/api/v1/sales-orders/${order.id}/address`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(payload),
        }
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to update address");
      }

      toast.success("Shipping address updated");
      setEditingAddress(false);
      onOrderUpdated();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSavingAddress(false);
    }
  };

  return (
    <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-6 shadow-[var(--shadow-pop)]">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-[var(--ink)]">Shipping Address</h2>
        {!editingAddress && (
          <button
            onClick={handleEditAddress}
            className="text-[var(--orange)] hover:text-[var(--orange-press)] text-sm"
          >
            Edit
          </button>
        )}
      </div>

      {editingAddress ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 md:col-span-1">
              <label className="block text-sm text-[var(--ink-3)] mb-1">
                Shipping Charge
              </label>
              <input
                type="number"
                value={addressForm.shipping_cost}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_cost: e.target.value,
                  })
                }
                className="w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-4 py-2 text-[var(--ink)]"
                min="0"
                step="0.01"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm text-[var(--ink-3)] mb-1">
                Address Line 1
              </label>
              <input
                type="text"
                value={addressForm.shipping_address_line1}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_address_line1: e.target.value,
                  })
                }
                className="w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-4 py-2 text-[var(--ink)]"
                placeholder="Street address"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm text-[var(--ink-3)] mb-1">
                Address Line 2
              </label>
              <input
                type="text"
                value={addressForm.shipping_address_line2}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_address_line2: e.target.value,
                  })
                }
                className="w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-4 py-2 text-[var(--ink)]"
                placeholder="Apt, suite, etc."
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--ink-3)] mb-1">City</label>
              <input
                type="text"
                value={addressForm.shipping_city}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_city: e.target.value,
                  })
                }
                className="w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-4 py-2 text-[var(--ink)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--ink-3)] mb-1">
                State
              </label>
              <input
                type="text"
                value={addressForm.shipping_state}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_state: e.target.value,
                  })
                }
                className="w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-4 py-2 text-[var(--ink)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--ink-3)] mb-1">
                ZIP Code
              </label>
              <input
                type="text"
                value={addressForm.shipping_zip}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_zip: e.target.value,
                  })
                }
                className="w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-4 py-2 text-[var(--ink)]"
              />
            </div>
            <div>
              <label className="block text-sm text-[var(--ink-3)] mb-1">
                Country
              </label>
              <input
                type="text"
                value={addressForm.shipping_country}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_country: e.target.value,
                  })
                }
                className="w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-4 py-2 text-[var(--ink)]"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setEditingAddress(false)}
              className="px-4 py-2 text-[var(--ink-3)] hover:text-[var(--ink)]"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveAddress}
              disabled={savingAddress}
              className="px-4 py-2 bg-[var(--orange)] hover:bg-[var(--orange-press)] text-white rounded-lg disabled:opacity-50"
            >
              {savingAddress ? "Saving..." : "Save Address"}
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <div className="text-sm text-[var(--ink-3)]">Shipping Charge</div>
              <div className="text-[var(--ink)] font-medium">
                ${Number.isNaN(shippingCharge) ? "0.00" : shippingCharge.toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-sm text-[var(--ink-3)]">Order Total</div>
              <div className="text-[var(--ink)] font-medium">
                ${Number.isNaN(grandTotal) ? "0.00" : grandTotal.toFixed(2)}
              </div>
            </div>
          </div>
          {order.shipping_address_line1 ? (
            <div className="text-[var(--ink)]">
              <div>{order.shipping_address_line1}</div>
              {order.shipping_address_line2 && (
                <div>{order.shipping_address_line2}</div>
              )}
              <div>
                {order.shipping_city}, {order.shipping_state}{" "}
                {order.shipping_zip}
              </div>
              <div className="text-[var(--ink-3)]">
                {order.shipping_country || "USA"}
              </div>
            </div>
          ) : (
            <div className="text-[var(--status-amber)] flex items-center gap-2">
              <svg
                className="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              No shipping address on file. Click Edit to add one.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
