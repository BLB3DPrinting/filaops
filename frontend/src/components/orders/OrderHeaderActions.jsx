/**
 * OrderHeaderActions - Header action buttons (Refresh, Print Packing Slip).
 *
 * Extracted from OrderDetail.jsx (DEBT-1 D1-C).
 */
import { API_URL } from "../../config/api";

export default function OrderHeaderActions({ orderId, refreshing, onRefresh }) {
  return (
        <div className="flex gap-2">
          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 disabled:opacity-50"
            title="Refresh order data"
          >
            {refreshing ? "Refreshing..." : "\u21BB Refresh"}
          </button>
          <button
            onClick={() =>
              window.open(
                `${API_URL}/api/v1/sales-orders/${orderId}/packing-slip/pdf`,
                "_blank"
              )
            }
            className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
            title="Print packing slip PDF"
          >
            Print Packing Slip
          </button>
        </div>
  );
}
