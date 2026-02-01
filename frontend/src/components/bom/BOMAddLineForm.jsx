import SearchableSelect from "../SearchableSelect";

/**
 * BOMAddLineForm - Form for adding a new component to a BOM.
 * Includes product search, quantity, unit override, scrap factor, and notes.
 */
export default function BOMAddLineForm({
  newLine,
  setNewLine,
  products,
  uoms,
  loading,
  onAddLine,
  onCancel,
}) {
  const selectedProduct = products.find(
    (p) => String(p.id) === String(newLine.component_id)
  );
  const selectedCost = selectedProduct
    ? selectedProduct.standard_cost ||
      selectedProduct.average_cost ||
      selectedProduct.selling_price ||
      0
    : 0;

  return (
    <div className="bg-gray-800 rounded-lg p-4 space-y-4">
      <h4 className="font-medium text-white">Add Component</h4>
      {/* Selected component info */}
      {selectedProduct && (
        <div className="bg-gray-900 rounded-lg p-3 flex items-center justify-between">
          <div>
            <span className="text-white font-medium">
              {selectedProduct.name}
            </span>
            <span className="text-gray-500 ml-2">({selectedProduct.sku})</span>
          </div>
          <div className="text-right">
            <span className="text-green-400 font-mono">
              ${parseFloat(selectedCost).toFixed(2)}
            </span>
            <span className="text-gray-500 ml-1">
              / {selectedProduct.unit || "EA"}
            </span>
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Component
          </label>
          <SearchableSelect
            options={products}
            value={newLine.component_id}
            onChange={(val) => {
              const selected = products.find(
                (p) => String(p.id) === String(val)
              );
              setNewLine({
                ...newLine,
                component_id: val,
                unit: selected?.unit || newLine.unit,
              });
            }}
            placeholder="Select component..."
            displayKey="name"
            valueKey="id"
            formatOption={(p) => {
              const cost =
                p.standard_cost || p.average_cost || p.selling_price || 0;
              return `${p.name} (${p.sku}) - $${parseFloat(cost).toFixed(
                2
              )}/${p.unit || "EA"}`;
            }}
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Quantity
          </label>
          <div className="flex">
            <input
              type="number"
              step="0.001"
              value={newLine.quantity}
              onChange={(e) =>
                setNewLine({ ...newLine, quantity: e.target.value })
              }
              className="flex-1 bg-gray-900 border border-gray-700 rounded-l-lg px-3 py-2 text-white"
            />
            <span className="bg-gray-700 border border-l-0 border-gray-700 rounded-r-lg px-3 py-2 text-gray-300 font-mono text-sm">
              {newLine.unit || selectedProduct?.unit || "EA"}
            </span>
          </div>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Unit Override
          </label>
          <select
            value={newLine.unit}
            onChange={(e) =>
              setNewLine({ ...newLine, unit: e.target.value })
            }
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
          >
            <option value="">Use component default</option>
            {uoms.map((u) => (
              <option key={u.code} value={u.code}>
                {u.code} - {u.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Scrap Factor %
          </label>
          <input
            type="number"
            step="0.1"
            value={newLine.scrap_factor}
            onChange={(e) =>
              setNewLine({ ...newLine, scrap_factor: e.target.value })
            }
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
          />
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">Notes</label>
          <input
            type="text"
            value={newLine.notes}
            onChange={(e) =>
              setNewLine({ ...newLine, notes: e.target.value })
            }
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white"
          />
        </div>
      </div>
      <div className="flex gap-2">
        <button
          onClick={onAddLine}
          disabled={loading || !newLine.component_id}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
        >
          Add Component
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
