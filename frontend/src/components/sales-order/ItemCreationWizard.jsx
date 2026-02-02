/**
 * ItemCreationWizard - Inline "New Item Wizard" for creating products within the Sales Order Wizard.
 *
 * Extracted from SalesOrderWizard.jsx Step 2 ("Create New Product" flow).
 * Contains 3 sub-steps:
 *   1. Basic Info (item type, category, procurement type, name, SKU, unit, description)
 *   2. BOM Builder (images, components, routing operations, cost summary) - only for "make" procurement types
 *   3. Pricing (cost summary, margin calculator, selling price)
 *
 * All state is managed by the parent SalesOrderWizard; this component is purely presentational.
 *
 * @param {Object} props - See SalesOrderWizard for full prop descriptions
 */
import MaterialWizardInline from "./MaterialWizardInline";
import SubComponentWizardInline from "./SubComponentWizardInline";

export default function ItemCreationWizard({
  // Constants
  ITEM_TYPES,
  PROCUREMENT_TYPES,

  // Item wizard state
  itemWizardStep,
  setItemWizardStep,
  itemNeedsBom,
  newItem,
  setNewItem,
  categories,

  // BOM state
  bomLines,
  addBomLine,
  removeBomLine,
  updateBomQuantity,
  components,

  // Material wizard state
  showMaterialWizard,
  setShowMaterialWizard,
  newMaterial,
  setNewMaterial,
  materialTypes,
  allColors,
  fetchColorsForType,
  handleCreateMaterial,

  // Sub-component wizard state
  showSubComponentWizard,
  setShowSubComponentWizard,
  startSubComponent,
  subComponent,
  setSubComponent,
  handleSaveSubComponent,

  // Routing state
  routingOperations,
  addRoutingOperation,
  removeRoutingOperation,
  updateOperationTime,
  workCenters,
  routingTemplates,
  selectedTemplate,
  applyRoutingTemplate,

  // Image state
  imagePreviewUrls,
  handleImageSelect,
  handleImageDrop,
  removeImage,

  // Cost/pricing state
  calculatedCost,
  laborCost,
  totalCost,
  targetMargin,
  setTargetMargin,
  suggestedPrice,

  // Actions
  loading,
  onSave,
  onCancel,
}) {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-white">
          Create New Product - Step {itemWizardStep} of{" "}
          {itemNeedsBom ? 3 : 2}
        </h3>
        <button
          onClick={onCancel}
          className="text-gray-400 hover:text-white text-sm"
        >
          Cancel
        </button>
      </div>

      {/* Progress indicator */}
      <div className="flex gap-2">
        <div
          className={`flex-1 h-1 rounded ${
            itemWizardStep >= 1 ? "bg-blue-500" : "bg-gray-700"
          }`}
        />
        {itemNeedsBom && (
          <div
            className={`flex-1 h-1 rounded ${
              itemWizardStep >= 2 ? "bg-blue-500" : "bg-gray-700"
            }`}
          />
        )}
        <div
          className={`flex-1 h-1 rounded ${
            itemWizardStep >= (itemNeedsBom ? 3 : 2)
              ? "bg-blue-500"
              : "bg-gray-700"
          }`}
        />
      </div>

      {/* Item Wizard Step 1: Basic Info */}
      {itemWizardStep === 1 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Item Type
              </label>
              <select
                value={newItem.item_type}
                onChange={(e) => {
                  const itemType = ITEM_TYPES.find(
                    (t) => t.value === e.target.value
                  );
                  setNewItem({
                    ...newItem,
                    item_type: e.target.value,
                    procurement_type:
                      itemType?.defaultProcurement || "buy",
                    sku: "",
                  });
                }}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              >
                {ITEM_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Category
              </label>
              <select
                value={newItem.category_id ?? ""}
                onChange={(e) =>
                  setNewItem({
                    ...newItem,
                    category_id: e.target.value
                      ? parseInt(e.target.value)
                      : null,
                  })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              >
                <option value="">-- None --</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_path || c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Make vs Buy selector */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Procurement Type (Make vs Buy)
            </label>
            <div className="grid grid-cols-3 gap-2">
              {PROCUREMENT_TYPES.map((pt) => (
                <button
                  key={pt.value}
                  type="button"
                  onClick={() =>
                    setNewItem({
                      ...newItem,
                      procurement_type: pt.value,
                    })
                  }
                  className={`p-3 rounded-lg border text-left transition-colors ${
                    newItem.procurement_type === pt.value
                      ? pt.value === "make"
                        ? "bg-green-600/20 border-green-500 text-green-400"
                        : pt.value === "buy"
                        ? "bg-blue-600/20 border-blue-500 text-blue-400"
                        : "bg-yellow-600/20 border-yellow-500 text-yellow-400"
                      : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500"
                  }`}
                >
                  <div className="font-medium text-sm">
                    {pt.label}
                  </div>
                  <div className="text-xs opacity-70 mt-1">
                    {pt.description}
                  </div>
                </button>
              ))}
            </div>
            {itemNeedsBom && (
              <p className="text-xs text-green-400 mt-2">
                This item will have a BOM and/or routing
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Product Name *
            </label>
            <input
              type="text"
              value={newItem.name}
              onChange={(e) =>
                setNewItem({ ...newItem, name: e.target.value })
              }
              placeholder="e.g. Custom Widget Assembly"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                SKU (auto-generated)
              </label>
              <input
                type="text"
                value={newItem.sku}
                onChange={(e) =>
                  setNewItem({
                    ...newItem,
                    sku: e.target.value.toUpperCase(),
                  })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white font-mono"
              />
              <p className="text-xs text-gray-500 mt-1">
                Auto-generated from type + timestamp
              </p>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Unit
              </label>
              <input
                type="text"
                value={newItem.unit}
                onChange={(e) =>
                  setNewItem({
                    ...newItem,
                    unit: e.target.value.toUpperCase(),
                  })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm text-gray-400 mb-1">
              Description
            </label>
            <textarea
              value={newItem.description}
              onChange={(e) =>
                setNewItem({
                  ...newItem,
                  description: e.target.value,
                })
              }
              rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>

          <div className="flex justify-end">
            <button
              onClick={() =>
                setItemWizardStep(2)
              }
              disabled={!newItem.name}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 disabled:opacity-50"
            >
              {itemNeedsBom
                ? "Next: Add BOM Components"
                : "Next: Set Pricing"}
            </button>
          </div>
        </div>
      )}

      {/* Item Wizard Step 2: BOM Builder (only for finished goods) */}
      {itemWizardStep === 2 && itemNeedsBom && (
        <div className="space-y-4 max-h-[60vh] overflow-auto pr-2">
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
            <p className="text-blue-400 text-sm">
              Add components, processes, and images for this
              product. Costs are calculated automatically.
            </p>
          </div>

          {/* Image Dropbox */}
          <div>
            <label className="block text-sm text-gray-400 mb-2">
              Product Images
            </label>
            <div
              role="button"
              tabIndex={0}
              aria-label="Add product images"
              onDrop={handleImageDrop}
              onDragOver={(e) => e.preventDefault()}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  document.getElementById("image-input")?.click();
                }
              }}
              className="border-2 border-dashed border-gray-600 rounded-lg p-4 text-center hover:border-blue-500 transition-colors cursor-pointer"
              onClick={() =>
                document.getElementById("image-input")?.click()
              }
            >
              <input
                type="file"
                id="image-input"
                multiple
                accept="image/*"
                onChange={handleImageSelect}
                className="hidden"
              />
              <svg
                className="w-8 h-8 mx-auto text-gray-500 mb-2"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
                />
              </svg>
              <p className="text-gray-400 text-sm">
                Drop images here or click to browse
              </p>
              <p className="text-gray-500 text-xs mt-1">
                For online marketplaces
              </p>
            </div>
            {imagePreviewUrls.length > 0 && (
              <div className="flex gap-2 mt-3 flex-wrap">
                {imagePreviewUrls.map((url, idx) => (
                  <div key={idx} className="relative group">
                    <img
                      src={url}
                      alt={`Preview ${idx + 1}`}
                      className="w-16 h-16 object-cover rounded-lg border border-gray-700"
                    />
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        removeImage(idx);
                      }}
                      className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 rounded-full text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* BOM Components Section */}
          <div className="border-t border-gray-700 pt-4">
            <div className="flex justify-between items-center mb-2">
              <label className="text-sm text-gray-400">
                BOM Components (Materials)
              </label>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowMaterialWizard(true)}
                  className="text-xs px-2 py-1 bg-pink-600/20 border border-pink-500/30 text-pink-400 rounded hover:bg-pink-600/30"
                >
                  + Add Filament
                </button>
                <button
                  type="button"
                  onClick={startSubComponent}
                  className="text-xs px-2 py-1 bg-purple-600/20 border border-purple-500/30 text-purple-400 rounded hover:bg-purple-600/30"
                >
                  + Create Component
                </button>
              </div>
            </div>

            {/* Inline Material (Filament) Wizard */}
            {showMaterialWizard && (
              <MaterialWizardInline
                newMaterial={newMaterial}
                setNewMaterial={setNewMaterial}
                materialTypes={materialTypes}
                allColors={allColors}
                loading={loading}
                onFetchColors={fetchColorsForType}
                onCreateMaterial={handleCreateMaterial}
                onCancel={() => setShowMaterialWizard(false)}
              />
            )}

            {/* Inline Sub-Component Wizard */}
            {showSubComponentWizard && (
              <SubComponentWizardInline
                subComponent={subComponent}
                setSubComponent={setSubComponent}
                loading={loading}
                onSave={handleSaveSubComponent}
                onCancel={() => setShowSubComponentWizard(false)}
              />
            )}

            <select
              onChange={(e) => {
                const val = e.target.value;
                // Handle both numeric IDs (items) and string IDs (materials)
                const comp = components.find(
                  (c) => String(c.id) === val
                );
                if (comp) addBomLine(comp);
                e.target.value = "";
              }}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            >
              <option value="">
                -- Select component or material to add --
              </option>
              <optgroup label="📦 Components & Supplies">
                {components
                  .filter(
                    (c) =>
                      !c.is_material &&
                      !bomLines.find(
                        (bl) => bl.component_id === c.id
                      )
                  )
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.sku} - {c.name} ($
                      {parseFloat(
                        c.standard_cost ||
                          c.average_cost ||
                          c.cost ||
                          0
                      ).toFixed(2)}
                      /{c.unit})
                    </option>
                  ))}
              </optgroup>
              <optgroup label="🎨 Filament / Materials">
                {components
                  .filter(
                    (c) =>
                      c.is_material &&
                      !bomLines.find(
                        (bl) => bl.component_id === c.id
                      )
                  )
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} {c.in_stock ? "" : "(Out of Stock)"}{" "}
                      ($
                      {parseFloat(c.standard_cost || 0).toFixed(3)}/
                      {c.unit})
                    </option>
                  ))}
              </optgroup>
            </select>
          </div>

          {/* BOM Lines */}
          {bomLines.length > 0 && (
            <div className="bg-gray-800/50 rounded-lg border border-gray-700 divide-y divide-gray-700">
              {bomLines.map((line) => (
                <div
                  key={line.component_id}
                  className="p-3 flex items-center gap-4"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium">
                        {line.component_name}
                      </span>
                      {line.is_material && (
                        <span className="text-xs bg-purple-600/30 text-purple-300 px-1.5 py-0.5 rounded">
                          Filament
                        </span>
                      )}
                    </div>
                    <div className="text-gray-500 text-xs font-mono">
                      {line.component_sku}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <label className="text-gray-400 text-sm">
                      Qty:
                    </label>
                    <input
                      type="number"
                      min="0.01"
                      step="0.01"
                      value={line.quantity}
                      onChange={(e) =>
                        updateBomQuantity(
                          line.component_id,
                          parseFloat(e.target.value) || 0.01
                        )
                      }
                      className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center"
                    />
                    <span className="text-gray-500 text-sm">
                      {line.component_unit}
                    </span>
                  </div>
                  <div className="text-gray-400 text-sm">
                    @ ${parseFloat(line.component_cost).toFixed(2)}
                  </div>
                  <div className="text-green-400 font-medium w-20 text-right">
                    $
                    {(line.quantity * line.component_cost).toFixed(
                      2
                    )}
                  </div>
                  <button
                    onClick={() => removeBomLine(line.component_id)}
                    className="text-red-400 hover:text-red-300 p-1"
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
              ))}
              <div className="p-3 flex justify-between items-center bg-gray-800/80">
                <span className="text-white font-medium">
                  Material Cost
                </span>
                <span className="text-green-400 font-bold">
                  ${calculatedCost.toFixed(2)}
                </span>
              </div>
            </div>
          )}

          {/* Processes/Routing Section */}
          <div className="border-t border-gray-700 pt-4">
            <div className="flex justify-between items-center mb-2">
              <label className="text-sm text-gray-400">
                Manufacturing Processes
              </label>
              {routingTemplates.length > 0 && (
                <select
                  value={selectedTemplate?.id ?? ""}
                  onChange={(e) => {
                    const tpl = routingTemplates.find(
                      (t) => t.id === parseInt(e.target.value)
                    );
                    applyRoutingTemplate(tpl || null);
                  }}
                  className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300"
                >
                  <option value="">Use Template...</option>
                  {routingTemplates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name || t.code}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <select
              onChange={(e) => {
                const wc = workCenters.find(
                  (w) => w.id === parseInt(e.target.value)
                );
                if (wc) addRoutingOperation(wc);
                e.target.value = "";
              }}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            >
              <option value="">-- Add process step --</option>
              {workCenters.map((wc) => (
                <option key={wc.id} value={wc.id}>
                  {wc.name} ($
                  {parseFloat(wc.total_rate_per_hour || 0).toFixed(
                    2
                  )}
                  /hr)
                </option>
              ))}
            </select>
          </div>

          {/* Routing Operations */}
          {routingOperations.length > 0 && (
            <div className="bg-purple-500/10 border border-purple-500/30 rounded-lg divide-y divide-purple-500/20">
              {routingOperations.map((op, idx) => (
                <div
                  key={op.id}
                  className="p-3 flex items-center gap-3"
                >
                  <div className="w-6 h-6 rounded-full bg-purple-600 text-white text-xs flex items-center justify-center font-medium">
                    {idx + 1}
                  </div>
                  <div className="flex-1">
                    <div className="text-white font-medium">
                      {op.operation_name}
                    </div>
                    <div className="text-purple-400 text-xs">
                      {op.work_center_code}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-gray-400">
                      Setup:
                    </div>
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={op.setup_time_minutes}
                      onChange={(e) =>
                        updateOperationTime(
                          op.id,
                          "setup_time_minutes",
                          e.target.value
                        )
                      }
                      className="w-14 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center text-sm"
                    />
                    <span className="text-gray-500 text-xs">
                      min
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="text-xs text-gray-400">
                      Run:
                    </div>
                    <input
                      type="number"
                      min="0"
                      step="1"
                      value={op.run_time_minutes}
                      onChange={(e) =>
                        updateOperationTime(
                          op.id,
                          "run_time_minutes",
                          e.target.value
                        )
                      }
                      className="w-14 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center text-sm"
                    />
                    <span className="text-gray-500 text-xs">
                      min
                    </span>
                  </div>
                  <div className="text-purple-400 font-medium w-16 text-right text-sm">
                    $
                    {(
                      ((op.setup_time_minutes +
                        op.run_time_minutes) /
                        60) *
                      op.rate_per_hour
                    ).toFixed(2)}
                  </div>
                  <button
                    onClick={() => removeRoutingOperation(op.id)}
                    className="text-red-400 hover:text-red-300 p-1"
                  >
                    <svg
                      className="w-4 h-4"
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
              ))}
              <div className="p-3 flex justify-between items-center bg-purple-900/30">
                <span className="text-white font-medium">
                  Labor Cost
                </span>
                <span className="text-purple-400 font-bold">
                  ${laborCost.toFixed(2)}
                </span>
              </div>
            </div>
          )}

          {/* Cost Summary */}
          {(bomLines.length > 0 ||
            routingOperations.length > 0) && (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex justify-between items-center">
                <div>
                  <span className="text-gray-400 text-sm">
                    Total Product Cost
                  </span>
                  <div className="text-xs text-gray-500">
                    Materials + Labor
                  </div>
                </div>
                <span className="text-green-400 font-bold text-xl">
                  ${totalCost.toFixed(2)}
                </span>
              </div>
            </div>
          )}

          <div className="flex justify-between pt-2">
            <button
              onClick={() => setItemWizardStep(1)}
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Back
            </button>
            <button
              onClick={() => setItemWizardStep(3)}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500"
            >
              Next: Set Pricing
            </button>
          </div>
        </div>
      )}

      {/* Item Wizard Step 3 (or 2 if no BOM): Pricing */}
      {itemWizardStep === (itemNeedsBom ? 3 : 2) && (
        <div className="space-y-4">
          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="grid grid-cols-3 gap-4">
              <div>
                <div className="text-gray-400 text-sm">
                  Material Cost
                </div>
                <div className="text-xl font-bold text-green-400">
                  ${calculatedCost.toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-gray-400 text-sm">
                  Labor Cost
                </div>
                <div className="text-xl font-bold text-purple-400">
                  ${laborCost.toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-gray-400 text-sm">
                  Total Cost
                </div>
                <div className="text-xl font-bold text-white">
                  ${totalCost.toFixed(2)}
                </div>
              </div>
            </div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
            <div className="text-gray-400 text-sm mb-2">
              <label>Target Margin %</label>
            </div>
            <input
              type="number"
              min="0"
              max="99"
              value={targetMargin}
              onChange={(e) =>
                setTargetMargin(parseFloat(e.target.value) || 0)
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white text-xl font-bold"
            />
          </div>

          <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
            <div className="flex justify-between items-center">
              <div>
                <div className="text-gray-400 text-sm">
                  Suggested Selling Price
                </div>
                <div className="text-3xl font-bold text-green-400">
                  ${suggestedPrice.toFixed(2)}
                </div>
                <div className="text-gray-500 text-xs mt-1">
                  Based on {targetMargin}% margin
                </div>
              </div>
              <button
                onClick={() =>
                  setNewItem({
                    ...newItem,
                    selling_price: suggestedPrice,
                  })
                }
                className="px-4 py-2 bg-green-600/20 border border-green-500/30 text-green-400 rounded-lg hover:bg-green-600/30"
              >
                Use Suggested
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Standard Cost
              </label>
              <input
                type="number"
                step="0.01"
                value={newItem.standard_cost ?? totalCost ?? ""}
                onChange={(e) =>
                  setNewItem({
                    ...newItem,
                    standard_cost:
                      parseFloat(e.target.value) || null,
                  })
                }
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
              <p className="text-xs text-gray-500 mt-1">
                Auto-filled from BOM + Labor
              </p>
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">
                Selling Price *
              </label>
              <input
                type="number"
                step="0.01"
                value={newItem.selling_price ?? ""}
                onChange={(e) =>
                  setNewItem({
                    ...newItem,
                    selling_price:
                      parseFloat(e.target.value) || null,
                  })
                }
                placeholder={suggestedPrice.toFixed(2)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>
          </div>

          {/* Margin Preview */}
          {newItem.selling_price > 0 && totalCost > 0 && (
            <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
              <div className="text-gray-400 text-sm mb-2">
                Actual Margin Preview
              </div>
              <div className="flex gap-8">
                <div>
                  <div className="text-gray-500 text-xs">
                    Gross Profit
                  </div>
                  <div className="text-white font-medium">
                    $
                    {(newItem.selling_price - totalCost).toFixed(2)}
                  </div>
                </div>
                <div>
                  <div className="text-gray-500 text-xs">
                    Margin %
                  </div>
                  <div
                    className={`font-medium ${
                      ((newItem.selling_price - totalCost) /
                        newItem.selling_price) *
                        100 >=
                      targetMargin
                        ? "text-green-400"
                        : "text-yellow-400"
                    }`}
                  >
                    {(
                      ((newItem.selling_price - totalCost) /
                        newItem.selling_price) *
                      100
                    ).toFixed(1)}
                    %
                  </div>
                </div>
                <div>
                  <div className="text-gray-500 text-xs">
                    Markup %
                  </div>
                  <div className="text-white font-medium">
                    {(
                      ((newItem.selling_price - totalCost) /
                        totalCost) *
                      100
                    ).toFixed(1)}
                    %
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="flex justify-between">
            <button
              onClick={() =>
                setItemWizardStep(itemNeedsBom ? 2 : 1)
              }
              className="px-4 py-2 text-gray-400 hover:text-white"
            >
              Back
            </button>
            <button
              onClick={onSave}
              disabled={loading || !newItem.name || !newItem.sku}
              className="px-6 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-500 hover:to-emerald-500 disabled:opacity-50"
            >
              {loading
                ? "Creating..."
                : "Create Product & Add to Order"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
