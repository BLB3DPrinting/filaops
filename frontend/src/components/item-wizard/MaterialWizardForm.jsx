/**
 * MaterialWizardForm - Inline form for adding filament to inventory & BOM.
 *
 * Extracted from ItemWizard.jsx (ARCHITECT-002)
 */

export default function MaterialWizardForm({
  materialTypes,
  allColors,
  newMaterial,
  loading,
  onMaterialChange,
  onColorTypeChange,
  onCreateMaterial,
  onCancel,
}) {
  return (
    <div className="bg-pink-900/20 border border-pink-500/30 rounded-lg p-4 mb-3 space-y-3">
      <div className="flex justify-between items-center">
        <span className="text-pink-400 font-medium text-sm">Add Filament to Inventory</span>
        <button type="button" onClick={onCancel} className="text-gray-400 hover:text-white text-xs">Cancel</button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Material Type *</label>
          <select
            value={newMaterial.material_type_code}
            onChange={(e) => onColorTypeChange(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
          >
            <option value="">Select material...</option>
            {materialTypes.map(mt => (
              <option key={mt.code} value={mt.code}>{mt.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Color *</label>
          <select
            value={newMaterial.color_code}
            onChange={(e) => onMaterialChange({ ...newMaterial, color_code: e.target.value })}
            disabled={!newMaterial.material_type_code}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm disabled:opacity-50"
          >
            <option value="">{newMaterial.material_type_code ? "Select color..." : "Select material first"}</option>
            {allColors.map(c => (
              <option key={c.code} value={c.code}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Quantity (kg)</label>
          <input
            type="number"
            step="0.1"
            value={newMaterial.quantity_kg}
            onChange={(e) => onMaterialChange({ ...newMaterial, quantity_kg: parseFloat(e.target.value) || 1.0 })}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Cost per kg ($)</label>
          <input
            type="number"
            step="0.01"
            value={newMaterial.cost_per_kg || ""}
            onChange={(e) => onMaterialChange({ ...newMaterial, cost_per_kg: parseFloat(e.target.value) || null })}
            placeholder="Auto from material"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
          />
        </div>
      </div>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onCreateMaterial}
          disabled={loading || !newMaterial.material_type_code || !newMaterial.color_code}
          className="px-3 py-1.5 bg-pink-600 text-white text-sm rounded hover:bg-pink-500 disabled:opacity-50"
        >
          {loading ? "Creating..." : "Add to Inventory & BOM"}
        </button>
      </div>
    </div>
  );
}
