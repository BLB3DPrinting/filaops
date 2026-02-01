/**
 * VendorModal - Create/Edit vendor form
 */
import { useState } from "react";
import { useToast } from "../Toast";
import Modal from "../Modal";

export default function VendorModal({ vendor, onClose, onSave }) {
  const toast = useToast();
  const [form, setForm] = useState({
    name: vendor?.name || "",
    code: vendor?.code || "",
    contact_name: vendor?.contact_name || "",
    email: vendor?.email || "",
    phone: vendor?.phone || "",
    website: vendor?.website || "",
    address_line1: vendor?.address_line1 || "",
    address_line2: vendor?.address_line2 || "",
    city: vendor?.city || "",
    state: vendor?.state || "",
    postal_code: vendor?.postal_code || "",
    country: vendor?.country || "USA",
    payment_terms: vendor?.payment_terms || "",
    account_number: vendor?.account_number || "",
    notes: vendor?.notes || "",
    is_active: vendor?.is_active ?? true,
  });

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.warning("Vendor name is required");
      return;
    }
    onSave(form);
  };

  return (
    <Modal isOpen={true} onClose={onClose} title={vendor ? "Edit Vendor" : "New Vendor"} className="max-w-2xl w-full mx-auto p-6">
          <div className="flex justify-between items-center mb-6">
            <h3 className="text-lg font-semibold text-white">
              {vendor ? "Edit Vendor" : "New Vendor"}
            </h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white"
            >
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
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Name *
                </label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Code (auto if empty)
                </label>
                <input
                  type="text"
                  value={form.code}
                  onChange={(e) => setForm({ ...form, code: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  placeholder="VND-001"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Contact Name
                </label>
                <input
                  type="text"
                  value={form.contact_name}
                  onChange={(e) =>
                    setForm({ ...form, contact_name: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Email
                </label>
                <input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Phone
                </label>
                <input
                  type="text"
                  value={form.phone}
                  onChange={(e) => setForm({ ...form, phone: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Website
                </label>
                <input
                  type="text"
                  value={form.website}
                  onChange={(e) =>
                    setForm({ ...form, website: e.target.value })
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                />
              </div>
            </div>

            <div className="border-t border-gray-800 pt-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">
                Address
              </h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="col-span-2">
                  <input
                    type="text"
                    value={form.address_line1}
                    onChange={(e) =>
                      setForm({ ...form, address_line1: e.target.value })
                    }
                    placeholder="Address Line 1"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div className="col-span-2">
                  <input
                    type="text"
                    value={form.address_line2}
                    onChange={(e) =>
                      setForm({ ...form, address_line2: e.target.value })
                    }
                    placeholder="Address Line 2"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={form.city}
                    onChange={(e) => setForm({ ...form, city: e.target.value })}
                    placeholder="City"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={form.state}
                    onChange={(e) =>
                      setForm({ ...form, state: e.target.value })
                    }
                    placeholder="State"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={form.postal_code}
                    onChange={(e) =>
                      setForm({ ...form, postal_code: e.target.value })
                    }
                    placeholder="Postal Code"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <input
                    type="text"
                    value={form.country}
                    onChange={(e) =>
                      setForm({ ...form, country: e.target.value })
                    }
                    placeholder="Country"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
              </div>
            </div>

            <div className="border-t border-gray-800 pt-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">
                Business Info
              </h4>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    Payment Terms
                  </label>
                  <input
                    type="text"
                    value={form.payment_terms}
                    onChange={(e) =>
                      setForm({ ...form, payment_terms: e.target.value })
                    }
                    placeholder="Net 30, COD, etc."
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    Account Number
                  </label>
                  <input
                    type="text"
                    value={form.account_number}
                    onChange={(e) =>
                      setForm({ ...form, account_number: e.target.value })
                    }
                    placeholder="Our account with them"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">Notes</label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                rows={3}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active"
                checked={form.is_active}
                onChange={(e) =>
                  setForm({ ...form, is_active: e.target.checked })
                }
                className="rounded bg-gray-800 border-gray-700"
              />
              <label htmlFor="is_active" className="text-sm text-gray-300">
                Active
              </label>
            </div>

            <div className="flex justify-end gap-3 pt-4 border-t border-gray-800">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium"
              >
                {vendor ? "Save Changes" : "Create Vendor"}
              </button>
            </div>
          </form>
    </Modal>
  );
}
