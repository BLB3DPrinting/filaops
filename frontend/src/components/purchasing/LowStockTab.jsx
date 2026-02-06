import { statusColors } from "./constants";

/**
 * Render the low-stock management tab with summary cards, an optional MRP shortage alert, and an actionable table of items requiring attention.
 *
 * @param {Object[]} lowStockItems - Array of items flagged for attention; each item should include fields like `id`, `name`, `sku`, `available_qty`, `reorder_point`, `shortfall`, `mrp_shortage`, `shortage_source`, `unit`, and `category_name`.
 * @param {Object} [lowStockSummary] - Aggregate counts and values for summary cards; expected fields include `critical_count`, `urgent_count`, `low_count`, `total_shortfall_value`, and `mrp_shortage_count`.
 * @param {boolean} lowStockLoading - Whether low-stock data is currently loading.
 * @param {Set<number|string>} selectedLowStockIds - Set of item IDs currently selected in the table.
 * @param {Object[]} selectedItemsByVendor - Groups of selected items keyed by vendor; each group should include `vendorId`, `vendorName`, `items` (array), and `totalValue`.
 * @param {(id: number|string) => void} toggleLowStockItem - Toggle selection for a single item ID.
 * @param {() => void} toggleAllLowStock - Toggle selection of all visible low-stock items.
 * @param {() => void} clearLowStockSelection - Clear all selected low-stock items.
 * @param {() => void} fetchLowStock - Refresh the low-stock data.
 * @param {(item: Object) => void} onCreatePO - Create a purchase order for a single item.
 * @param {(vendorGroup: Object) => void} onCreatePOFromSelection - Create a purchase order from a vendor group of selected items.
 * @returns {JSX.Element} The rendered Low Stock tab UI.
 */
