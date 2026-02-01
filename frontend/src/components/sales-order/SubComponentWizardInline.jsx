/**
 * SubComponentWizardInline - Inline form for creating a new component and adding it to BOM.
 * Shown within the BOM builder section of the Item Creation Wizard.
 */
export default function SubComponentWizardInline({
  subComponent,
  setSubComponent,
  loading,
  onSave,
  onCancel,
}) {
  return (
    <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4 mb-3 space-y-3">
      <div className="flex justify-between items-center">
        <span className="text-purple-400 font-medium text-sm">
          New Component
        </span>
        <button
          type="button"
          onClick={onCancel}
          className="text-gray-400 hover:text-white text-xs"
        >
          Cancel
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Component Name *
          </label>
          <input
            type="text"
            value={subComponent.name}
            onChange={(e) =>
              setSubComponent({
                ...subComponent,
                name: e.target.value,
              })
            }
            placeholder="e.g. M3 Heat Insert"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            SKU
          </label>
          <input
            type="text"
            value={subComponent.sku}
            onChange={(e) =>
              setSubComponent({
                ...subComponent,
                sku: e.target.value.toUpperCase(),
              })
            }
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm font-mono"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Unit Cost ($)
          </label>
          <input
            type="number"
            step="0.01"
            value={subComponent.standard_cost || ""}
            onChange={(e) =>
              setSubComponent({
                ...subComponent,
                standard_cost:
                  parseFloat(e.target.value) || null,
              })
            }
            placeholder="0.00"
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Unit
          </label>
          <input
            type="text"
            value={subComponent.unit}
            onChange={(e) =>
              setSubComponent({
                ...subComponent,
                unit: e.target.value.toUpperCase(),
              })
            }
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-1.5 text-white text-sm"
          />
        </div>
      </div>
      <div className="flex justify-end">
        <button
          type="button"
          onClick={onSave}
          disabled={loading || !subComponent.name}
          className="px-3 py-1.5 bg-purple-600 text-white text-sm rounded hover:bg-purple-500 disabled:opacity-50"
        >
          {loading
            ? "Creating..."
            : "Create & Add to BOM"}
        </button>
      </div>
    </div>
  );
}
