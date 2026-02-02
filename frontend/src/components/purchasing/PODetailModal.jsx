/**
 * PODetailModal - View purchase order details with actions
 */
import Modal from "../Modal";
import POActivityTimeline from "../POActivityTimeline";
import DocumentUploadPanel from "./DocumentUploadPanel";
import { statusColors } from "./constants";

export default function PODetailModal({
  po,
  onClose,
  onStatusChange,
  onEdit,
  onReceive,
}) {

  return (
    <Modal isOpen={true} onClose={onClose} title={`Purchase Order ${po.po_number}`} className="max-w-3xl w-full mx-auto p-6 max-h-[90vh] overflow-y-auto">
          <div className="flex justify-between items-center mb-6">
            <div>
              <h3 className="text-lg font-semibold text-white">
                {po.po_number}
              </h3>
              <p className="text-sm text-gray-400">{po.vendor_name}</p>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`px-3 py-1 rounded-full text-sm ${
                  statusColors[po.status]
                }`}
              >
                {po.status}
              </span>
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-white"
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
          </div>

          {/* Dates */}
          <div className="grid grid-cols-4 gap-4 mb-6 text-sm">
            <div>
              <span className="text-gray-400">Order Date</span>
              <p className="text-white">
                {po.order_date
                  ? new Date(po.order_date).toLocaleDateString()
                  : "-"}
              </p>
            </div>
            <div>
              <span className="text-gray-400">Expected</span>
              <p className="text-white">
                {po.expected_date
                  ? new Date(po.expected_date).toLocaleDateString()
                  : "-"}
              </p>
            </div>
            <div>
              <span className="text-gray-400">Shipped</span>
              <p className="text-white">
                {po.shipped_date
                  ? new Date(po.shipped_date).toLocaleDateString()
                  : "-"}
              </p>
            </div>
            <div>
              <span className="text-gray-400">Received</span>
              <p className="text-white">
                {po.received_date
                  ? new Date(po.received_date).toLocaleDateString()
                  : "-"}
              </p>
            </div>
          </div>

          {/* Tracking */}
          {(po.tracking_number || po.carrier) && (
            <div className="bg-gray-800/50 p-3 rounded-lg mb-6 text-sm">
              <span className="text-gray-400">Tracking: </span>
              <span className="text-white">
                {po.carrier} {po.tracking_number}
              </span>
            </div>
          )}

          {/* Lines */}
          <div className="mb-6">
            <h4 className="text-sm font-medium text-gray-300 mb-3">
              Line Items
            </h4>
            <div className="bg-gray-800/30 rounded-lg overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-gray-800/50">
                  <tr>
                    <th className="text-left py-2 px-3 text-xs text-gray-400">
                      #
                    </th>
                    <th className="text-left py-2 px-3 text-xs text-gray-400">
                      Item
                    </th>
                    <th className="text-right py-2 px-3 text-xs text-gray-400">
                      Ordered
                    </th>
                    <th className="text-right py-2 px-3 text-xs text-gray-400">
                      Received
                    </th>
                    <th className="text-right py-2 px-3 text-xs text-gray-400">
                      Unit Cost
                    </th>
                    <th className="text-right py-2 px-3 text-xs text-gray-400">
                      Total
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {po.lines?.map((line) => (
                    <tr key={line.id} className="border-t border-gray-800">
                      <td className="py-2 px-3 text-gray-400">
                        {line.line_number}
                      </td>
                      <td className="py-2 px-3">
                        <div className="text-white">{line.product_sku}</div>
                        <div className="text-xs text-gray-400">
                          {line.product_name}
                        </div>
                      </td>
                      <td className="py-2 px-3 text-right text-white">
                        {parseFloat(line.quantity_ordered).toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-right">
                        <span
                          className={
                            parseFloat(line.quantity_received) >=
                            parseFloat(line.quantity_ordered)
                              ? "text-green-400"
                              : "text-yellow-400"
                          }
                        >
                          {parseFloat(line.quantity_received).toFixed(2)}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right text-gray-400">
                        ${parseFloat(line.unit_cost).toFixed(2)}
                      </td>
                      <td className="py-2 px-3 text-right text-white">
                        ${parseFloat(line.line_total).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Totals */}
          <div className="text-right text-sm mb-6">
            <div className="text-gray-400">
              Subtotal: ${parseFloat(po.subtotal || 0).toFixed(2)}
            </div>
            <div className="text-gray-400">
              Tax: ${parseFloat(po.tax_amount || 0).toFixed(2)}
            </div>
            <div className="text-gray-400">
              Shipping: ${parseFloat(po.shipping_cost || 0).toFixed(2)}
            </div>
            <div className="text-lg font-semibold text-white mt-1">
              Total: ${parseFloat(po.total_amount || 0).toFixed(2)}
            </div>
          </div>

          {/* Documents */}
          <div className="mb-6">
            <DocumentUploadPanel
              poId={po.id}
              poNumber={po.po_number}
              onDocumentsChange={() => {
                // Optionally refresh PO details when documents change
              }}
            />
          </div>

          {/* Notes */}
          {po.notes && (
            <div className="bg-gray-800/30 p-3 rounded-lg mb-6">
              <span className="text-sm text-gray-400">Notes: </span>
              <span className="text-sm text-white">{po.notes}</span>
            </div>
          )}

          {/* Activity Timeline */}
          <div className="mb-6">
            <h4 className="text-sm font-medium text-gray-300 mb-3">
              Activity
            </h4>
            <div className="bg-gray-800/30 rounded-lg p-4 max-h-64 overflow-y-auto">
              <POActivityTimeline poId={po.id} />
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-between items-center pt-4 border-t border-gray-800">
            <div className="flex gap-2">
              {po.status === "draft" && (
                <>
                  <button
                    onClick={onEdit}
                    className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm text-white"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => onStatusChange(po.id, "ordered")}
                    className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 rounded-lg text-sm text-white"
                  >
                    Place Order
                  </button>
                </>
              )}
              {po.status === "ordered" && (
                <>
                  <button
                    onClick={() => onStatusChange(po.id, "shipped")}
                    className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 rounded-lg text-sm text-white"
                  >
                    Mark Shipped
                  </button>
                  <button
                    onClick={onReceive}
                    className="px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded-lg text-sm text-white"
                  >
                    Receive Items
                  </button>
                </>
              )}
              {po.status === "shipped" && (
                <button
                  onClick={onReceive}
                  className="px-3 py-1.5 bg-green-600 hover:bg-green-700 rounded-lg text-sm text-white"
                >
                  Receive Items
                </button>
              )}
              {po.status === "received" && (
                <button
                  onClick={() => onStatusChange(po.id, "closed")}
                  className="px-3 py-1.5 bg-gray-600 hover:bg-gray-700 rounded-lg text-sm text-white"
                >
                  Close PO
                </button>
              )}
              {!["received", "closed", "cancelled"].includes(po.status) && (
                <button
                  onClick={() => onStatusChange(po.id, "cancelled")}
                  className="px-3 py-1.5 bg-red-600/20 hover:bg-red-600/30 rounded-lg text-sm text-red-400"
                >
                  Cancel
                </button>
              )}
            </div>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300"
            >
              Close
            </button>
          </div>
    </Modal>
  );
}
