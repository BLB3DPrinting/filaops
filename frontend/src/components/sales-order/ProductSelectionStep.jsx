import { useState } from "react";
import ItemCreationWizard from "./ItemCreationWizard";

const TABS = [
  { id: "products", label: "Finished Goods" },
  { id: "materials", label: "Raw Materials" },
];

export default function ProductSelectionStep({
  products,
  productSearch,
  setProductSearch,
  lineItems,
  addLineItem,
  addMaterialLineItem,
  removeLineItem,
  updateLineQuantity,
  updateLinePrice,
  orderTotal,
  startNewItem,
  materialInventory = [],
  materialSearch = "",
  setMaterialSearch,
  // Item creation wizard props
  showItemWizard,
  itemWizardProps,
}) {
  const [activeTab, setActiveTab] = useState("products");

  if (showItemWizard) {
    return (
      <div className="space-y-6">
        <ItemCreationWizard {...itemWizardProps} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-white">
          Add Line Items
        </h3>
        <button
          onClick={startNewItem}
          className="px-4 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg hover:from-green-500 hover:to-emerald-500 text-sm"
        >
          + Create New Product
        </button>
      </div>

      {/* Tab Toggle */}
      <div className="flex gap-1 bg-gray-800 p-1 rounded-lg">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-white hover:bg-gray-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Products Tab */}
      {activeTab === "products" && (
        <>
          {/* Product Search */}
          <div className="relative">
            <input
              type="text"
              placeholder="Search products by SKU or name..."
              value={productSearch}
              onChange={(e) => setProductSearch(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white pl-10"
            />
            <svg
              className="w-5 h-5 absolute left-3 top-3.5 text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            {productSearch && (
              <button
                onClick={() => setProductSearch("")}
                className="absolute right-3 top-3.5 text-gray-500 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Product Grid */}
          <div className="grid grid-cols-3 gap-3 max-h-[300px] overflow-auto">
            {(() => {
              const searchTerm = productSearch.trim().toLowerCase();
              const filteredProducts = products.filter((p) => {
                if (!p.has_bom && !p.has_routing) return false;
                if (!searchTerm) return true;
                const nameMatch = (p.name || "").toLowerCase().includes(searchTerm);
                const skuMatch = (p.sku || "").toLowerCase().includes(searchTerm);
                return nameMatch || skuMatch;
              });

              if (filteredProducts.length === 0) {
                return (
                  <div className="col-span-3 text-center py-8 text-gray-500">
                    {searchTerm
                      ? `No sellable products found matching "${productSearch}"`
                      : "No sellable products available. Create a BOM or routing for your products to sell them."}
                  </div>
                );
              }

              return filteredProducts.map((product) => (
                <button
                  key={product.id}
                  onClick={() => addLineItem(product)}
                  className="text-left p-3 bg-gray-800 border border-gray-700 rounded-lg hover:border-blue-500 hover:bg-gray-800/80 transition-colors"
                >
                  <div className="text-white font-medium text-sm truncate">
                    {product.name}
                  </div>
                  <div className="text-gray-500 text-xs font-mono">
                    {product.sku}
                  </div>
                  <div className="text-green-400 text-sm mt-1">
                    ${parseFloat(product.selling_price || 0).toFixed(2)}
                  </div>
                </button>
              ));
            })()}
          </div>
        </>
      )}

      {/* Materials Tab */}
      {activeTab === "materials" && (
        <>
          {/* Material Search */}
          <div className="relative">
            <input
              type="text"
              placeholder="Search materials by SKU, type, or color..."
              value={materialSearch}
              onChange={(e) => setMaterialSearch(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white pl-10"
            />
            <svg
              className="w-5 h-5 absolute left-3 top-3.5 text-gray-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            {materialSearch && (
              <button
                onClick={() => setMaterialSearch("")}
                className="absolute right-3 top-3.5 text-gray-500 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>

          {/* Material Grid */}
          <div className="grid grid-cols-3 gap-3 max-h-[300px] overflow-auto">
            {(() => {
              const searchTerm = (materialSearch || "").trim().toLowerCase();
              const filtered = materialInventory.filter((m) => {
                if (!searchTerm) return true;
                const nameMatch = (m.name || "").toLowerCase().includes(searchTerm);
                const skuMatch = (m.sku || "").toLowerCase().includes(searchTerm);
                const typeMatch = (m.material_type_name || "").toLowerCase().includes(searchTerm);
                const colorMatch = (m.color_name || "").toLowerCase().includes(searchTerm);
                return nameMatch || skuMatch || typeMatch || colorMatch;
              });

              if (filtered.length === 0) {
                return (
                  <div className="col-span-3 text-center py-8 text-gray-500">
                    {searchTerm
                      ? `No materials found matching "${materialSearch}"`
                      : "No material inventory available. Add materials in the Materials module."}
                  </div>
                );
              }

              return filtered.map((material) => (
                <button
                  key={material.id}
                  onClick={() => addMaterialLineItem(material)}
                  className="text-left p-3 bg-gray-800 border border-gray-700 rounded-lg hover:border-orange-500 hover:bg-gray-800/80 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    {material.color_hex && (
                      <span
                        className="w-3 h-3 rounded-full border border-gray-600 flex-shrink-0"
                        style={{ backgroundColor: material.color_hex }}
                      />
                    )}
                    <div className="text-white font-medium text-sm truncate">
                      {material.name}
                    </div>
                  </div>
                  <div className="text-gray-500 text-xs font-mono mt-1">
                    {material.sku}
                  </div>
                  <div className="flex justify-between items-center mt-1">
                    <span className="text-orange-400 text-sm">
                      ${parseFloat(material.cost_per_kg || 0).toFixed(2)}/kg
                    </span>
                    {material.in_stock ? (
                      <span className="text-green-400 text-xs">
                        {material.quantity_kg.toFixed(1)}kg
                      </span>
                    ) : (
                      <span className="text-red-400 text-xs">Out of stock</span>
                    )}
                  </div>
                </button>
              ));
            })()}
          </div>
        </>
      )}

      {/* Selected Line Items */}
      {lineItems.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-md font-medium text-white">
            Order Lines
          </h4>
          <div className="bg-gray-800/50 rounded-lg border border-gray-700 divide-y divide-gray-700">
            {lineItems.map((li) => (
              <div
                key={li._key}
                className="p-3 flex items-center gap-4"
              >
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    {li.line_type === "material" && (
                      <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-orange-500/20 text-orange-400 border border-orange-500/30 rounded">
                        RAW
                      </span>
                    )}
                    <div className="text-white font-medium">
                      {li.line_type === "material"
                        ? li.material?.name
                        : li.product?.name}
                    </div>
                  </div>
                  <div className="text-gray-500 text-xs font-mono">
                    {li.line_type === "material"
                      ? li.material?.sku
                      : li.product?.sku}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-gray-400 text-sm">
                    Qty:
                  </label>
                  <input
                    type="number"
                    min={li.line_type === "material" ? "0.01" : "1"}
                    step={li.line_type === "material" ? "0.01" : "1"}
                    value={li.quantity}
                    onChange={(e) =>
                      updateLineQuantity(
                        li._key,
                        li.line_type === "material"
                          ? parseFloat(e.target.value) || 0.01
                          : parseInt(e.target.value, 10) || 1
                      )
                    }
                    className="w-16 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-center"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-gray-400 text-sm">$</label>
                  <input
                    type="number"
                    step="0.01"
                    value={li.unit_price}
                    onChange={(e) =>
                      updateLinePrice(
                        li._key,
                        parseFloat(e.target.value) || 0
                      )
                    }
                    className="w-24 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-right"
                  />
                </div>
                <div className="text-green-400 font-medium w-24 text-right">
                  ${(li.quantity * li.unit_price).toFixed(2)}
                </div>
                <button
                  onClick={() => removeLineItem(li._key)}
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
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))}
            <div className="p-3 flex justify-between items-center bg-gray-800/80">
              <span className="text-white font-medium">
                Order Total
              </span>
              <span className="text-green-400 font-bold text-lg">
                ${orderTotal.toFixed(2)}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
