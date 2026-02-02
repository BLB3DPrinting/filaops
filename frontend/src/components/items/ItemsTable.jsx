/**
 * ItemsTable - Table view for items with sorting, inline editing, bulk selection, and pagination.
 */
// Item type options (for display labels)
const ITEM_TYPES = [
  { value: "finished_good", label: "Finished Good", color: "blue" },
  { value: "component", label: "Component", color: "purple" },
  { value: "material", label: "Material", color: "orange" },
  { value: "filament", label: "Filament (Legacy)", color: "orange" },
  { value: "supply", label: "Supply", color: "yellow" },
  { value: "service", label: "Service", color: "green" },
];

const getItemTypeStyle = (type, hasFilament = false) => {
  if (hasFilament) {
    return "bg-orange-500/20 text-orange-400";
  }
  const found = ITEM_TYPES.find((t) => t.value === type);
  if (!found) return "bg-gray-500/20 text-gray-400";
  return {
    blue: "bg-blue-500/20 text-blue-400",
    purple: "bg-purple-500/20 text-purple-400",
    orange: "bg-orange-500/20 text-orange-400",
    yellow: "bg-yellow-500/20 text-yellow-400",
    green: "bg-green-500/20 text-green-400",
  }[found.color];
};

function SortIndicator({ columnKey, sortConfig }) {
  if (sortConfig.key !== columnKey && !(sortConfig.key === "stock_status" && columnKey === "available_qty")) {
    return <span className="text-gray-600 ml-1">↕</span>;
  }
  return (
    <span className="text-blue-400 ml-1">
      {sortConfig.direction === "asc" ? "↑" : "↓"}
    </span>
  );
}

