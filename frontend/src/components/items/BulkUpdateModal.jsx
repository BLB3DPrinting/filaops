/**
 * BulkUpdateModal - Form for bulk updating category/type/procurement/status on selected items.
 */
import { useState } from "react";
import Modal from "../Modal";

const ITEM_TYPES = [
  { value: "finished_good", label: "Finished Good" },
  { value: "component", label: "Component" },
  { value: "material", label: "Material" },
  { value: "supply", label: "Supply" },
  { value: "service", label: "Service" },
];

export default function BulkUpdateModal({
  categories,
  selectedCount,
  onSave,
  onClose,
}) {
  const [categoryId, setCategoryId] = useState("");
  const [itemType, setItemType] = useState("");
  const [procurementType, setProcurementType] = useState("");
  const [active, setActive] = useState("");

  const handleSubmit = () => {
    const updateData = {};
    if (categoryId) updateData.category_id = parseInt(categoryId);
    if (itemType) updateData.item_type = itemType;
    if (procurementType) updateData.procurement_type = procurementType;
    if (active !== "") updateData.is_active = active === "true";
    onSave(updateData);
  };

  const hasChanges = categoryId || itemType || procurementType || active !== "";

  return (
    <Modal isOpen={true} onClose={onClose} title="Bulk Update Items" className="w-full max-w-md">
      <div className="p-6 space-y-4">
        <p className="text-gray-400 text-sm">
          Updating {selectedCount} selected item
          {selectedCount !== 1 ? "s" : ""}. Only filled fields will be changed.
        </p>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Category</label>
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            <option value="">-- No change --</option>
            {categories
              .filter((c) => c.is_active)
              .map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Item Type</label>
          <select
            value={itemType}
            onChange={(e) => setItemType(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            <option value="">-- No change --</option>
            {ITEM_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Procurement Type
          </label>
          <select
            value={procurementType}
            onChange={(e) => setProcurementType(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            <option value="">-- No change --</option>
            <option value="buy">Buy</option>
            <option value="make">Make</option>
            <option value="make_or_buy">Make or Buy</option>
          </select>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-1">Status</label>
          <select
            value={active}
            onChange={(e) => setActive(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          >
            <option value="">-- No change --</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>

        <div className="flex gap-3 pt-2">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!hasChanges}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Update Items
          </button>
        </div>
      </div>
    </Modal>
  );
}