export default function LowStockTab({
  lowStockItems,
  lowStockSummary,
  lowStockLoading,
  selectedLowStockIds,
  selectedItemsByVendor,
  toggleLowStockItem,
  toggleAllLowStock,
  clearLowStockSelection,
  fetchLowStock,
  onCreatePO,
  onCreatePOFromSelection,
}) {
  return (
    <div className="space-y-6">
      {/* Enhanced Summary Cards */}
      {lowStockSummary && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
            <div className="text-3xl font-bold text-red-400">
              {lowStockSummary.critical_count || 0}
            </div>
            <div className="text-sm text-gray-400">Critical (Out of Stock)</div>
          </div>
          <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4">
            <div className="text-3xl font-bold text-orange-400">
              {lowStockSummary.urgent_count || 0}
            </div>
            <div className="text-sm text-gray-400">Urgent (&lt;50% Reorder)</div>
          </div>
          <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
            <div className="text-3xl font-bold text-yellow-400">
              {lowStockSummary.low_count || 0}
            </div>
            <div className="text-sm text-gray-400">Low Stock</div>
          </div>
          <div className="bg-gray-700/30 border border-gray-600 rounded-xl p-4">
            <div className="text-3xl font-bold text-white">
              ${lowStockSummary.total_shortfall_value?.toFixed(0) || "0"}
            </div>
            <div className="text-sm text-gray-400">Shortfall Value</div>
          </div>
        </div>
      )}

      {/* MRP Shortage Alert */}
      {lowStockSummary?.mrp_shortage_count > 0 && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 flex items-center gap-3">
          <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-blue-300 text-sm">
            <strong>{lowStockSummary.mrp_shortage_count}</strong> items have MRP-driven shortages from active sales orders
          </span>
        </div>
      )}

      {/* Low Stock Table */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="p-4 border-b border-gray-800 flex justify-between items-center">
          <div>
            <h3 className="text-lg font-semibold text-white">
              Items Requiring Attention
            </h3>
            <p className="text-sm text-gray-400 mt-0.5">
              {lowStockItems.length} items below reorder point or with MRP shortages
              {selectedLowStockIds.size > 0 && (
                <span className="ml-2 text-blue-400">({selectedLowStockIds.size} selected)</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* Create PO Dropdown - shows when items are selected */}
            {selectedLowStockIds.size > 0 && selectedItemsByVendor.length > 0 && (
              <div className="relative group">
                <button className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm text-white flex items-center gap-2">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  Create PO ({selectedLowStockIds.size})
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
                <div className="absolute right-0 mt-1 w-64 bg-gray-800 border border-gray-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                  {selectedItemsByVendor.map((group) => (
                    <button
                      key={group.vendorId || 'no_vendor'}
                      onClick={() => onCreatePOFromSelection(group)}
                      disabled={!group.vendorId}
                      className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-700 first:rounded-t-lg last:rounded-b-lg ${
                        !group.vendorId ? 'text-gray-500 cursor-not-allowed' : 'text-white'
                      }`}
                    >
                      <div className="font-medium">{group.vendorName}</div>
                      <div className="text-xs text-gray-400">
                        {group.items.length} items · ${group.totalValue.toFixed(2)}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Clear Selection */}
            {selectedLowStockIds.size > 0 && (
              <button
                onClick={clearLowStockSelection}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded-lg text-sm text-gray-300"
              >
                Clear
              </button>
            )}

            <button
              onClick={fetchLowStock}
              disabled={lowStockLoading}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-gray-300 flex items-center gap-2"
            >
              <svg className={`w-4 h-4 ${lowStockLoading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {lowStockLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>

        {lowStockLoading ? (
          <div className="p-8 text-center text-gray-400">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-3"></div>
            Loading low stock items...
          </div>
        ) : lowStockItems.length === 0 ? (
          <div className="p-12 text-center">
            <svg className="w-16 h-16 mx-auto text-green-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="text-green-400 text-lg font-medium mb-2">
              All Stock Levels OK
            </div>
            <p className="text-gray-400 text-sm">
              No items are currently below their reorder point.
            </p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-center py-3 px-2 text-xs font-medium text-gray-400 uppercase w-10">
                  <input
                    type="checkbox"
                    checked={lowStockItems.length > 0 && selectedLowStockIds.size === lowStockItems.length}
                    onChange={toggleAllLowStock}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-900"
                  />
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Urgency
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Item
                </th>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Category
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Available
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Reorder Pt
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Shortfall
                </th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {lowStockItems.map((item) => {
                const isCritical = item.available_qty <= 0;
                const isUrgent = !isCritical && item.reorder_point && item.available_qty <= item.reorder_point * 0.5;
                const hasMrpShortage = item.mrp_shortage > 0;

                return (
                  <tr
                    key={item.id}
                    className={`border-b border-gray-800 hover:bg-gray-800/30 ${
                      isCritical ? 'bg-red-500/5' : isUrgent ? 'bg-orange-500/5' : ''
                    } ${selectedLowStockIds.has(item.id) ? 'bg-blue-500/10' : ''}`}
                  >
                    <td className="py-3 px-2 text-center">
                      <input
                        type="checkbox"
                        checked={selectedLowStockIds.has(item.id)}
                        onChange={() => toggleLowStockItem(item.id)}
                        className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-blue-600 focus:ring-blue-500 focus:ring-offset-gray-900"
                      />
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        {isCritical && (
                          <span className="px-2 py-0.5 bg-red-500/20 text-red-400 rounded text-xs font-medium">
                            CRITICAL
                          </span>
                        )}
                        {isUrgent && (
                          <span className="px-2 py-0.5 bg-orange-500/20 text-orange-400 rounded text-xs font-medium">
                            URGENT
                          </span>
                        )}
                        {!isCritical && !isUrgent && (
                          <span className="px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded text-xs font-medium">
                            LOW
                          </span>
                        )}
                        {hasMrpShortage && (
                          <span className="px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded text-xs" title="MRP shortage from active orders">
                            MRP
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="text-white font-medium">
                        {item.name}
                      </div>
                      <div className="text-gray-500 text-xs">{item.sku}</div>
                    </td>
                    <td className="py-3 px-4 text-gray-400 text-sm">
                      {item.category_name || "-"}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span
                        className={
                          isCritical
                            ? "text-red-400 font-medium"
                            : isUrgent
                            ? "text-orange-400"
                            : "text-yellow-400"
                        }
                      >
                        {item.available_qty?.toFixed(2)} {item.unit}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-right text-gray-400">
                      {item.reorder_point?.toFixed(2) || "-"} {item.unit}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className="text-red-400 font-medium">
                        -{item.shortfall?.toFixed(2)} {item.unit}
                      </span>
                      {item.mrp_shortage > 0 && item.shortage_source === "mrp" && (
                        <div className="text-xs text-blue-400 mt-1">
                          (MRP: {item.mrp_shortage.toFixed(2)})
                        </div>
                      )}
                      {item.mrp_shortage > 0 && item.shortage_source === "both" && (
                        <div className="text-xs text-purple-400 mt-1">
                          +MRP: {item.mrp_shortage.toFixed(2)}
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex gap-2 justify-end">
                        <button
                          onClick={() => onCreatePO(item)}
                          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 rounded text-xs text-white"
                        >
                          Create PO
                        </button>
                        <button
                          onClick={() =>
                            (window.location.href = `/admin/items?edit=${item.id}`)
                          }
                          className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs text-gray-300"
                        >
                          Edit Item
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}