export default function ItemsTable({
  items,
  loading,
  // Selection
  selectedItems,
  onSelectAll,
  onSelectItem,
  isAllSelected,
  isIndeterminate,
  // Sorting
  sortConfig,
  onSort,
  // Inline qty editing
  editingQtyItem,
  editingQtyValue,
  onEditingQtyValueChange,
  adjustmentReason,
  adjustingQty,
  onStartEditQty,
  onSaveQtyAdjustment,
  onCancelEditQty,
  onShowAdjustmentModal,
  // Pagination
  pagination,
  onPageChange,
  onPageSizeChange,
  totalPages,
  canGoPrev,
  canGoNext,
  // Actions
  onEditItem,
  onEditRouting,
}) {
  return (
    <div className={`bg-gray-900 border border-gray-800 rounded-xl overflow-hidden transition-opacity ${loading ? 'opacity-60' : ''}`}>
      <table className="w-full">
        <thead className="bg-gray-800/50">
          <tr>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase w-12">
              <input
                type="checkbox"
                checked={isAllSelected}
                ref={(input) => {
                  if (input) input.indeterminate = isIndeterminate;
                }}
                onChange={onSelectAll}
                className="rounded"
              />
            </th>
            <th
              className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("sku")}
            >
              SKU <SortIndicator columnKey="sku" sortConfig={sortConfig} />
            </th>
            <th
              className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("name")}
            >
              Name <SortIndicator columnKey="name" sortConfig={sortConfig} />
            </th>
            <th
              className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("item_type")}
            >
              Type <SortIndicator columnKey="item_type" sortConfig={sortConfig} />
            </th>
            <th
              className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("category_name")}
            >
              Category <SortIndicator columnKey="category_name" sortConfig={sortConfig} />
            </th>
            <th
              className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("standard_cost")}
            >
              Std Cost <SortIndicator columnKey="standard_cost" sortConfig={sortConfig} />
            </th>
            <th
              className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("selling_price")}
            >
              Price <SortIndicator columnKey="selling_price" sortConfig={sortConfig} />
            </th>
            <th
              className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("on_hand_qty")}
            >
              On Hand <SortIndicator columnKey="on_hand_qty" sortConfig={sortConfig} />
            </th>
            <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Reserved
            </th>
            <th
              className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("available_qty")}
            >
              Available <SortIndicator columnKey="available_qty" sortConfig={sortConfig} />
            </th>
            <th
              className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("stocking_policy")}
            >
              Policy <SortIndicator columnKey="stocking_policy" sortConfig={sortConfig} />
            </th>
            <th
              className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("reorder_point")}
            >
              Reorder Pt <SortIndicator columnKey="reorder_point" sortConfig={sortConfig} />
            </th>
            <th
              className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase cursor-pointer hover:text-white select-none"
              onClick={() => onSort("active")}
            >
              Status <SortIndicator columnKey="active" sortConfig={sortConfig} />
            </th>
            <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr
              key={item.id}
              className="border-b border-gray-800 hover:bg-gray-800/50"
            >
              <td className="py-3 px-4">
                <input
                  type="checkbox"
                  checked={selectedItems.has(item.id)}
                  onChange={() => onSelectItem(item.id)}
                  className="rounded"
                />
              </td>
              <td className="py-3 px-4 text-white font-mono text-sm">
                {item.sku}
              </td>
              <td className="py-3 px-4 text-gray-300">{item.name}</td>
              <td className="py-3 px-4">
                <span
                  className={`px-2 py-1 rounded-full text-xs ${getItemTypeStyle(
                    item.item_type,
                    !!item.material_type_id
                  )}`}
                >
                  {item.material_type_id
                    ? "Filament"
                    : ITEM_TYPES.find((t) => t.value === item.item_type)
                        ?.label || item.item_type}
                </span>
              </td>
              <td className="py-3 px-4 text-gray-400">
                {item.category_name || "-"}
              </td>
              <td className="py-3 px-4 text-right text-gray-400">
                {item.standard_cost ? (
                  item.material_type_id ? (
                    <div className="flex flex-col items-end">
                      <span>${parseFloat(item.standard_cost).toFixed(2)}/KG</span>
                      <span className="text-xs text-gray-500">
                        ${(parseFloat(item.standard_cost) / 1000).toFixed(4)}/g
                      </span>
                    </div>
                  ) : (
                    `$${parseFloat(item.standard_cost).toFixed(2)}`
                  )
                ) : (
                  "-"
                )}
              </td>
              <td className="py-3 px-4 text-right text-green-400">
                {item.material_type_id || item.item_type === "supply"
                  ? "-"
                  : item.selling_price
                  ? `$${parseFloat(item.selling_price).toFixed(2)}`
                  : "-"}
              </td>
              {/* On Hand - Inline Editable */}
              <td className="py-3 px-4 text-right">
                {editingQtyItem?.id === item.id ? (
                  <div className="flex items-center gap-2">
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        value={editingQtyValue}
                        onChange={(e) => onEditingQtyValueChange(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            if (!adjustmentReason.trim()) {
                              onShowAdjustmentModal();
                            } else {
                              onSaveQtyAdjustment(item);
                            }
                          } else if (e.key === "Escape") {
                            onCancelEditQty();
                          }
                        }}
                        className="w-24 bg-gray-800 border border-blue-500 rounded px-2 py-1 text-white text-sm"
                        autoFocus
                        step={item.material_type_id ? "1" : "0.01"}
                        min="0"
                      />
                      <span className="text-gray-400 text-xs">
                        {item.material_type_id ? "g" : (item.unit || "EA")}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        if (!adjustmentReason.trim()) {
                          onShowAdjustmentModal();
                        } else {
                          onSaveQtyAdjustment(item);
                        }
                      }}
                      disabled={adjustingQty}
                      className="text-green-400 hover:text-green-300 text-sm disabled:opacity-50"
                      title="Save"
                    >
                      ✓
                    </button>
                    <button
                      onClick={onCancelEditQty}
                      className="text-red-400 hover:text-red-300 text-sm"
                      title="Cancel"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => onStartEditQty(item)}
                    className={`text-right hover:bg-gray-800 px-2 py-1 rounded ${
                      item.needs_reorder ? "text-red-400" : "text-gray-300"
                    } hover:text-white`}
                    title="Click to edit on-hand quantity"
                  >
                    {item.on_hand_qty != null ? (
                      <>
                        {item.material_type_id
                          ? parseFloat(item.on_hand_qty).toFixed(0)
                          : parseFloat(item.on_hand_qty).toFixed(0)}
                        <span className="text-gray-500 text-xs ml-1">
                          {item.material_type_id ? "g" : (item.unit || "EA")}
                        </span>
                      </>
                    ) : (
                      "-"
                    )}
                  </button>
                )}
              </td>
              <td className="py-3 px-4 text-right text-yellow-400">
                {item.allocated_qty != null &&
                parseFloat(item.allocated_qty) > 0 ? (
                  <>
                    {item.material_type_id
                      ? (parseFloat(item.allocated_qty) * 1000).toFixed(0)
                      : parseFloat(item.allocated_qty).toFixed(0)}
                    <span className="text-gray-500 text-xs ml-1">
                      {item.material_type_id ? "g" : (item.unit || "EA")}
                    </span>
                  </>
                ) : (
                  "-"
                )}
              </td>
              <td className="py-3 px-4 text-right">
                <span
                  className={
                    item.available_qty != null &&
                    parseFloat(item.available_qty) <= 0
                      ? "text-red-400"
                      : item.needs_reorder
                      ? "text-yellow-400"
                      : "text-green-400"
                  }
                >
                  {item.available_qty != null ? (
                    <>
                      {item.material_type_id
                        ? (parseFloat(item.available_qty) * 1000).toFixed(0)
                        : parseFloat(item.available_qty).toFixed(0)}
                      <span className="text-gray-500 text-xs ml-1">
                        {item.material_type_id ? "g" : (item.unit || "EA")}
                      </span>
                    </>
                  ) : (
                    "-"
                  )}
                </span>
              </td>
              <td className="py-3 px-4 text-center">
                <span
                  className={`px-2 py-0.5 rounded text-xs ${
                    item.stocking_policy === "stocked"
                      ? "bg-purple-500/20 text-purple-400"
                      : "text-gray-500"
                  }`}
                >
                  {item.stocking_policy === "stocked" ? "Stocked" : "MRP"}
                </span>
              </td>
              <td className="py-3 px-4 text-right text-gray-400">
                {item.stocking_policy === "stocked" && item.reorder_point != null ? (
                  <>
                    {parseFloat(item.reorder_point).toLocaleString()}
                    <span className="text-gray-500 text-xs ml-1">
                      {item.material_type_id ? "g" : (item.unit || "EA")}
                    </span>
                  </>
                ) : (
                  "-"
                )}
              </td>
              <td className="py-3 px-4 text-center">
                <span
                  className={`px-2 py-1 rounded-full text-xs ${
                    item.active
                      ? "bg-green-500/20 text-green-400"
                      : "bg-gray-500/20 text-gray-400"
                  }`}
                >
                  {item.active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="py-3 px-4 text-right">
                <div className="flex gap-2 justify-end">
                  <button
                    onClick={() => onEditItem(item)}
                    className="text-blue-400 hover:text-blue-300 text-sm"
                  >
                    Edit
                  </button>
                  {(item.procurement_type === "make" ||
                    item.procurement_type === "make_or_buy") && (
                    <>
                      <button
                        onClick={() => onEditRouting(item)}
                        className="text-green-400 hover:text-green-300 text-sm"
                        title="Edit Routing & Materials (BOM is now integrated into Routing)"
                      >
                        Route/BOM
                      </button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td
                colSpan={14}
                className="py-12 text-center text-gray-500"
              >
                No items found
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Pagination Controls */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-gray-700">
        <div className="text-sm text-gray-400">
          {(() => {
            const start =
              pagination.total === 0
                ? 0
                : (pagination.page - 1) * pagination.pageSize + 1;
            const end =
              pagination.total === 0
                ? 0
                : Math.min(
                    pagination.page * pagination.pageSize,
                    pagination.total
                  );
            return `Showing ${start} - ${end} of ${pagination.total} items`;
          })()}
        </div>
        <div className="flex items-center gap-2">
          <select
            value={pagination.pageSize}
            onChange={(e) => onPageSizeChange(parseInt(e.target.value))}
            className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm"
          >
            <option value={25}>25 per page</option>
            <option value={50}>50 per page</option>
            <option value={100}>100 per page</option>
            <option value={200}>200 per page</option>
          </select>
          <button
            onClick={() => onPageChange(pagination.page - 1)}
            disabled={!canGoPrev}
            className="px-3 py-1 bg-gray-700 border border-gray-600 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-600"
          >
            Previous
          </button>
          <span className="text-sm text-gray-400">
            Page {pagination.page} of {totalPages || 1}
          </span>
          <button
            onClick={() => onPageChange(pagination.page + 1)}
            disabled={!canGoNext}
            className="px-3 py-1 bg-gray-700 border border-gray-600 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-gray-600"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
