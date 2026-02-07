/**
 * QuickCreateItemModal - Quick item creation from PO screen
 *
 * Creates a minimal supply/material item for purchasing
 * User can add more details later from Items page
 */
import { useState } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import Modal from "../Modal";

export default function QuickCreateItemModal({ onClose, onCreated, initialName = "" }) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    sku: "",
    name: initialName,
    item_type: "supply", // Default to supply for purchased items
    procurement_type: "buy",
    stocking_policy: "on_demand", // Default to on_demand (MRP-driven)
    unit: "pcs",
    last_cost: "",
    reorder_point: "",
    notes: "",
  });

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.sku.trim()) {
      toast.warning("SKU is required");
      return;
    }
    if (!form.name.trim()) {
      toast.warning("Name is required");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/items`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          sku: form.sku.trim(),
          name: form.name.trim(),
          item_type: form.item_type,
          procurement_type: form.procurement_type,
          stocking_policy: form.stocking_policy,
          unit: form.unit,
          last_cost: form.last_cost ? parseFloat(form.last_cost) : null,
          reorder_point: form.stocking_policy === "stocked" && form.reorder_point
            ? parseFloat(form.reorder_point)
            : null,
          notes: form.notes || null,
          active: true,
        }),
      });

      if (res.ok) {
        const newItem = await res.json();
        toast.success(`Item "${newItem.sku}" created`);
        onCreated(newItem);
      } else {
        const error = await res.json();
        toast.error(error.detail || "Failed to create item");
      }
    } catch {
      toast.error("Failed to create item");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose} title="Quick Create Item" disableClose={loading} className="max-w-md w-full mx-auto p-6">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold text-white">Quick Create Item</h3>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <p className="text-sm text-gray-400 mb-4">
            Create a new item quickly. You can add more details later from the Items page.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  SKU *
                </label>
                <input
                  type="text"
                  value={form.sku}
                  onChange={(e) => setForm({ ...form, sku: e.target.value.toUpperCase() })}
                  placeholder="MAT-NEW-001"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Unit
                </label>
                <select
                  value={form.unit}
                  onChange={(e) => setForm({ ...form, unit: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="pcs">Pieces (pcs)</option>
                  <option value="kg">Kilograms (kg)</option>
                  <option value="g">Grams (g)</option>
                  <option value="m">Meters (m)</option>
                  <option value="ft">Feet (ft)</option>
                  <option value="L">Liters (L)</option>
                  <option value="mL">Milliliters (mL)</option>
                  <option value="roll">Rolls</option>
                  <option value="box">Boxes</option>
                  <option value="pack">Packs</option>
                </select>
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Name *
              </label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Item description"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Item Type
                </label>
                <select
                  value={form.item_type}
                  onChange={(e) => setForm({ ...form, item_type: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="supply">Supply</option>
                  <option value="material">Material (Filament)</option>
                  <option value="component">Component</option>
                  <option value="finished_good">Finished Good</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Stocking Policy
                </label>
                <select
                  value={form.stocking_policy}
                  onChange={(e) => setForm({ ...form, stocking_policy: e.target.value })}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                >
                  <option value="on_demand">On-Demand (MRP)</option>
                  <option value="stocked">Stocked (Reorder Point)</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Last Cost
                </label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">$</span>
                  <input
                    type="number"
                    value={form.last_cost}
                    onChange={(e) => setForm({ ...form, last_cost: e.target.value })}
                    placeholder="0.00"
                    min="0"
                    step="0.01"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-7 pr-3 py-2 text-white"
                  />
                </div>
              </div>
              {form.stocking_policy === "stocked" && (
                <div>
                  <label className="block text-sm text-gray-400 mb-1">
                    Reorder Point
                  </label>
                  <input
                    type="number"
                    value={form.reorder_point}
                    onChange={(e) => setForm({ ...form, reorder_point: e.target.value })}
                    placeholder="Min qty to keep on hand"
                    min="0"
                    step="1"
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
                  />
                </div>
              )}
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Notes (optional)
              </label>
              <textarea
                value={form.notes}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
                rows={2}
                placeholder="Vendor part number, specs, etc."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg text-white font-medium disabled:opacity-50 flex items-center gap-2"
              >
                {loading ? (
                  <>
                    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Creating...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    Create Item
                  </>
                )}
              </button>
            </div>
          </form>
    </Modal>
  );
}
