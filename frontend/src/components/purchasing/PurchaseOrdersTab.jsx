import { statusColors } from "./constants";
import EmptyState from "../EmptyState";

export default function PurchaseOrdersTab({
  filteredOrders,
  totalOrders,
  hasActiveFilters,
  onClearFilters,
  onCreatePO,
  onViewPO,
  onStatusChange,
  onReceivePO,
  onDeletePO,
  onCancelPO,
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-800/50">
          <tr>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              PO #
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Vendor
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Status
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Order Date
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Expected
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Received
            </th>
            <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Total
            </th>
            <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Lines
            </th>
            <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {filteredOrders.map((po) => (
            <tr
              key={po.id}
              className="border-b border-gray-800 hover:bg-gray-800/50"
            >
              <td className="py-3 px-4 text-white font-medium">
                {po.po_number}
              </td>
              <td className="py-3 px-4 text-gray-300">{po.vendor_name}</td>
              <td className="py-3 px-4">
                <span
                  className={`px-2 py-1 rounded-full text-xs ${
                    statusColors[po.status]
                  }`}
                >
                  {po.status}
                </span>
              </td>
              <td className="py-3 px-4 text-gray-400">
                {po.order_date
                  ? new Date(po.order_date + "T00:00:00").toLocaleDateString()
                  : "-"}
              </td>
              <td className="py-3 px-4 text-gray-400">
                {po.expected_date
                  ? new Date(po.expected_date + "T00:00:00").toLocaleDateString()
                  : "-"}
              </td>
              <td className="py-3 px-4 text-gray-400">
                {po.received_date
                  ? new Date(po.received_date + "T00:00:00").toLocaleDateString()
                  : "-"}
              </td>
              <td className="py-3 px-4 text-right text-green-400 font-medium">
                ${parseFloat(po.total_amount || 0).toFixed(2)}
              </td>
              <td className="py-3 px-4 text-center text-gray-400">
                {po.line_count}
              </td>
              <td className="py-3 px-4 text-right space-x-2">
                <button
                  onClick={() => onViewPO(po.id)}
                  className="text-blue-400 hover:text-blue-300 text-sm"
                >
                  View
                </button>
                {po.status === "draft" && (
                  <button
                    onClick={() => onStatusChange(po.id, "ordered")}
                    className="text-green-400 hover:text-green-300 text-sm"
                  >
                    Order
                  </button>
                )}
                {(po.status === "ordered" || po.status === "shipped") && (
                  <button
                    onClick={() => onReceivePO(po.id)}
                    className="text-purple-400 hover:text-purple-300 text-sm"
                  >
                    Receive
                  </button>
                )}
                {po.status === "draft" && (
                  <button
                    onClick={() => onDeletePO(po.id, po.po_number)}
                    className="text-red-400 hover:text-red-300 text-sm"
                  >
                    Delete
                  </button>
                )}
                {!["draft", "closed", "cancelled"].includes(po.status) && (
                  <button
                    onClick={() => onCancelPO(po.id, po.po_number)}
                    className="text-orange-400 hover:text-orange-300 text-sm"
                  >
                    Cancel
                  </button>
                )}
              </td>
            </tr>
          ))}
          {filteredOrders.length === 0 && (
            <tr>
              <td colSpan={9} className="py-4">
                {hasActiveFilters ? (
                  <EmptyState
                    icon="filter"
                    title="No purchase orders match your filters"
                    onClearFilters={onClearFilters}
                  />
                ) : (
                  <EmptyState
                    icon="inventory"
                    title="No purchase orders yet"
                    description="Create a purchase order to restock your materials."
                    actionLabel="Create PO"
                    onAction={onCreatePO}
                  />
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
