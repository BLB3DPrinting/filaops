import SearchableSelect from "../SearchableSelect";

/**
 * AddOperationMaterialForm - Form content for adding a material to a routing operation.
 * Rendered inside a Modal by BOMDetailView.
 */
export default function AddOperationMaterialForm({
  newMaterial,
  setNewMaterial,
  products,
  uoms,
  onSubmit,
  onClose,
}) {
  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-white">Add Material to Operation</h2>
        <button onClick={onClose} className="text-gray-400 hover:text-white p-1" aria-label="Close">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
      <div className="space-y-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Component *
          </label>
          <SearchableSelect
            options={products}
            value={newMaterial.component_id}
            onChange={(val) => {
              const selected = products.find(
                (p) => String(p.id) === String(val)
              );
              setNewMaterial({
                ...newMaterial,
                component_id: val,
                unit: selected?.unit || "",
              });
            }}
            placeholder="Select component..."
            displayKey="name"
            valueKey="id"
            formatOption={(p) => {
              const cost =
                p.standard_cost || p.average_cost || p.selling_price || 0;
              return `${p.name} (${p.sku}) - ${parseFloat(cost).toFixed(2)}/${
                p.unit || "EA"
              }`;
            }}
          />
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Quantity *
            </label>
            <input
              type="number"
              step="0.001"
              value={newMaterial.quantity}
              onChange={(e) =>
                setNewMaterial({
                  ...newMaterial,
                  quantity: e.target.value,
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Scrap %
            </label>
            <input
              type="number"
              step="0.1"
              value={newMaterial.scrap_factor}
              onChange={(e) =>
                setNewMaterial({
                  ...newMaterial,
                  scrap_factor: e.target.value,
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Unit
            </label>
            <select
              value={newMaterial.unit}
              onChange={(e) =>
                setNewMaterial({ ...newMaterial, unit: e.target.value })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white"
            >
              <option value="">Use component default</option>
              {uoms.map((u) => (
                <option key={u.code} value={u.code}>
                  {u.code} - {u.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <button
            onClick={onSubmit}
            disabled={!newMaterial.component_id}
            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            Add Material
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
