/**
 * CustomerModal - Create/edit customer form with billing & shipping addresses.
 *
 * Extracted from AdminCustomers.jsx (ARCHITECT-002)
 */
import { useState } from "react";
import Modal from "../Modal";
import { STATUS_OPTIONS, PAYMENT_TERMS_OPTIONS, formatPhoneNumber } from "./constants";

export default function CustomerModal({ customer, onSave, onClose }) {
  const [form, setForm] = useState({
    email: customer?.email || "",
    first_name: customer?.first_name || "",
    last_name: customer?.last_name || "",
    company_name: customer?.company_name || "",
    phone: customer?.phone || "",
    status: customer?.status || "active",
    // Billing
    billing_address_line1: customer?.billing_address_line1 || "",
    billing_address_line2: customer?.billing_address_line2 || "",
    billing_city: customer?.billing_city || "",
    billing_state: customer?.billing_state || "",
    billing_zip: customer?.billing_zip || "",
    billing_country: customer?.billing_country || "USA",
    // Shipping
    shipping_address_line1: customer?.shipping_address_line1 || "",
    shipping_address_line2: customer?.shipping_address_line2 || "",
    shipping_city: customer?.shipping_city || "",
    shipping_state: customer?.shipping_state || "",
    shipping_zip: customer?.shipping_zip || "",
    shipping_country: customer?.shipping_country || "USA",
    // Payment Terms
    payment_terms: customer?.payment_terms || "cod",
    credit_limit: customer?.credit_limit ?? "",
    approved_for_terms: customer?.approved_for_terms || false,
  });
  const [termsError, setTermsError] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    setTermsError("");
    if ((form.payment_terms === "net15" || form.payment_terms === "net30") && !form.approved_for_terms) {
      setTermsError("Customer must be approved for terms before assigning Net 15 or Net 30.");
      return;
    }
    const payload = {
      ...form,
      credit_limit: form.credit_limit === "" ? null : parseFloat(form.credit_limit),
    };
    onSave(payload);
  };

  const copyBillingToShipping = () => {
    setForm({
      ...form,
      shipping_address_line1: form.billing_address_line1,
      shipping_address_line2: form.billing_address_line2,
      shipping_city: form.billing_city,
      shipping_state: form.billing_state,
      shipping_zip: form.billing_zip,
      shipping_country: form.billing_country,
    });
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={customer ? "Edit Customer" : "Add New Customer"}
      className="w-full max-w-3xl max-h-[90vh] overflow-auto"
    >
      <div className="p-6 border-b border-gray-800">
        <h2 className="text-xl font-bold text-white">
          {customer ? "Edit Customer" : "Add New Customer"}
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Basic Info */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
              Basic Information
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Email *
                </label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  required
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Status
                </label>
                <select
                  value={form.status}
                  onChange={(e) => setForm({ ...form, status: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  {STATUS_OPTIONS.map((s) => (
                    <option key={s.value} value={s.value}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                First Name
              </label>
              <input
                type="text"
                value={form.first_name}
                onChange={(e) =>
                  setForm({ ...form, first_name: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Last Name
              </label>
              <input
                type="text"
                value={form.last_name}
                onChange={(e) =>
                  setForm({ ...form, last_name: e.target.value })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Phone</label>
              <input
                type="text"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: formatPhoneNumber(e.target.value) })}
                placeholder="(512) 555-9067"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Company Name
            </label>
            <input
              type="text"
              value={form.company_name}
              onChange={(e) =>
                setForm({ ...form, company_name: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>

          {/* Payment Terms */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
              Payment Terms
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Terms
                </label>
                <select
                  value={form.payment_terms}
                  onChange={(e) => {
                    setForm({ ...form, payment_terms: e.target.value });
                    setTermsError("");
                  }}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  {PAYMENT_TERMS_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Credit Limit
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  value={form.credit_limit}
                  onChange={(e) =>
                    setForm({ ...form, credit_limit: e.target.value })
                  }
                  placeholder="No limit"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 cursor-pointer pb-2">
                  <input
                    type="checkbox"
                    checked={form.approved_for_terms}
                    onChange={(e) => {
                      setForm({ ...form, approved_for_terms: e.target.checked });
                      setTermsError("");
                    }}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-300">Approved for Terms</span>
                </label>
              </div>
            </div>
            {termsError && (
              <p className="mt-2 text-sm text-red-400">{termsError}</p>
            )}
            {(form.payment_terms === "net15" || form.payment_terms === "net30") && !form.approved_for_terms && !termsError && (
              <p className="mt-2 text-sm text-yellow-400">
                Net terms require approval before saving.
              </p>
            )}
          </div>

          {/* Billing Address */}
          <div>
            <h3 className="text-sm font-medium text-gray-400 uppercase mb-3">
              Billing Address
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 1
                </label>
                <input
                  type="text"
                  value={form.billing_address_line1}
                  onChange={(e) =>
                    setForm({ ...form, billing_address_line1: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 2
                </label>
                <input
                  type="text"
                  value={form.billing_address_line2}
                  onChange={(e) =>
                    setForm({ ...form, billing_address_line2: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div className="grid grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    City
                  </label>
                  <input
                    type="text"
                    value={form.billing_city}
                    onChange={(e) =>
                      setForm({ ...form, billing_city: e.target.value })
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
                    value={form.billing_state}
                    onChange={(e) =>
                      setForm({ ...form, billing_state: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    ZIP
                  </label>
                  <input
                    type="text"
                    value={form.billing_zip}
                    onChange={(e) =>
                      setForm({ ...form, billing_zip: e.target.value })
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
                    value={form.billing_country}
                    onChange={(e) =>
                      setForm({ ...form, billing_country: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Shipping Address */}
          <div>
            <div className="flex justify-between items-center mb-3">
              <h3 className="text-sm font-medium text-gray-400 uppercase">
                Shipping Address
              </h3>
              <button
                type="button"
                onClick={copyBillingToShipping}
                className="text-sm text-blue-400 hover:text-blue-300"
              >
                Copy from Billing
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 1
                </label>
                <input
                  type="text"
                  value={form.shipping_address_line1}
                  onChange={(e) =>
                    setForm({ ...form, shipping_address_line1: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Address Line 2
                </label>
                <input
                  type="text"
                  value={form.shipping_address_line2}
                  onChange={(e) =>
                    setForm({ ...form, shipping_address_line2: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                />
              </div>
              <div className="grid grid-cols-4 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    City
                  </label>
                  <input
                    type="text"
                    value={form.shipping_city}
                    onChange={(e) =>
                      setForm({ ...form, shipping_city: e.target.value })
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
                    value={form.shipping_state}
                    onChange={(e) =>
                      setForm({ ...form, shipping_state: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    ZIP
                  </label>
                  <input
                    type="text"
                    value={form.shipping_zip}
                    onChange={(e) =>
                      setForm({ ...form, shipping_zip: e.target.value })
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
                    value={form.shipping_country}
                    onChange={(e) =>
                      setForm({ ...form, shipping_country: e.target.value })
                    }
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-4 pt-4 border-t border-gray-800">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500"
            >
              {customer ? "Save Changes" : "Create Customer"}
            </button>
          </div>
      </form>
    </Modal>
  );
}
