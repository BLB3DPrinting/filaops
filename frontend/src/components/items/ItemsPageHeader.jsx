/**
 * Header bar for the Items page.
 * Contains page title, view toggle, action buttons, and recost/pricing result banners.
 */
import { useFormatCurrency } from "../../hooks/useFormatCurrency";

export default function ItemsPageHeader({
  viewMode,
  onViewModeChange,
  loading,
  recosting,
  recostResult,
  onRefresh,
  onRecostAll,
  onClearRecostResult,
  onSuggestPrices,
  suggestPricesResult,
  onClearSuggestPricesResult,
  onNewMaterial,
  onNewItem,
}) {
  const formatCurrency = useFormatCurrency();
  return (
    <>
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Items</h1>
          <p className="text-gray-400 mt-1">
            Manage products, components, supplies, and services
          </p>
        </div>
        <div className="flex gap-2">
          {/* View Toggle */}
          <div className="flex bg-gray-800 rounded-lg p-1 border border-gray-700">
            <button
              data-testid="view-toggle-table"
              onClick={() => onViewModeChange("table")}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                viewMode === "table"
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              Table
            </button>
            <button
              data-testid="view-toggle-cards"
              onClick={() => onViewModeChange("cards")}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                viewMode === "cards"
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              Cards
            </button>
          </div>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50"
            title="Refresh items"
          >
            {loading ? "Loading..." : "↻ Refresh"}
          </button>
          <button
            onClick={onRecostAll}
            disabled={recosting}
            className="px-4 py-2 bg-gray-800 border border-gray-700 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white disabled:opacity-50"
          >
            {recosting ? "Recosting..." : "Recost All"}
          </button>
          <button
            onClick={onSuggestPrices}
            className="px-4 py-2 bg-gray-800 border border-gray-700 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white"
          >
            Suggest Prices
          </button>
          <button
            onClick={onNewMaterial}
            className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-medium transition-colors"
          >
            + New Material
          </button>
          <button
            onClick={onNewItem}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
          >
            + New Item
          </button>
        </div>
      </div>

      {/* Recost Result */}
      {recostResult && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-green-400 font-medium">
                Recost complete: {recostResult.updated} items updated,{" "}
                {recostResult.skipped} skipped
              </p>
              {recostResult.items?.length > 0 && (
                <div className="mt-2 text-sm text-gray-400 max-h-32 overflow-auto">
                  {recostResult.items.slice(0, 10).map((item, i) => (
                    <div key={i}>
                      {item.sku}: ${item.old_cost.toFixed(2)} → $
                      {item.new_cost.toFixed(2)} ({item.cost_source})
                    </div>
                  ))}
                  {recostResult.items.length > 10 && (
                    <div className="text-gray-500">
                      ...and {recostResult.items.length - 10} more
                    </div>
                  )}
                </div>
              )}
            </div>
            <button
              onClick={onClearRecostResult}
              className="text-gray-500 hover:text-white"
            >
              x
            </button>
          </div>
        </div>
      )}

      {/* Suggest Prices Result */}
      {suggestPricesResult && (
        <div className="bg-purple-500/10 border border-purple-500/30 rounded-xl p-4">
          <div className="flex justify-between items-start">
            <div>
              <p className="text-purple-400 font-medium">
                Prices updated: {suggestPricesResult.updated} items updated,{" "}
                {suggestPricesResult.skipped} skipped
              </p>
              {suggestPricesResult.items?.length > 0 && (
                <div className="mt-2 text-sm text-gray-400 max-h-32 overflow-auto">
                  {suggestPricesResult.items.slice(0, 10).map((item, i) => (
                    <div key={i}>
                      {item.sku}: {item.old_price != null ? formatCurrency(item.old_price) : "none"} →{" "}
                      {formatCurrency(item.new_price)}
                    </div>
                  ))}
                  {suggestPricesResult.items.length > 10 && (
                    <div className="text-gray-500">
                      ...and {suggestPricesResult.items.length - 10} more
                    </div>
                  )}
                </div>
              )}
            </div>
            <button
              onClick={onClearSuggestPricesResult}
              className="text-gray-500 hover:text-white"
            >
              x
            </button>
          </div>
        </div>
      )}
    </>
  );
}
