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

  const handleEditAddress = () => {
    setAddressForm({
      shipping_address_line1: order.shipping_address_line1 || "",
      shipping_address_line2: order.shipping_address_line2 || "",
      shipping_city: order.shipping_city || "",
      shipping_state: order.shipping_state || "",
      shipping_zip: order.shipping_zip || "",
      shipping_country: order.shipping_country || "USA",
    });
    setEditingAddress(true);
  };

  const handleSaveAddress = async () => {
    setSavingAddress(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/sales-orders/${order.id}/address`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(addressForm),
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
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-white">Shipping Address</h2>
        {!editingAddress && (
          <button
            onClick={handleEditAddress}
            className="text-blue-400 hover:text-blue-300 text-sm"
          >
            Edit
          </button>
        )}
      </div>

      {editingAddress ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm text-gray-400 mb-1">
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                placeholder="Street address"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-sm text-gray-400 mb-1">
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                placeholder="Apt, suite, etc."
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">City</label>
              <input
                type="text"
                value={addressForm.shipping_city}
                onChange={(e) =>
                  setAddressForm({
                    ...addressForm,
                    shipping_city: e.target.value,
                  })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
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
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button
              onClick={() => setEditingAddress(false)}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={handleSaveAddress}
              disabled={savingAddress}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
            >
              {savingAddress ? "Saving..." : "Save Address"}
            </button>
          </div>
        </div>
      ) : (
        <div>
          {order.shipping_address_line1 ? (
            <div className="text-white">
              <div>{order.shipping_address_line1}</div>
              {order.shipping_address_line2 && (
                <div>{order.shipping_address_line2}</div>
              )}
              <div>
                {order.shipping_city}, {order.shipping_state}{" "}
                {order.shipping_zip}
              </div>
              <div className="text-gray-400">
                {order.shipping_country || "USA"}
              </div>
            </div>
          ) : (
            <div className="text-yellow-400 flex items-center gap-2">
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
